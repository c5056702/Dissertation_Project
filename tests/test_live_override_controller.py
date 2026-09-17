"""Exercise live inputs and separated scenario inputs with fake Webots devices."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(SOURCE))
from model import WAYPOINTS
from validation import ValidationLogger


class Device:
    velocity = 0.0
    def enable(self, *_): pass
    def setPosition(self, *_): pass
    def setVelocity(self, value): self.velocity = value


class Keyboard(Device):
    END = 312
    def getKey(self): return -1


class Robot:
    def __init__(self, tick_limit=12):
        self.tick = 0
        self.tick_limit = tick_limit
        self.devices = {}
        self.samples = {}
    def getDevice(self, name): return self.devices.setdefault(name, Device())
    def getTime(self): return self.tick * .032
    def getFromDef(self, _): return None
    def setLabel(self, *_): pass
    def step(self, _):
        self.tick += 1
        self.samples[self.tick] = tuple(self.getDevice(n).velocity for n in ("left wheel motor", "right wheel motor"))
        return 0 if self.tick <= self.tick_limit else -1


class Navigator:
    obstacle_threshold = 4050
    maximum_sensor_peak = actual_path_length = 0.0
    index = 1
    def __init__(self, left, right, *_): self.left, self.right = left, right
    def position(self): return WAYPOINTS["S"]
    def start(self, _): pass
    def stop(self):
        self.left.setVelocity(0)
        self.right.setVelocity(0)
    def step(self):
        self.left.setVelocity(2)
        self.right.setVelocity(2)
        return "moving", {}


class LiveOverrideControllerTests(unittest.TestCase):
    def run_live(self, confirmation=None, *, schedule=None, travelled_position=None, scenario_actions=None,
                 initial_position=WAYPOINTS["S"], tick_limit=12, trace_schedule=None, wall_seconds_per_tick=0.25,
                 capture_dashboard=False):
        robot = Robot(tick_limit=tick_limit)
        if schedule is None:
            schedule = {1: {"command": "start"}, 2: {"command": "go to A"},
                        3: {"gesture": "NOD"}, 5: {"command": "go to B", "gesture": "NOD"}}
            if confirmation:
                schedule[9] = {"gesture": confirmation}
        schedule = {tick: dict(action) for tick, action in schedule.items()}
        robot.routes = []
        robot.dashboard_snapshots = []
        robot.dashboard_console_routes = []
        class TrackedNavigator(Navigator):
            current = initial_position
            points = []
            def position(self): return self.current
            def start(self, points):
                robot.routes.append(tuple(points))
                self.points = list(points)[1:]
            def step(self):
                if travelled_position is not None:
                    self.current = travelled_position(robot.routes[-1]) if callable(travelled_position) else travelled_position
                return super().step()
        class Inputs:
            ready = face_present = gesture_calibrated = True
            def poll(self): return schedule.pop(robot.tick, None)
            def status(self):
                return dict.fromkeys(("ready", "voice_ready", "camera_ready", "face_present", "gesture_calibrated"), True)
            def close(self): pass
        class TracedInputs(Inputs):
            trace = {}
            def poll(self):
                if robot.tick in trace_schedule:
                    self.trace = trace_schedule[robot.tick]
                return super().poll()
            def status(self):
                return {**super().status(), "voice_reconnects": self.trace.get("voice_reconnects", 1)}
            def trace_status(self): return self.trace
        class Logger(ValidationLogger):
            def event(self, name, **details):
                return super().event(name, simulation_tick=robot.tick, **details)
        class Dashboard:
            def __init__(self, **_): pass
            def update(self, snapshot, *_args, **_kwargs):
                robot.dashboard_snapshots.append((robot.tick, snapshot))
                route_lines = [line.removeprefix("[route] ") for line in controller_output.getvalue().splitlines()
                               if line.startswith("[route] ")]
                robot.dashboard_console_routes.append(route_lines[-1] if route_lines else None)
                return True
            def poll_action(self): return None
            def record_event(self, _entry): pass
            def close(self): pass
        if capture_dashboard:
            Inputs.trace_status = lambda self: self.status()
            Inputs.consume_preview_frame = lambda self: None
        webots = types.SimpleNamespace(Supervisor=lambda: robot, Keyboard=Keyboard)
        modules = {"controller": webots}
        if capture_dashboard:
            modules["live_dashboard"] = types.SimpleNamespace(LiveTraceDashboard=Dashboard)
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, modules), patch.dict(os.environ, {"EPUCK_DISABLE_DASHBOARD": "0" if capture_dashboard else "1", "EPUCK_DISABLE_CAMERA": "1", "EPUCK_VALIDATION_DIR": folder}, clear=True):
            if scenario_actions is not None:
                scenario_path = Path(folder) / "scenario.json"
                scenario_path.write_text(json.dumps({"actions": scenario_actions, "expected_terminal": "safe_stop"}), encoding="utf-8")
                os.environ["EPUCK_SCENARIO_FILE"] = str(scenario_path)
            spec = importlib.util.spec_from_file_location("live_controller_under_test", SOURCE / "epuck_waypoint_controller.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            inputs = Inputs() if trace_schedule is None else TracedInputs()
            controller_output = io.StringIO()
            with patch.object(module, "LocalMultimodalInput", return_value=inputs), patch.object(module, "WaypointNavigator", TrackedNavigator), patch.object(module, "ValidationLogger", Logger), patch.object(module, "monotonic", side_effect=lambda: robot.tick * wall_seconds_per_tick), contextlib.redirect_stdout(controller_output):
                robot.controller_result = module.main()
            robot.controller_output = controller_output.getvalue()
            events = [json.loads(line) for line in (Path(folder) / "controller_events.ndjson").read_text().splitlines()]
        return robot, events

    def test_console_and_dashboard_agree_through_confirmation_override_and_stop(self):
        from live_dashboard import LiveTraceDashboard
        for destination in "ABCS":
            with self.subTest(destination=destination):
                replacement = "B" if destination != "B" else "C"
                robot, events = self.run_live(capture_dashboard=True,
                    initial_position=WAYPOINTS["A" if destination == "S" else "S"], schedule={
                        1: {"command": "start"}, 2: {"command": f"go to {destination}"},
                        3: {"gesture": "TILT_RIGHT"}, 5: {"gesture": "NOD"},
                        6: {"gesture": "TILT_LEFT"}, 7: {"gesture": "TILT_RIGHT"},
                        8: {"command": f"go to {replacement}"}, 9: {"gesture": "NOD"},
                        10: {"command": "stop"}, 11: {"command": "start"},
                    })
                self.assertFalse(any(e["event"] == "dashboard_failure" for e in events))
                for (_, current), console in zip(robot.dashboard_snapshots, robot.dashboard_console_routes):
                    self.assertEqual(console, current["route_status"])
                    self.assertEqual(console, LiveTraceDashboard.selected_route_text(current))
                snapshots = dict(robot.dashboard_snapshots)
                self.assertEqual(snapshots[4]["route_status"], f"TO {destination}: ALTERNATIVE - awaiting NOD")
                self.assertEqual(snapshots[6]["route_status"], f"TO {destination}: ALTERNATIVE - navigating")
                self.assertEqual(snapshots[7]["route_status"], f"TO {destination}: SHORTEST - awaiting NOD")
                self.assertEqual(snapshots[8]["route_status"], f"TO {destination}: ALTERNATIVE - awaiting NOD")
                self.assertEqual(snapshots[9]["route_status"], f"TO {replacement}: SHORTEST - awaiting NOD")
                self.assertEqual(snapshots[10]["route_status"], f"TO {replacement}: SHORTEST - navigating")
                self.assertEqual(snapshots[11]["route_status"], "None - START required")
                self.assertEqual(snapshots[12]["route_status"], "None - choose a destination")
                self.assertNotIn("awaiting NOD", snapshots[6]["last_route_selection"])

    def test_dashboard_shows_new_destination_and_choice_while_old_route_is_paused(self):
        robot, events = self.run_live(capture_dashboard=True, schedule={
            1: {"command": "start"}, 2: {"command": "go to A"}, 3: {"gesture": "NOD"},
            4: {"command": "go to B"}, 5: {"gesture": "TILT_RIGHT"},
            6: {"command": "go to B"}, 7: {"gesture": "NOD"},
        })
        self.assertFalse(any(e["event"] == "dashboard_error" for e in events))
        snapshots = dict(robot.dashboard_snapshots)
        for tick in (6, 7):
            pending = snapshots[tick]
            self.assertEqual(pending["destination"], "B")
            self.assertEqual(pending["pending_destination"], "B")
            self.assertEqual(pending["pending_route_choice"], "alternative")
            self.assertEqual(pending["active_destination"], "A")
            self.assertIsNone(pending["route"])
            self.assertIsNone(pending["next_waypoint"])
            self.assertIn("ALTERNATIVE selected", pending["last_route_selection"])
        self.assertEqual(snapshots[8]["active_destination"], "B")
        self.assertEqual(snapshots[8]["active_route_choice"], "alternative")

    def test_unavailable_alternative_remains_stopped_and_is_reported(self):
        with patch('model.ROUTE_GRAPH.plan', side_effect=ValueError('alternative_route_unavailable')):
            robot, events = self.run_live(capture_dashboard=True, schedule={
                1: {"command": "start"}, 2: {"command": "go to A"},
                3: {"gesture": "TILT_RIGHT"}, 5: {"gesture": "NOD"},
            })
        self.assertEqual(robot.routes, [])
        self.assertTrue(all(sample == (0, 0) for sample in robot.samples.values()))
        self.assertEqual(dict(robot.dashboard_snapshots)[6]["route_selection_error"], "TO A: ALTERNATIVE unavailable")
        self.assertTrue(any(e["event"] == "route_selection_unavailable" and e["destination"] == "A" for e in events))

    def test_right_selection_survives_repeated_destination_and_every_tilt_is_printed(self):
        for destination in "ABCS":
            with self.subTest(destination=destination):
                origin = "A" if destination == "S" else "S"
                robot, events = self.run_live(initial_position=WAYPOINTS[origin], schedule={
                    1: {"command": "start"}, 2: {"command": f"go to {destination}"},
                    3: {"gesture": "TILT_RIGHT"}, 4: {"gesture": "TILT_RIGHT"},
                    5: {"command": f"go to {destination}"}, 7: {"gesture": "NOD"},
                })
                selections = [e for e in events if e["event"] == "route_selection"]
                self.assertEqual(len(selections), 2)
                for selection in selections:
                    self.assertEqual(selection["destination"], destination)
                    self.assertEqual(selection["route_choice"], "alternative")
                    self.assertTrue(selection["selected"])
                    self.assertIn(f"TO {destination}: ALTERNATIVE selected", selection["message"])
                self.assertEqual(robot.controller_output.count(f"TILT RIGHT -> TO {destination}: ALTERNATIVE selected"), 2)
                confirms = [e for e in events if e["event"] == "command_confirmed"]
                self.assertEqual(len(confirms), 1)
                self.assertTrue(confirms[0]["alternative"])
                self.assertIn(f"TO {destination}: ALTERNATIVE;", robot.controller_output)
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(1, 8)))

    def test_every_pending_tilt_reports_final_choice_and_new_destination(self):
        robot, events = self.run_live(schedule={
            1: {"command": "start"}, 2: {"command": "go to A"}, 3: {"gesture": "NOD"},
            4: {"command": "go to B"}, 5: {"gesture": "TILT_RIGHT"},
            6: {"gesture": "TILT_LEFT"}, 7: {"gesture": "TILT_RIGHT"}, 9: {"gesture": "NOD"},
        })
        selections = [e for e in events if e["event"] == "route_selection"]
        self.assertEqual([e["destination"] for e in selections], ["B"] * 3)
        self.assertEqual([e["route_choice"] for e in selections], ["alternative", "shortest", "alternative"])
        confirms = [e for e in events if e["event"] == "command_confirmed"]
        self.assertEqual(confirms[-1]["destination"], "B")
        self.assertTrue(confirms[-1]["alternative"])
        self.assertIn("TILT LEFT -> TO B: SHORTEST selected", robot.controller_output)

    def test_tilt_with_voice_is_reported_as_ignored_not_selected(self):
        robot, events = self.run_live(schedule={
            1: {"command": "start"}, 2: {"command": "go to A"}, 3: {"gesture": "NOD"},
            5: {"command": "go to B", "gesture": "TILT_RIGHT"}, 9: {"gesture": "NOD"},
        })
        ignored = next(e for e in events if e["event"] == "route_selection")
        self.assertFalse(ignored["selected"])
        self.assertEqual(ignored["outcome"], "ignored_voice_priority")
        self.assertIn("voice GO TO B has priority", robot.controller_output)
        confirms = [e for e in events if e["event"] == "command_confirmed"]
        self.assertFalse(confirms[-1]["alternative"])

    @staticmethod
    def rejected_voice_decision(decision_id=1):
        return {
            "decision_id": decision_id, "source": "local_vosk_microphone",
            "transcript": "go to a", "command": "go to A", "confidence": 0.42,
            "threshold": 0.65, "accepted": False, "reason": "low_confidence",
            "word_confidences": [{"word": "go", "confidence": 1.0}, {"word": "a", "confidence": 0.42}],
        }

    def test_rejected_final_voice_decision_logged_once_without_raw_trace(self):
        decision = self.rejected_voice_decision()
        decision["audio"] = "must stay transient"
        decision["word_confidences"][0]["landmarks"] = "must stay transient"
        robot, events = self.run_live(schedule={}, trace_schedule={
            1: {"voice": {"transcript": "go", "reason": "partial_transcript"}},
            2: {"voice_final_decision": decision, "frame": "must stay transient"},
            3: {"voice_final_decision": decision, "voice": {"transcript": "", "reason": "empty_transcript"}},
            4: {"voice_final_decision": decision, "voice": {"transcript": "go to", "reason": "partial_transcript"}},
        })
        finals = [event for event in events if event["event"] == "voice_final_decision"]
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0]["simulation_tick"], 2)
        for key, value in self.rejected_voice_decision().items():
            self.assertEqual(finals[0][key], value)
        self.assertNotIn("audio", finals[0])
        self.assertNotIn("frame", finals[0])
        self.assertNotIn("landmarks", finals[0]["word_confidences"][0])
        self.assertFalse(any(event["event"] == "command_recognised" for event in events))
        self.assertTrue(all(sample == (0, 0) for sample in robot.samples.values()))

    def test_repeated_final_voice_text_logs_each_new_decision_id(self):
        _, events = self.run_live(schedule={}, trace_schedule={
            2: {"voice_final_decision": self.rejected_voice_decision(1)},
            5: {"voice_final_decision": self.rejected_voice_decision(2)},
        })
        finals = [event for event in events if event["event"] == "voice_final_decision"]
        self.assertEqual([event["simulation_tick"] for event in finals], [2, 5])
        self.assertEqual([event["decision_id"] for event in finals], [1, 2])

    def test_voice_reconnect_logs_restarted_final_decision_id(self):
        decision = self.rejected_voice_decision(1)
        _, events = self.run_live(schedule={}, trace_schedule={
            2: {"voice_reconnects": 1, "voice_final_decision": decision},
            4: {"voice_reconnects": 2, "voice_final_decision": None},
            5: {"voice_reconnects": 2, "voice_final_decision": decision},
        })
        finals = [event for event in events if event["event"] == "voice_final_decision"]
        self.assertEqual([event["simulation_tick"] for event in finals], [2, 5])
        self.assertEqual([(event["voice_reconnects"], event["decision_id"]) for event in finals], [(1, 1), (2, 1)])

    @staticmethod
    def gesture_diagnostic_trace(gate="waiting_for_tilt", **changes):
        return {"gesture_trace": {
            "tilt_gate": gate, "tilt_direction": None, "armed": True, "candidate": None,
            "tilt_blocked_axes": [], "neutral_axes_outside": [], **changes,
        }}

    def test_gesture_diagnostics_log_moving_and_pending_context_without_raw_fields(self):
        trace = self.gesture_diagnostic_trace(
            "yaw_outside_range", tilt_direction="TILT_RIGHT", tilt_blocked_axes=["yaw"],
            pose=[0.1, 0.2, 0.3], face_box=[0, 0, 1, 1], evidence={"roll": 0.3},
            frame="private frame", landmarks="private landmarks", tilt_frames=2, tilt_frames_required=3,
        )
        schedule = self.travelling_schedule(**{"7": {"gesture": "TILT_RIGHT"}, "11": {"gesture": "NOD"}})
        robot, events = self.run_live(schedule=schedule, trace_schedule={1: trace})
        diagnostics = [event for event in events if event["event"] == "gesture_detection_status"]
        moving = next(event for event in diagnostics if event["state"] == "NAVIGATING")
        self.assertEqual(moving["tilt_gate"], "yaw_outside_range")
        self.assertEqual(moving["tilt_direction"], "TILT_RIGHT")
        self.assertEqual(moving["tilt_blocked_axes"], ["yaw"])
        self.assertTrue(moving["armed"])
        self.assertFalse(moving["pending_confirmation"])
        self.assertEqual(moving["active_destination"], "A")
        pending = next(event for event in diagnostics if event["state"] == "PAUSED")
        self.assertTrue(pending["pending_confirmation"])
        self.assertEqual(pending["pending_command"], "go to A")
        allowed = {"event", "time", "session_id", "simulation_tick", "sample_reason", "tilt_gate", "tilt_direction",
                   "armed", "candidate", "tilt_blocked_axes", "neutral_axes_outside", "state", "pending_confirmation",
                   "pending_command", "active_destination"}
        self.assertTrue(all(set(event) <= allowed for event in diagnostics))
        self.assertEqual(len(robot.routes), 2)
        self.assertEqual(robot.samples[12], (2, 2))

    def test_gesture_diagnostic_changes_are_limited_to_two_per_wall_second(self):
        gates = ["waiting_for_tilt", "pitch_outside_range", "yaw_outside_range", "holding_tilt",
                 "waiting_for_neutral", "cooldown", "waiting_for_tilt"]
        _, events = self.run_live(schedule={}, trace_schedule={
            tick: self.gesture_diagnostic_trace(gate) for tick, gate in enumerate(gates, 1)
        })
        diagnostics = [event for event in events if event["event"] == "gesture_detection_status"]
        self.assertEqual([event["simulation_tick"] for event in diagnostics], [1, 3, 5, 7])
        self.assertEqual([event["tilt_gate"] for event in diagnostics], gates[::2])
        self.assertTrue(all(event["sample_reason"] == "changed" for event in diagnostics))

    def test_unchanged_gesture_diagnostics_refresh_every_five_wall_seconds(self):
        _, events = self.run_live(schedule={}, tick_limit=22, trace_schedule={
            1: self.gesture_diagnostic_trace(tilt_frames=0),
            10: self.gesture_diagnostic_trace(tilt_frames=1, pose=[0.1, 0.2, 0.3]),
        })
        diagnostics = [event for event in events if event["event"] == "gesture_detection_status"]
        self.assertEqual([event["simulation_tick"] for event in diagnostics], [1, 21])
        self.assertEqual([event["sample_reason"] for event in diagnostics], ["changed", "periodic"])

    def test_scenario_tilt_accepts_separate_confirmation(self):
        robot, events = self.run_live(scenario_actions=[
            {"command": "start"},
            {"command": "go to A", "gesture": "NOD"},
            {"gesture": "TILT_RIGHT", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "1"},
            {"gesture": "NOD"},
            {"command": "stop"},
        ])
        pending = next(e for e in events if e["event"] == "gesture_route_override_pending")
        confirmation = next(e for e in events if e["event"] == "command_confirmed" and e.get("alternative"))
        self.assertGreater(confirmation["simulation_tick"], pending["simulation_tick"])
        self.assertEqual(robot.samples[confirmation["simulation_tick"]], (0, 0))
        self.assertEqual(len(robot.routes), 2)
        self.assertEqual(robot.controller_result, 0)

    def test_scenario_tilt_accepts_separate_safety_stop(self):
        for stop in ({"gesture": "SHAKE"}, {"command": "stop"}):
            with self.subTest(stop=stop):
                robot, events = self.run_live(scenario_actions=[
                    {"command": "start"},
                    {"command": "go to A", "gesture": "NOD"},
                    {"gesture": "TILT_RIGHT", "wait_for_route": "GRAPH_S_A"},
                    stop,
                ])
                self.assertEqual(len(robot.routes), 1)
                self.assertEqual(robot.controller_result, 0)
                self.assertEqual(robot.getDevice("left wheel motor").velocity, 0)
                self.assertEqual(robot.getDevice("right wheel motor").velocity, 0)
                self.assertTrue(any(e["event"] == "safety_stop" and e["state"] == "STOPPED" for e in events))

    def test_override_waits_for_later_nod_and_switches_modes(self):
        robot, events = self.run_live("NOD")
        self.assertEqual(robot.samples[5], (2, 2))  # travelling before GO TO B
        for tick in range(6, 10):
            self.assertEqual(robot.samples[tick], (0, 0))
        confirms = [e for e in events if e["event"] == "command_confirmed" and e.get("command") == "go to B"]
        self.assertEqual([e["simulation_tick"] for e in confirms], [9])
        modes = [(e["simulation_tick"], e["mode"]) for e in events if e["event"] == "input_mode_changed"]
        self.assertIn((5, "MICROPHONE"), modes)
        self.assertIn((9, "CAMERA"), modes)
        self.assertEqual(robot.samples[10], (2, 2))

    def test_no_later_nod_never_restarts(self):
        robot, events = self.run_live(None)
        self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 14)))
        self.assertFalse(any(e["event"] == "command_confirmed" and e.get("command") == "go to B" for e in events))

    def test_shake_cancels_pending_override(self):
        robot, events = self.run_live("SHAKE")
        self.assertEqual(robot.samples[10], (0, 0))
        self.assertTrue(any(e["event"] == "safety_stop" and e.get("source") == "head_shake" for e in events))

    @staticmethod
    def travelling_schedule(**actions):
        schedule = {1: {"command": "start"}, 2: {"command": "go to A"},
                    3: {"gesture": "NOD"}}
        schedule.update({int(tick): action for tick, action in actions.items()})
        return schedule

    def test_travelling_tilt_stops_until_fresh_nod_and_replans_same_destination(self):
        current = (-1.20, 2.02)
        for gesture, alternative in (("TILT_LEFT", False), ("TILT_RIGHT", True)):
            with self.subTest(gesture=gesture):
                schedule = self.travelling_schedule(**{"5": {"gesture": gesture}, "9": {"gesture": "NOD"}})
                robot, events = self.run_live(schedule=schedule, travelled_position=current)
                self.assertEqual(robot.samples[5], (2, 2))
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 10)))
                confirms = [event for event in events if event["event"] == "command_confirmed"]
                self.assertEqual([event["simulation_tick"] for event in confirms], [3, 9])
                self.assertEqual(confirms[-1]["command"], "go to A")
                self.assertEqual(confirms[-1]["destination"], "A")
                self.assertEqual(confirms[-1]["alternative"], alternative)
                self.assertEqual(tuple(confirms[-1]["position"]), current)
                self.assertEqual(robot.routes[-1][0], current)
                self.assertEqual(robot.routes[-1][-1], WAYPOINTS["A"])
                self.assertEqual(robot.samples[10], (2, 2))

    def test_travelling_tilt_without_nod_keeps_motors_stopped(self):
        for gesture in ("TILT_LEFT", "TILT_RIGHT"):
            with self.subTest(gesture=gesture):
                robot, events = self.run_live(schedule=self.travelling_schedule(**{"5": {"gesture": gesture}}))
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 14)))
                self.assertEqual(len(robot.routes), 1)

    @staticmethod
    def advance_along_route(points):
        start = points[0]
        end = next(point for point in points[1:] if point != start)
        return tuple((first + second) / 2 for first, second in zip(start, end))

    def test_repeated_travelling_tilts_work_for_every_destination(self):
        for destination in ("A", "B", "C", "S"):
            for first_tilt in ("TILT_LEFT", "TILT_RIGHT"):
                for second_tilt in ("TILT_LEFT", "TILT_RIGHT"):
                    with self.subTest(destination=destination, first=first_tilt, second=second_tilt):
                        origin = "A" if destination == "S" else "S"
                        schedule = {
                            1: {"command": "start"}, 2: {"command": f"go to {destination}"},
                            3: {"gesture": "NOD"}, 5: {"gesture": first_tilt}, 7: {"gesture": "NOD"},
                            9: {"gesture": second_tilt}, 11: {"gesture": "NOD"},
                        }
                        robot, events = self.run_live(schedule=schedule, initial_position=WAYPOINTS[origin],
                                                      travelled_position=self.advance_along_route)
                        confirms = [e for e in events if e["event"] == "command_confirmed"]
                        self.assertEqual([e["simulation_tick"] for e in confirms], [3, 7, 11])
                        self.assertEqual([e["alternative"] for e in confirms],
                                         [False, first_tilt == "TILT_RIGHT", second_tilt == "TILT_RIGHT"])
                        self.assertEqual(len(robot.routes), 3)
                        self.assertEqual([e["destination"] for e in confirms], [destination] * 3)
                        self.assertEqual([e["state"] for e in confirms], ["NAVIGATING"] * 3)
                        for index in (1, 2):
                            current = self.advance_along_route(robot.routes[index - 1])
                            self.assertEqual(robot.routes[index][0], current)
                            self.assertEqual(tuple(confirms[index]["position"]), current)
                            self.assertEqual(robot.routes[index][-1], WAYPOINTS[destination])
                        self.assertTrue(all(robot.samples[t] == (0, 0) for t in (6, 7, 10, 11)))
                        self.assertTrue(all(robot.samples[t] == (2, 2) for t in (5, 8, 9, 12, 13)))
                        self.assertFalse(any(e["event"] in {"route_failed", "safety_stop"} for e in events))

    def test_repeated_pending_tilts_work_for_every_destination(self):
        for destination in ("A", "B", "C", "S"):
            with self.subTest(destination=destination):
                origin = "A" if destination == "S" else "S"
                robot, events = self.run_live(initial_position=WAYPOINTS[origin], schedule={
                    1: {"command": "start"}, 2: {"command": f"go to {destination}"},
                    3: {"gesture": "TILT_RIGHT"}, 5: {"gesture": "TILT_LEFT"},
                    7: {"gesture": "TILT_RIGHT"}, 9: {"gesture": "NOD"},
                })
                selections = [e for e in events if e["event"] == "gesture_recognised" and e["gesture"].startswith("TILT")]
                self.assertEqual([e["outcome"] for e in selections],
                                 ["route_alternative_selected", "route_short_selected", "route_alternative_selected"])
                confirms = [e for e in events if e["event"] == "command_confirmed"]
                self.assertEqual([e["simulation_tick"] for e in confirms], [9])
                self.assertEqual(confirms[0]["destination"], destination)
                self.assertTrue(confirms[0]["alternative"])
                self.assertEqual(len(robot.routes), 1)
                self.assertEqual(robot.routes[0][-1], WAYPOINTS[destination])
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(1, 10)))
                self.assertFalse(any(e["event"] in {"route_failed", "safety_stop"} for e in events))

    def test_voice_replacement_after_second_travelling_tilt_requires_new_nod(self):
        for destination, replacement in (("A", "C"), ("B", "S"), ("C", "A"), ("S", "B")):
            with self.subTest(destination=destination, replacement=replacement):
                origin = "A" if destination == "S" else "S"
                schedule = {
                    1: {"command": "start"}, 2: {"command": f"go to {destination}"},
                    3: {"gesture": "NOD"}, 5: {"gesture": "TILT_RIGHT"}, 7: {"gesture": "NOD"},
                    9: {"gesture": "TILT_RIGHT"},
                    11: {"command": f"go to {replacement}", "gesture": "NOD"},
                    15: {"gesture": "NOD"},
                }
                robot, events = self.run_live(schedule=schedule, initial_position=WAYPOINTS[origin],
                                              travelled_position=self.advance_along_route, tick_limit=16)
                confirms = [e for e in events if e["event"] == "command_confirmed"]
                self.assertEqual([e["simulation_tick"] for e in confirms], [3, 7, 15])
                self.assertEqual([e["destination"] for e in confirms], [destination, destination, replacement])
                self.assertEqual([e["alternative"] for e in confirms], [False, True, False])
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(10, 16)))
                self.assertEqual(robot.samples[16], (2, 2))
                self.assertEqual(robot.routes[-1][0], self.advance_along_route(robot.routes[-2]))
                self.assertEqual(robot.routes[-1][-1], WAYPOINTS[replacement])

    def test_stop_and_shake_cancel_pending_travelling_tilt(self):
        for action, source in (({"command": "stop"}, "voice"), ({"gesture": "SHAKE"}, "head_shake")):
            with self.subTest(source=source):
                schedule = self.travelling_schedule(**{"5": {"gesture": "TILT_RIGHT"}, "7": action,
                                                       "9": {"gesture": "NOD"}, "11": {"command": "start"}})
                robot, events = self.run_live(schedule=schedule)
                self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 14)))
                self.assertEqual(len(robot.routes), 1)
                self.assertTrue(any(e["event"] == "safety_stop" and e.get("source") == source for e in events))
                self.assertTrue(any(e["event"] == "system_activated" and e["simulation_tick"] == 11 for e in events))

    def test_voice_destination_takes_priority_over_simultaneous_tilt(self):
        schedule = self.travelling_schedule(**{"5": {"command": "go to B", "gesture": "TILT_RIGHT"},
                                               "9": {"gesture": "NOD"}})
        robot, events = self.run_live(schedule=schedule)
        self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 10)))
        confirms = [e for e in events if e["event"] == "command_confirmed"]
        self.assertEqual([e["simulation_tick"] for e in confirms], [3, 9])
        self.assertEqual(confirms[-1]["destination"], "B")
        self.assertFalse(confirms[-1]["alternative"])

    def test_pickup_during_tilt_confirmation_stops_and_allows_fresh_start(self):
        schedule = self.travelling_schedule(**{"5": {"gesture": "TILT_RIGHT"}, "7": {"command": "pickup"},
                                               "9": {"gesture": "NOD"}, "11": {"command": "start"}})
        robot, events = self.run_live(schedule=schedule)
        self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 14)))
        self.assertEqual(len(robot.routes), 1)
        self.assertTrue(any(e["event"] == "safety_stop" and e.get("source") == "conflicting_pending_command" for e in events))
        self.assertTrue(any(e["event"] == "system_activated" and e["simulation_tick"] == 11 for e in events))

    def test_tilt_after_voice_direction_pause_waits_for_nod(self):
        schedule = self.travelling_schedule(**{"5": {"command": "left"}, "7": {"gesture": "TILT_RIGHT"},
                                               "9": {"gesture": "NOD"}})
        robot, events = self.run_live(schedule=schedule, travelled_position=(-1.20, 2.02))
        self.assertTrue(all(robot.samples[t] == (0, 0) for t in range(6, 10)))
        confirms = [e for e in events if e["event"] == "command_confirmed"]
        self.assertEqual([e["simulation_tick"] for e in confirms], [3, 9])
        self.assertEqual(confirms[-1]["destination"], "A")
        self.assertTrue(confirms[-1]["alternative"])
        self.assertEqual(robot.samples[10], (2, 2))

    def test_nod_alone_during_travel_does_not_replan_or_stop(self):
        robot, events = self.run_live(schedule=self.travelling_schedule(**{"5": {"gesture": "NOD"}}))
        self.assertTrue(all(robot.samples[t] == (2, 2) for t in range(5, 14)))
        self.assertEqual(len(robot.routes), 1)


if __name__ == "__main__":
    unittest.main()
