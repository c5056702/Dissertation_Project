"""Derived tilt feedback must explain, without changing, recognition gates."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import GestureStateDetector


class TiltGateFeedbackTests(unittest.TestCase):
    def test_four_frame_tilt_at_moving_camera_rate_still_emits_once(self):
        for roll, expected in ((-0.3, "TILT_LEFT"), (0.3, "TILT_RIGHT")):
            with self.subTest(roll=roll):
                detector = GestureStateDetector()
                events = []
                for frame in range(12):
                    now = frame / 7.5
                    event = detector.update((roll, 0.0, 0.0), now)
                    if event:
                        events.append(event)
                    trace = detector.trace_status(now)
                    self.assertEqual(trace["tilt_direction"], expected)
                    self.assertEqual(trace["tilt_frames_required"], 4)
                    if frame < 3:
                        self.assertEqual(trace["tilt_gate"], "holding_tilt")
                        self.assertEqual(trace["tilt_frames"], frame + 1)
                    else:
                        self.assertEqual(trace["tilt_gate"], "waiting_for_neutral")
                        self.assertEqual(trace["tilt_frames"], 0)
                self.assertEqual(events, [expected])

    def test_armed_tilt_reports_pitch_yaw_or_both_without_accepting(self):
        for pitch, yaw, axes, gate in (
            (0.076, 0.0, ["pitch"], "pitch_outside_range"),
            (0.0, -0.101, ["yaw"], "yaw_outside_range"),
            (-0.076, 0.101, ["pitch", "yaw"], "pitch_outside_range"),
        ):
            for roll in (-0.3, 0.3):
                with self.subTest(pitch=pitch, yaw=yaw, roll=roll):
                    detector = GestureStateDetector()
                    for frame in range(8):
                        self.assertIsNone(detector.update((roll, pitch, yaw), frame / 7.5))
                    trace = detector.trace_status(1.0)
                    self.assertTrue(trace["armed"])
                    self.assertEqual(trace["tilt_gate"], gate)
                    self.assertEqual(trace["tilt_blocked_axes"], axes)
                    self.assertEqual(trace["tilt_frames"], 0)

    def test_existing_pitch_yaw_and_roll_boundaries_still_accept(self):
        detector = GestureStateDetector()
        pose = (detector.TILT_THRESHOLD, detector.TILT_MAX_PITCH, detector.TILT_MAX_YAW)
        for frame in range(3):
            self.assertIsNone(detector.update(pose, frame / 7.5))
            trace = detector.trace_status(frame / 7.5)
            self.assertEqual(trace["tilt_gate"], "holding_tilt")
            self.assertEqual(trace["tilt_blocked_axes"], [])
        self.assertEqual(detector.update(pose, 3 / 7.5), "TILT_RIGHT")

    def test_low_roll_and_post_nod_rearm_explain_different_gates(self):
        detector = GestureStateDetector()
        self.assertEqual(detector.trace_status(0.0)["tilt_gate"], "no_pose")
        detector.update((0.19, 0.0, 0.0), 0.0)
        trace = detector.trace_status(0.0)
        self.assertEqual(trace["tilt_gate"], "waiting_for_tilt")
        self.assertIsNone(trace["tilt_direction"])

        for frame in range(4):
            event = detector.update((0.0, 0.07, 0.0), 0.04 + frame * 0.04)
        self.assertEqual(event, "NOD")
        self.assertEqual(detector.trace_status(0.16)["tilt_gate"], "waiting_for_neutral")
        for frame in range(6):
            self.assertIsNone(detector.update((0.0, 0.0, 0.0), 0.2 + frame * 0.04))
        self.assertEqual(detector.trace_status(0.4)["tilt_gate"], "cooldown")
        self.assertIsNone(detector.update((0.3, 0.0, 0.0), 0.44))
        self.assertEqual(detector.trace_status(0.44)["tilt_gate"], "waiting_for_neutral")

        detector.face_lost()
        trace = detector.trace_status(1.0)
        self.assertEqual(trace["tilt_gate"], "no_pose")
        self.assertIsNone(trace["tilt_direction"])
        self.assertEqual(trace["tilt_blocked_axes"], [])
        for frame in range(6):
            self.assertIsNone(detector.update((0.0, 0.0, 0.0), 1.0 + frame * 0.04))
        self.assertEqual(detector.trace_status(1.2)["tilt_gate"], "waiting_for_tilt")
        self.assertTrue(detector.armed)


if __name__ == "__main__":
    unittest.main()
