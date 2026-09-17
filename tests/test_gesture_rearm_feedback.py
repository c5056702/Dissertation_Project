"""Explain repeat-gesture readiness without relaxing the recognition gates."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import GestureStateDetector


class GestureRearmFeedbackTests(unittest.TestCase):
    @staticmethod
    def emit_tilt(detector):
        for index in range(3):
            assert detector.update((0.25, 0.0, 0.0), index * 0.04) is None
        return detector.update((0.25, 0.0, 0.0), 0.12)

    def test_blocking_axis_is_reported_until_full_neutral_hold(self):
        for axis, pose in (
            ("roll", (0.11, 0.0, 0.0)),
            ("pitch", (0.0, 0.03, 0.0)),
            ("yaw", (0.0, 0.0, 0.041)),
        ):
            with self.subTest(axis=axis):
                detector = GestureStateDetector()
                self.assertEqual(self.emit_tilt(detector), "TILT_RIGHT")
                for index in range(10):
                    self.assertIsNone(detector.update(pose, 1.0 + index * 0.04))
                trace = detector.trace_status(now=1.4)
                self.assertEqual(trace["neutral_axes_outside"], [axis])
                self.assertEqual(trace["neutral_frames"], 0)
                self.assertEqual(trace["cooldown_remaining"], 0.0)
                self.assertFalse(trace["armed"])

                for index in range(5):
                    self.assertIsNone(detector.update((0.0, 0.0, 0.0), 1.4 + index * 0.04))
                trace = detector.trace_status(now=1.6)
                self.assertEqual(trace["neutral_axes_outside"], [])
                self.assertEqual(trace["neutral_frames"], 5)
                self.assertEqual(trace["neutral_frames_required"], 6)
                self.assertFalse(trace["armed"])
                self.assertIsNone(detector.update((0.0, 0.0, 0.0), 1.64))
                self.assertTrue(detector.trace_status(now=1.64)["armed"])

    def test_neutral_progress_distinguishes_cooldown_and_face_loss(self):
        detector = GestureStateDetector()
        self.assertEqual(self.emit_tilt(detector), "TILT_RIGHT")
        for index in range(10):
            self.assertIsNone(detector.update((0.0, 0.0, 0.0), 0.16 + index * 0.04))
        trace = detector.trace_status(now=0.52)
        self.assertEqual(trace["neutral_frames"], 6)
        self.assertEqual(trace["neutral_axes_outside"], [])
        self.assertGreater(trace["cooldown_remaining"], 0.0)
        self.assertFalse(trace["armed"])

        detector.face_lost()
        trace = detector.trace_status(now=1.0)
        self.assertIsNone(trace["neutral_axes_outside"])
        self.assertEqual(trace["neutral_frames"], 0)
        self.assertFalse(trace["armed"])
        self.assertFalse(trace["shake_armed"])


if __name__ == "__main__":
    unittest.main()
