from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import GestureStateDetector, classify_pose_history, parse_vosk_result


class InputAdapterLogicTests(unittest.TestCase):
    @staticmethod
    def feed(detector, poses, start=0.0, step=0.04):
        events = []
        for index, pose in enumerate(poses):
            gesture = detector.update(pose, start + index * step)
            if gesture:
                events.append(gesture)
        return events

    def test_vosk_result_accepts_bounded_high_confidence_command(self):
        payload = json.dumps({"text": "start a", "result": [{"word": "start", "conf": 0.91}, {"word": "a", "conf": 0.88}]})
        self.assertEqual(parse_vosk_result(payload), "start A")

    def test_vosk_result_rejects_low_confidence_and_unbounded_text(self):
        low = json.dumps({"text": "return", "result": [{"word": "return", "conf": 0.4}]})
        unknown = json.dumps({"text": "drive away", "result": [{"word": "drive", "conf": 0.99}]})
        self.assertIsNone(parse_vosk_result(low))
        self.assertIsNone(parse_vosk_result(unknown))

    def test_standalone_start_uses_safe_activation_threshold_without_movement(self):
        start = json.dumps({"text": "start", "result": [{"word": "start", "conf": 0.55}]})
        movement = json.dumps({"text": "return", "result": [{"word": "return", "conf": 0.55}]})
        self.assertEqual(parse_vosk_result(start), "start")
        self.assertIsNone(parse_vosk_result(movement))

    def test_smoothed_head_pose_classification(self):
        self.assertEqual(classify_pose_history([(-0.25, 0.0, 0.0)] * 8), "TILT_LEFT")
        self.assertEqual(classify_pose_history([(0.25, 0.0, 0.0)] * 8), "TILT_RIGHT")
        self.assertEqual(classify_pose_history([(0.0, -0.04, 0.0), (0.0, 0.04, 0.0)] * 4), "NOD")
        self.assertEqual(classify_pose_history([(0.0, 0.0, -0.05), (0.0, 0.0, 0.05)] * 4), "SHAKE")
        self.assertIsNone(classify_pose_history([(0.01, 0.01, 0.01)] * 8))

    def test_held_tilt_emits_once_and_rearms_after_neutral(self):
        detector = GestureStateDetector(cooldown_seconds=0.2)
        first = self.feed(detector, [(-0.25, 0.0, 0.0)] * 30)
        neutral = self.feed(detector, [(0.0, 0.0, 0.0)] * 10, start=1.2)
        second = self.feed(detector, [(0.25, 0.0, 0.0)] * 12, start=1.6)
        self.assertEqual(first, ["TILT_LEFT"])
        self.assertEqual(neutral, [])
        self.assertEqual(second, ["TILT_RIGHT"])

    def test_nod_requires_sustained_pitch_and_emits_once(self):
        detector = GestureStateDetector(cooldown_seconds=0.2)
        poses = [(0.0, 0.07, 0.0)] * 6 + [(0.0, 0.0, 0.0)] * 8
        self.assertEqual(self.feed(detector, poses), ["NOD"])

    def test_shake_requires_both_yaw_directions(self):
        detector = GestureStateDetector(cooldown_seconds=0.2)
        poses = [(0.0, 0.0, -0.08)] * 5 + [(0.0, 0.0, 0.08)] * 5
        self.assertEqual(self.feed(detector, poses), ["SHAKE"])

    def test_single_head_turn_is_not_a_shake(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                detector = GestureStateDetector(cooldown_seconds=0.2)
                # The one-sided excursion exceeds the shake span threshold,
                # including the return to neutral, without becoming a shake.
                yaws = [0.0, 0.04, 0.08, 0.12, 0.16, 0.12, 0.08, 0.04, 0.0]
                poses = [(0.0, 0.0, direction * yaw) for yaw in yaws]
                self.assertEqual(self.feed(detector, poses), [])
                self.assertIsNone(classify_pose_history(poses))
                self.assertIsNone(detector.trace_status(now=0.4)["candidate"])

    def test_shake_detects_either_order_of_two_sided_motion(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                detector = GestureStateDetector(cooldown_seconds=0.2)
                poses = [(0.0, 0.0, direction * yaw) for yaw in (0.0, 0.04, 0.08, 0.0, -0.04, -0.08)]
                self.assertEqual(self.feed(detector, poses), ["SHAKE"])
                self.assertEqual(classify_pose_history(poses), "SHAKE")

    def test_neutral_and_small_yaw_noise_are_not_shake_candidates(self):
        for yaws in ([0.0] * 20, [-0.02, 0.02] * 10):
            with self.subTest(yaws=yaws):
                detector = GestureStateDetector(cooldown_seconds=0.2)
                self.assertEqual(self.feed(detector, [(0.0, 0.0, yaw) for yaw in yaws]), [])
                self.assertIsNone(detector.trace_status(now=1.0)["candidate"])

    def test_shake_rearms_only_after_neutral_and_cooldown(self):
        detector = GestureStateDetector(cooldown_seconds=0.8)
        shake = [(0.0, 0.0, -0.08), (0.0, 0.0, 0.08)]
        self.assertEqual(self.feed(detector, shake), ["SHAKE"])
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 6, start=0.08), [])
        self.assertFalse(detector.shake_armed)
        self.assertEqual(self.feed(detector, shake * 5, start=0.32), [])
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 6, start=1.0), [])
        self.assertTrue(detector.shake_armed)
        self.assertEqual(self.feed(detector, shake, start=1.24), ["SHAKE"])

    def test_shake_keeps_priority_while_tilt_detector_waits_for_neutral(self):
        detector = GestureStateDetector(cooldown_seconds=0.2)
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 4), ["TILT_RIGHT"])
        self.assertFalse(detector.armed)
        shake = [(0.0, 0.0, -0.08), (0.0, 0.0, 0.08)]
        self.assertEqual(self.feed(detector, shake, start=0.5), ["SHAKE"])

    def test_repeated_route_tilts_and_nods_rearm_with_default_cooldown(self):
        for rolls in ((0.25, 0.25, 0.25), (-0.25, -0.25, -0.25), (0.25, -0.25, 0.25)):
            with self.subTest(rolls=rolls):
                detector = GestureStateDetector()
                poses = []
                expected = []
                for roll in rolls:
                    poses += [(roll, 0.0, 0.0)] * 4
                    poses += [(0.0, 0.0, 0.0)] * 25
                    poses += [(0.0, 0.07, 0.0)] * 4
                    poses += [(0.0, 0.0, 0.0)] * 25
                    expected += ["TILT_RIGHT" if roll > 0 else "TILT_LEFT", "NOD"]
                self.assertEqual(self.feed(detector, poses), expected)
                self.assertTrue(detector.armed)

    def test_second_tilt_waits_for_complete_neutral_hold(self):
        detector = GestureStateDetector()
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 4), ["TILT_RIGHT"])
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 5, start=1.0), [])
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 8, start=1.2), [])
        self.assertFalse(detector.armed)
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 6, start=1.6), [])
        self.assertTrue(detector.armed)
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 4, start=1.84), ["TILT_RIGHT"])

    def test_face_loss_recovers_for_repeated_tilt_nod_with_default_cooldown(self):
        detector = GestureStateDetector()
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 4), ["TILT_RIGHT"])
        detector.face_lost()
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 8, start=0.16), [])
        self.assertFalse(detector.armed)
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 25, start=0.5), [])
        self.assertTrue(detector.armed)
        self.assertTrue(detector.shake_armed)
        self.assertEqual(self.feed(detector, [(0.0, 0.07, 0.0)] * 4, start=1.5), ["NOD"])
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 25, start=1.7), [])
        self.assertEqual(self.feed(detector, [(0.25, 0.0, 0.0)] * 4, start=2.7), ["TILT_RIGHT"])

    def test_face_loss_discards_incomplete_motion(self):
        detector = GestureStateDetector(cooldown_seconds=0.2)
        self.assertEqual(self.feed(detector, [(0.0, 0.0, -0.08)] * 5), [])
        detector.face_lost()
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.08)] * 5, start=1.0), [])
        self.assertFalse(detector.shake_armed)
        self.assertEqual(self.feed(detector, [(0.0, 0.0, 0.0)] * 6, start=1.2), [])
        self.assertTrue(detector.shake_armed)
        self.assertEqual(self.feed(detector, [(0.0, 0.0, -0.08), (0.0, 0.0, 0.08)], start=1.5), ["SHAKE"])


if __name__ == "__main__":
    unittest.main()
