from pathlib import Path
import math
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from model import ROUTE_GRAPH, TaskMachine, TaskState, WAYPOINTS, live_startup_gate, normalise_command, route_length
from input_adapters import parse_vosk_result


class ExpandedNavigationTests(unittest.TestCase):
    def test_live_startup_gate_is_activation_only(self):
        self.assertEqual(live_startup_gate("start", TaskState.IDLE), "start")
        self.assertEqual(live_startup_gate("start A", TaskState.IDLE), "start")
        self.assertEqual(live_startup_gate("start B", TaskState.STOPPED), "start")
        self.assertEqual(live_startup_gate("start A", TaskState.READY), "start A")
        self.assertEqual(live_startup_gate("go to A", TaskState.IDLE), "go to A")

    def test_standalone_start_activates_without_movement_request(self):
        machine = TaskMachine()
        self.assertEqual(machine.state, TaskState.IDLE)
        self.assertEqual(machine.accept_command("START"), (True, "activated"))
        self.assertEqual(machine.state, TaskState.READY)
        self.assertIsNone(machine.pending_command)

    def test_destination_command_defaults_to_shortest_and_needs_nod(self):
        machine = TaskMachine()
        machine.accept_command("start")
        self.assertEqual(machine.accept_command("go to A"), (True, "pending_confirmation"))
        self.assertEqual(machine.state, TaskState.READY)
        outcome, request = machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(outcome, "route_started")
        self.assertEqual(request.destination, "A")
        self.assertFalse(request.alternative)
        self.assertEqual(machine.state, TaskState.NAVIGATING)

    def test_right_tilt_selects_distinct_alternative(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        self.assertEqual(machine.accept_gesture("TILT_RIGHT")[0], "route_alternative_selected")
        _, alternative = machine.accept_gesture("NOD", WAYPOINTS["S"])
        shortest = ROUTE_GRAPH.plan(WAYPOINTS["S"], "A")
        self.assertTrue(alternative.alternative)
        self.assertGreater(route_length(alternative.points), route_length(shortest.points))
        self.assertEqual(alternative.segment_ids, ("S_A_LONG",))
        self.assertNotIn("A_B", alternative.segment_ids)

    def test_every_directed_waypoint_pair_has_shortest_and_alternative(self):
        for origin in WAYPOINTS:
            for destination in WAYPOINTS:
                if origin == destination:
                    continue
                with self.subTest(origin=origin, destination=destination):
                    shortest = ROUTE_GRAPH.plan(WAYPOINTS[origin], destination)
                    alternative = ROUTE_GRAPH.plan(WAYPOINTS[origin], destination, alternative=True)
                    self.assertEqual(shortest.points[0], WAYPOINTS[origin])
                    self.assertEqual(shortest.points[-1], WAYPOINTS[destination])
                    self.assertGreaterEqual(route_length(alternative.points), route_length(shortest.points))
                    self.assertNotEqual(shortest.points, alternative.points)

    def test_current_position_replan_starts_at_measured_pose(self):
        current = (-1.20, 2.02)
        request = ROUTE_GRAPH.plan(current, "B")
        self.assertEqual(request.points[0], current)
        self.assertEqual(request.points[-1], WAYPOINTS["B"])

    def test_replan_rejects_pose_outside_route_network(self):
        with self.assertRaisesRegex(ValueError, "current_position_outside_route_network"):
            ROUTE_GRAPH.plan((20.0, 20.0), "A")

    def test_mid_route_direction_pauses_and_continue_resumes(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(machine.accept_command("turn right"), (True, "clarification_required"))
        self.assertEqual(machine.state, TaskState.PAUSED)
        self.assertEqual(machine.accept_command("continue"), (True, "resume_navigation"))
        self.assertEqual(machine.state, TaskState.NAVIGATING)

    def test_mid_route_destination_change_uses_current_pose(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(machine.accept_command("go to B"), (True, "pending_confirmation"))
        current = (-1.20, 2.02)
        _, request = machine.accept_gesture("NOD", current)
        self.assertEqual(request.points[0], current)
        self.assertEqual(request.destination, "B")

    def test_mid_route_tilts_pause_and_require_nod_to_replan_same_destination(self):
        current = (-1.20, 2.02)
        for gesture, choice, outcome in (("TILT_LEFT", "shortest", "route_short_selected"),
                                         ("TILT_RIGHT", "alternative", "route_alternative_selected")):
            with self.subTest(gesture=gesture):
                machine = TaskMachine()
                machine.accept_command("start")
                machine.accept_command("go to A")
                machine.accept_gesture("NOD", WAYPOINTS["S"])
                self.assertEqual(machine.accept_gesture(gesture, current), (outcome, None))
                self.assertEqual(machine.state, TaskState.PAUSED)
                self.assertEqual(machine.pending_command, "go to A")
                self.assertEqual(machine.route_choice, choice)
                self.assertEqual(machine.active_destination, "A")
                result, request = machine.accept_gesture("NOD", current)
                self.assertEqual(result, "route_started")
                self.assertEqual(request.destination, "A")
                self.assertEqual(request.points[0], current)
                self.assertEqual(request.alternative, choice == "alternative")
                self.assertEqual(machine.state, TaskState.NAVIGATING)

    def test_tilt_selects_route_after_voice_direction_pause(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        machine.accept_command("right")
        self.assertEqual(machine.accept_gesture("TILT_RIGHT"), ("route_alternative_selected", None))
        self.assertEqual(machine.state, TaskState.PAUSED)
        self.assertEqual(machine.pending_command, "go to A")
        self.assertEqual(machine.route_choice, "alternative")
        machine.accept_gesture("TILT_LEFT")
        self.assertEqual(machine.route_choice, "shortest")
        self.assertEqual(machine.state, TaskState.PAUSED)

    @staticmethod
    def legacy_machine_at_phase(phase):
        machine = TaskMachine()
        machine.accept_command("start A")
        machine.accept_gesture("TILT_LEFT")
        machine.accept_gesture("NOD")
        if phase == TaskState.TO_PICKUP:
            return machine
        machine.route_finished()
        machine.accept_command("pickup")
        machine.accept_gesture("NOD")
        machine.accept_command("drop off")
        machine.accept_gesture("NOD")
        if phase == TaskState.TO_DROPOFF:
            return machine
        machine.route_finished()
        machine.accept_command("return")
        machine.accept_gesture("NOD")
        return machine

    def test_same_destination_tilt_preserves_legacy_phase_and_arrival(self):
        phases = (
            (TaskState.TO_PICKUP, "A", (-1.20, 2.02), TaskState.AT_PICKUP, "pickup_waypoint_reached", "pickup"),
            (TaskState.TO_DROPOFF, "C", (2.25, 0.0), TaskState.AT_DROPOFF, "dropoff_waypoint_reached", "return"),
            (TaskState.TO_RETURN, "S", (2.25, 0.0), TaskState.READY, "execution_completed", "go to B"),
        )
        for phase, destination, current, arrival, completion, next_command in phases:
            for paused in (False, True):
                for gesture in ("TILT_LEFT", "TILT_RIGHT"):
                    with self.subTest(phase=phase, paused=paused, gesture=gesture):
                        machine = self.legacy_machine_at_phase(phase)
                        if paused:
                            machine.accept_command("left")
                        machine.accept_gesture(gesture, current)
                        self.assertEqual(machine.state, TaskState.PAUSED)
                        outcome, request = machine.accept_gesture("NOD", current)
                        self.assertEqual(outcome, "route_started")
                        self.assertEqual(request.destination, destination)
                        self.assertEqual(request.points[0], current)
                        self.assertEqual(request.alternative, gesture == "TILT_RIGHT")
                        self.assertEqual(machine.state, phase)
                        self.assertEqual(machine.active_mode, "legacy")
                        self.assertEqual(machine.route_finished(), completion)
                        self.assertEqual(machine.state, arrival)
                        self.assertEqual(machine.current_location, destination)
                        self.assertEqual(machine.accept_command(next_command), (True, "pending_confirmation"))

    def test_repeated_legacy_tilt_destination_preserves_choice_and_different_one_replaces(self):
        for phase in (TaskState.TO_PICKUP, TaskState.TO_DROPOFF, TaskState.TO_RETURN):
            for same_destination in (False, True):
                with self.subTest(phase=phase, same_destination=same_destination):
                    machine = self.legacy_machine_at_phase(phase)
                    destination = machine.active_destination if same_destination else "B"
                    machine.accept_gesture("TILT_RIGHT")
                    self.assertEqual(machine.accept_command(f"go to {destination}"), (True, "pending_confirmation"))
                    _, request = machine.accept_gesture("NOD", (-1.20, 2.02))
                    self.assertEqual(request.destination, destination)
                    self.assertEqual(request.alternative, same_destination)
                    self.assertEqual(machine.state, phase if same_destination else TaskState.NAVIGATING)
                    self.assertEqual(machine.active_mode, "legacy" if same_destination else "general")
                    if not same_destination:
                        self.assertEqual(machine.route_finished(), "destination_reached")
                        self.assertEqual(machine.state, TaskState.ARRIVED)

    def test_shake_clears_pending_legacy_phase_before_restart(self):
        machine = self.legacy_machine_at_phase(TaskState.TO_PICKUP)
        machine.accept_gesture("TILT_RIGHT")
        machine.accept_gesture("SHAKE")
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", (-1.20, 2.02))
        self.assertEqual(machine.state, TaskState.NAVIGATING)
        self.assertEqual(machine.route_finished(), "destination_reached")

    def test_travelling_nod_is_ignored_and_shake_still_stops(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(machine.accept_gesture("NOD"), ("ignored_gesture", None))
        self.assertEqual(machine.state, TaskState.NAVIGATING)
        self.assertEqual(machine.accept_gesture("SHAKE"), ("emergency_stop", None))
        self.assertEqual(machine.state, TaskState.STOPPED)
        self.assertIsNone(machine.pending_command)

    def test_latest_voice_destination_replaces_pending_midroute_override(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(machine.accept_command("go to B"), (True, "pending_confirmation"))
        self.assertEqual(machine.state, TaskState.PAUSED)
        self.assertEqual(machine.accept_command("go to C"), (True, "pending_confirmation"))
        self.assertEqual(machine.pending_command, "go to C")
        outcome, request = machine.accept_gesture("NOD", (-1.20, 2.02))
        self.assertEqual(outcome, "route_started")
        self.assertEqual(request.destination, "C")

    def test_reverse_requests_active_origin(self):
        machine = TaskMachine()
        machine.accept_command("start")
        machine.accept_command("go to A")
        machine.accept_gesture("NOD", WAYPOINTS["S"])
        self.assertEqual(machine.accept_command("reverse"), (True, "pending_confirmation"))
        self.assertEqual(machine.pending_command, "go to S")

    def test_stop_wins_while_paused(self):
        machine = TaskMachine()
        machine.accept_command("start A")
        machine.accept_gesture("TILT_LEFT")
        machine.accept_gesture("NOD")
        machine.accept_command("left")
        self.assertEqual(machine.accept_command("stop"), (True, "emergency_stop"))
        self.assertEqual(machine.state, TaskState.STOPPED)

    def test_expanded_command_vocabulary_is_bounded(self):
        accepted = {
            "start": "start",
            "forward": "forward",
            "reverse": "reverse",
            "turn left": "left",
            "turn right": "right",
            "go to s": "go to S",
            "alternative route": "alternative route",
        }
        for transcript, command in accepted.items():
            self.assertEqual(normalise_command(transcript), command)
        self.assertIsNone(normalise_command("turn around somewhere"))

    def test_expanded_vosk_transcriptions_use_confidence_boundary(self):
        for transcript in ("start", "go to a", "go to b", "go to s", "forward", "reverse", "left", "right", "continue", "alternative route", "stop"):
            words = [{"word": word, "conf": 0.82} for word in transcript.split()]
            payload = __import__("json").dumps({"text": transcript, "result": words})
            self.assertIsNotNone(parse_vosk_result(payload, confidence_threshold=0.65), transcript)
        low_confidence = __import__("json").dumps({"text": "go to a", "result": [{"word": "go", "conf": 0.64}]})
        self.assertIsNone(parse_vosk_result(low_confidence, confidence_threshold=0.65))


if __name__ == "__main__":
    unittest.main()
