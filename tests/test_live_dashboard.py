import unittest
from unittest.mock import patch

try:
    import cv2
    import numpy as np
except ImportError as error:  # Official headless Webots image deliberately omits GUI dependencies.
    raise unittest.SkipTest(f"Host dashboard rendering needs OpenCV and NumPy: {error}")

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(CONTROLLER))

from live_dashboard import DashboardAction, LiveTraceDashboard


def snapshot() -> dict:
    return {
        "session_id": "trace-session",
        "camera_ready": True,
        "voice_ready": True,
        "active_input_source": "MICROPHONE",
        "active_input_detail": "start A",
        "face_present": True,
        "gesture_trace": {
            "calibration_progress": 1.0,
            "pose": [-0.22, 0.03, -0.01],
            "face_box": [0.25, 0.15, 0.72, 0.86],
            "last_gesture": "TILT_LEFT",
            "candidate": None,
            "armed": False,
            "cooldown_remaining": 0.4,
        },
        "voice_decision": {"transcript": "start a", "command": "start A", "confidence": 0.91, "accepted": True, "reason": "accepted"},
        "state": "READY",
        "pending_command": "start A",
        "confirmation_required": True,
        "route": "S_A_SHORT",
        "origin": "S",
        "destination": "A",
        "position": [0.0, -2.0],
        "next_waypoint": [0.0, -1.0],
        "distance": 1.0,
        "sensor_peak": 125.0,
        "last_safety_stop": "clear",
    }


class ClosingCv:
    def __getattr__(self, name):
        return getattr(cv2, name)

    def namedWindow(self, *_args):
        pass

    def resizeWindow(self, *_args):
        pass

    def setMouseCallback(self, *_args):
        pass

    def imshow(self, *_args):
        pass

    def waitKey(self, *_args):
        return -1

    def getWindowProperty(self, *_args):
        return 0.0

    def destroyWindow(self, *_args):
        pass


class LiveDashboardTests(unittest.TestCase):
    def test_dashboard_renders_camera_and_placeholder(self):
        dashboard = LiveTraceDashboard(show_window=False)
        frame = np.full((480, 640, 3), (20, 80, 140), dtype=np.uint8)
        live = dashboard.render(snapshot(), frame)
        waiting = dashboard.render({**snapshot(), "camera_ready": False, "face_present": False}, None)
        self.assertEqual(live.shape, (760, 1280, 3))
        self.assertEqual(waiting.shape, live.shape)
        self.assertFalse(np.array_equal(live, waiting))

    def test_stop_and_reset_hitboxes_are_bounded(self):
        dashboard = LiveTraceDashboard(show_window=False)
        self.assertEqual(dashboard.handle_click(1050, 700), DashboardAction.STOP)
        self.assertEqual(dashboard.handle_click(1190, 700), DashboardAction.RESET)
        self.assertIsNone(dashboard.handle_click(900, 700))
        self.assertEqual(dashboard.poll_action(), DashboardAction.STOP)
        self.assertEqual(dashboard.poll_action(), DashboardAction.RESET)
        self.assertIsNone(dashboard.poll_action())

    def test_closed_window_queues_one_safety_stop(self):
        dashboard = LiveTraceDashboard(cv2_module=ClosingCv(), show_window=True)
        dashboard.update(snapshot(), np.zeros((30, 40, 3), dtype=np.uint8), force=True)
        self.assertTrue(dashboard.closed)
        self.assertEqual(dashboard.poll_action(), DashboardAction.STOP)
        dashboard.update(snapshot(), force=True)
        self.assertIsNone(dashboard.poll_action())

    def test_update_consumes_only_one_latest_frame_and_records_events(self):
        dashboard = LiveTraceDashboard(show_window=False)
        dashboard.record_event({"event": "command_recognised", "time": 1, "command": "start A"})
        dashboard.update(snapshot(), np.zeros((30, 40, 3), dtype=np.uint8), force=True)
        self.assertIsNone(dashboard._pending_frame)
        self.assertIn("command recognised", dashboard.events[0])
        self.assertIsNotNone(dashboard.mean_render_ms)
        self.assertLess(dashboard.mean_render_ms, 250.0)

    def test_next_step_instructions_follow_state_and_confirmation(self):
        ready = snapshot()
        ready["pending_command"] = None
        ready["confirmation_required"] = False
        ready["gesture_trace"] = {**ready["gesture_trace"], "armed": True, "cooldown_remaining": 0.0}
        self.assertIn("GO TO A, B, C, or S", LiveTraceDashboard.next_step_instruction(ready))

        moving = {**ready, "state": "NAVIGATING", "route": "GRAPH_S_A_SHORTEST", "destination": "A"}
        for mode in ("MICROPHONE", "CAMERA"):
            instruction = LiveTraceDashboard.next_step_instruction({**moving, "control_mode": mode})
            self.assertIn("TILT LEFT/RIGHT", instruction)
            self.assertIn("neutral, NOD", instruction)
            self.assertIn("SHAKE stops", instruction)
            self.assertIn("change destination", instruction)

        pending = {**moving, "state": "PAUSED", "pending_command": "go to B", "confirmation_required": True}
        self.assertIn("TO B: SHORTEST selected", LiveTraceDashboard.next_step_instruction(pending))
        self.assertIn("NOD to start", LiveTraceDashboard.next_step_instruction(pending))

        camera_pending = {**pending, "control_mode": "CAMERA", "active_input_source": "CAMERA"}
        self.assertIn("TO B: SHORTEST selected", LiveTraceDashboard.next_step_instruction(camera_pending))
        alternative = {**camera_pending, "route_choice": "alternative"}
        self.assertIn("TO B: ALTERNATIVE selected", LiveTraceDashboard.next_step_instruction(alternative))

        rearming = {**pending, "gesture_trace": {**pending["gesture_trace"], "armed": False, "cooldown_remaining": 0.5}}
        self.assertIn("re-arm", LiveTraceDashboard.next_step_instruction(rearming))

        stopped = {**ready, "state": "STOPPED", "last_safety_stop": "head_shake"}
        self.assertIn("remain still", LiveTraceDashboard.next_step_instruction(stopped))

        idle = {**ready, "state": "IDLE", "last_safety_stop": "clear"}
        self.assertIn("ROBOT LOCKED AT S", LiveTraceDashboard.next_step_instruction(idle))

        idle = {**ready, "state": "IDLE"}
        self.assertIn("say START", LiveTraceDashboard.next_step_instruction(idle))

    def test_rearm_guidance_applies_during_travel_and_pending_for_all_destinations(self):
        for destination in ("A", "B", "C", "S"):
            for state, pending in (("NAVIGATING", None), ("PAUSED", f"go to {destination}")):
                for axis, adjustment in (("roll", "straighten your head"), ("pitch", "level your chin"), ("yaw", "face the camera")):
                    with self.subTest(destination=destination, state=state, axis=axis):
                        current = {**snapshot(), "state": state, "pending_command": pending, "destination": destination}
                        current["gesture_trace"] = {**current["gesture_trace"], "neutral_axes_outside": [axis]}
                        self.assertIn(adjustment, LiveTraceDashboard.next_step_instruction(current))
                        if state == "NAVIGATING":
                            self.assertIn("Say STOP", LiveTraceDashboard.next_step_instruction(current))
                        current["state"] = "STOPPED"
                        self.assertIn("say START", LiveTraceDashboard.next_step_instruction(current))

    def test_partial_speech_does_not_hide_last_rejected_final(self):
        current = snapshot()
        current["voice_decision"] = {"transcript": "go to", "reason": "partial_transcript"}
        current["voice_final_decision"] = {
            "transcript": "go to a", "command": "go to A", "confidence": 0.4,
            "accepted": False, "reason": "low_confidence",
            "word_confidences": [{"word": "go", "confidence": 1.0}, {"word": "a", "confidence": 0.4}],
        }
        dashboard = LiveTraceDashboard(show_window=False)
        with patch.object(dashboard, "_draw_rows") as draw_rows:
            dashboard._draw_input_panel(np.zeros((760, 1280, 3), dtype=np.uint8), current)
        rows = {label: value for label, value, _color in draw_rows.call_args.args[1]}
        self.assertEqual(rows["Voice"], "hearing: go to")
        self.assertEqual(rows["Last speech"], "go to a")
        self.assertIn("Unclear 'a'", rows["Decision"])

    def test_armed_moving_tilt_reports_blocked_axis_or_incomplete_hold(self):
        moving = {**snapshot(), "state": "NAVIGATING", "pending_command": None}
        cases = (
            ("pitch_outside_range", ["pitch"], "chin at its starting height"),
            ("yaw_outside_range", ["yaw"], "keep looking toward the camera"),
            ("pitch_outside_range", ["pitch", "yaw"], "chin level and face the camera"),
            ("holding_tilt", [], "keep it steady until the robot pauses"),
        )
        for gate, axes, expected in cases:
            with self.subTest(gate=gate, axes=axes):
                moving["gesture_trace"] = {**moving["gesture_trace"], "armed": True,
                    "cooldown_remaining": 0.0, "tilt_gate": gate,
                    "tilt_blocked_axes": axes, "tilt_direction": "TILT_LEFT"}
                self.assertIn(expected, LiveTraceDashboard.next_step_instruction(moving))
        pending = {**moving, "state": "PAUSED", "pending_command": "go to A"}
        self.assertIn("route is selected", LiveTraceDashboard.next_step_instruction(pending))
        stopped = {**moving, "state": "STOPPED"}
        self.assertIn("say START", LiveTraceDashboard.next_step_instruction(stopped))
        moving["gesture_trace"] = {**moving["gesture_trace"], "tilt_gate": "waiting_for_tilt", "neutral_axes_outside": ["roll"]}
        self.assertIn("Tilt a little farther", LiveTraceDashboard.next_step_instruction(moving))

    def test_destination_and_choice_remain_visible_while_rearming(self):
        dashboard = LiveTraceDashboard(show_window=False)
        for destination in "ABCS":
            for choice in ("shortest", "alternative"):
                with self.subTest(destination=destination, choice=choice):
                    current = {**snapshot(), "state": "PAUSED", "pending_command": f"go to {destination}",
                               "pending_destination": destination, "pending_route_choice": choice,
                               "route_choice": choice, "active_destination": "C", "destination": destination,
                               "active_route_name": "GRAPH_S_C_SHORTEST", "route": None}
                    with patch.object(dashboard, "_draw_rows") as draw_rows:
                        dashboard._draw_robot_panel(np.zeros((760, 1280, 3), dtype=np.uint8), current)
                    rows = {label: value for label, value, _ in draw_rows.call_args.args[1]}
                    self.assertEqual(rows["Route status"], f"TO {destination}: {choice.upper()} - awaiting NOD")
                    self.assertIn("Previous route", rows)
                    current["gesture_trace"] = {**current["gesture_trace"], "armed": True, "cooldown_remaining": 0}
                    self.assertIn(f"TO {destination}: {choice.upper()} selected", dashboard.next_step_instruction(current))

    def test_route_selection_events_are_not_buried_by_pose_diagnostics(self):
        dashboard = LiveTraceDashboard(show_window=False)
        message = "TILT RIGHT -> TO B: ALTERNATIVE selected; awaiting NOD"
        dashboard.record_event({"event": "route_selection", "time": 1, "message": message,
                                "gesture": "TILT_RIGHT", "destination": "B",
                                "route_choice": "alternative", "selected": True})
        for _ in range(15):
            dashboard.record_event({"event": "gesture_detection_status", "time": 2, "tilt_gate": "waiting_for_neutral"})
        self.assertEqual(len(dashboard.events), 1)
        self.assertIn("T+00:01", dashboard.events[0])
        self.assertIn("TILT RIGHT", dashboard.events[0])
        self.assertIn("TO B: ALTERNATIVE", dashboard.events[0])
        self.assertNotIn("awaiting NOD", dashboard.events[0])

    def test_confirmed_alternative_replaces_stale_pending_headline_when_rendered(self):
        dashboard = LiveTraceDashboard(show_window=False)
        selection = "TILT RIGHT -> TO A: ALTERNATIVE selected; awaiting NOD"
        previous = {**snapshot(), "pending_command": "go to A", "route_choice": "alternative",
                    "last_route_selection": selection}
        dashboard._latest_snapshot = previous
        dashboard.record_event({"event": "route_selection", "time": 1, "message": selection,
                                "gesture": "TILT_RIGHT", "destination": "A",
                                "route_choice": "alternative", "selected": True})
        current = {**previous, "state": "NAVIGATING", "pending_command": None,
                   "confirmation_required": False, "active_destination": "A",
                   "active_route_choice": "alternative", "active_route_name": "GRAPH_S_A_ALTERNATIVE"}
        current["gesture_trace"] = {**current["gesture_trace"], "last_gesture": "NOD",
                                    "neutral_axes_outside": ["pitch"], "cooldown_remaining": 0.0}
        with patch.object(cv2, "putText", wraps=cv2.putText) as put_text:
            dashboard.render(current)
        displayed = [call.args[1] for call in put_text.call_args_list]
        self.assertIn("TO A: ALTERNATIVE - navigating", displayed)
        self.assertIn("Now: TO A: ALTERNATIVE - navigating", displayed)
        self.assertFalse(any("awaiting NOD" in text for text in displayed))
        self.assertFalse(any(text.startswith("Last tilt:") for text in displayed))
        self.assertTrue(any("T+00:01" in text and "TILT RIGHT" in text for text in displayed))
        next_step_lines = [call.args[1] for call in put_text.call_args_list
                           if call.args[2][0] == 700 and call.args[2][1] in (631, 654)]
        guidance = " ".join(next_step_lines)
        self.assertIn("Travelling to A.", guidance)
        self.assertIn("next gesture", guidance.lower())
        self.assertIn("level your chin", guidance)
        self.assertIn("Say STOP", guidance)
        self.assertLessEqual(len(next_step_lines), 2)
        self.assertTrue(all(len(line) <= 66 for line in next_step_lines))

    def test_route_status_follows_new_destination_pause_stop_and_arrival(self):
        active = {**snapshot(), "state": "NAVIGATING", "pending_command": None,
                  "confirmation_required": False, "active_destination": "A",
                  "active_route_choice": "alternative", "active_route_name": "GRAPH_S_A_ALTERNATIVE",
                  "last_route_selection": "TILT RIGHT -> TO A: ALTERNATIVE selected; awaiting NOD"}
        cases = (
            ({**active, "state": "PAUSED"}, "TO A: ALTERNATIVE - paused"),
            ({**active, "state": "PAUSED", "pending_command": "go to B",
              "pending_destination": "B", "pending_route_choice": "shortest"},
             "TO B: SHORTEST - awaiting NOD"),
            ({**active, "state": "ARRIVED", "current_location": "A", "active_destination": None},
             "AT A - arrived"),
            ({**active, "state": "AT_PICKUP", "current_location": "A"}, "AT A - arrived"),
            ({**active, "state": "AT_DROPOFF", "current_location": "C", "active_destination": "C"},
             "AT C - arrived"),
        )
        for current, expected in cases:
            with self.subTest(state=current["state"], pending=current.get("pending_command")):
                self.assertEqual(LiveTraceDashboard.selected_route_text(current), expected)
        for state in ("STOPPED", "IDLE"):
            with self.subTest(state=state):
                text = LiveTraceDashboard.selected_route_text({**active, "state": state})
                self.assertIn("START required", text)
                self.assertNotIn("ALTERNATIVE", text)
                self.assertNotIn("awaiting NOD", text)

        dashboard = LiveTraceDashboard(show_window=False)
        for state, destination in (("AT_PICKUP", "A"), ("AT_DROPOFF", "C")):
            with self.subTest(state=state):
                current = {**active, "state": state, "current_location": destination,
                           "active_destination": destination}
                with patch.object(dashboard, "_draw_rows") as draw_rows:
                    dashboard._draw_robot_panel(np.zeros((760, 1280, 3), dtype=np.uint8), current)
                rows = {label: value for label, value, _ in draw_rows.call_args.args[1]}
                self.assertNotIn("Active route", rows)
                self.assertIn("Last route", rows)


if __name__ == "__main__":
    unittest.main()
