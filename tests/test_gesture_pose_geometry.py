"""Synthetic face geometry checks; no camera frames or client poses are used."""

import math
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import GestureStateDetector, MediaPipeGestureRecognizer


class GesturePoseGeometryTests(unittest.TestCase):
    @staticmethod
    def recognizer(resolution=(640, 480)):
        recognizer = MediaPipeGestureRecognizer.__new__(MediaPipeGestureRecognizer)
        recognizer.resolution = resolution
        return recognizer

    @staticmethod
    def landmarks(resolution, roll=0.0, pitch=0.25, yaw=0.0):
        # Build a symmetric face in equal horizontal/vertical image units,
        # rotate it as one rigid shape, then normalize as MediaPipe does.
        width, height = resolution
        aspect_y = height / width
        jaw_width = 0.40
        points = {
            33: (-0.15, 0.0),
            263: (0.15, 0.0),
            1: (yaw * jaw_width, pitch * jaw_width * aspect_y),
            234: (-jaw_width / 2, 0.15),
            454: (jaw_width / 2, 0.15),
        }
        landmarks = [SimpleNamespace(x=0.5, y=0.4) for _ in range(455)]
        cosine, sine = math.cos(roll), math.sin(roll)
        for index, (x, y) in points.items():
            landmarks[index] = SimpleNamespace(
                x=0.5 + x * cosine - y * sine,
                y=0.4 + (x * sine + y * cosine) / aspect_y,
            )
        return landmarks

    def pose(self, recognizer, **kwargs):
        return recognizer._pose(self.landmarks(recognizer.resolution, **kwargs))

    def test_upright_pitch_and_yaw_keep_the_existing_scale(self):
        for resolution in ((640, 480), (1280, 720), (480, 640)):
            for pitch, yaw in ((0.25, 0.0), (0.32, 0.0), (0.25, -0.08), (0.25, 0.08)):
                with self.subTest(resolution=resolution, pitch=pitch, yaw=yaw):
                    pose = self.pose(self.recognizer(resolution), pitch=pitch, yaw=yaw)
                    for actual, expected in zip(pose, (0.0, pitch, yaw)):
                        self.assertAlmostEqual(actual, expected)

    def test_roll_is_measured_in_image_space_without_creating_yaw(self):
        for resolution in ((640, 480), (1280, 720), (480, 640), (640, 640)):
            recognizer = self.recognizer(resolution)
            for roll in (-0.55, -0.25, 0.25, 0.55):
                with self.subTest(resolution=resolution, roll=roll):
                    pose = self.pose(recognizer, roll=roll)
                    self.assertAlmostEqual(pose[0], roll)
                    self.assertAlmostEqual(pose[1], 0.25)
                    self.assertAlmostEqual(pose[2], 0.0)

    def test_large_pure_roll_still_emits_tilt_both_ways(self):
        recognizer = self.recognizer()
        neutral = self.pose(recognizer)
        for roll, expected in ((-0.55, "TILT_LEFT"), (0.55, "TILT_RIGHT")):
            with self.subTest(roll=roll):
                measured = self.pose(recognizer, roll=roll)
                relative = tuple(value - baseline for value, baseline in zip(measured, neutral))
                detector = GestureStateDetector()
                events = []
                for frame in range(4):
                    event = detector.update(relative, frame * 0.04)
                    if event:
                        events.append(event)
                self.assertEqual(events, [expected])

    def test_real_pitch_and_yaw_are_preserved_with_roll(self):
        recognizer = self.recognizer()
        for roll in (-0.4, 0.4):
            for pitch, yaw in ((0.32, 0.0), (0.25, -0.08), (0.25, 0.08)):
                with self.subTest(roll=roll, pitch=pitch, yaw=yaw):
                    pose = self.pose(recognizer, roll=roll, pitch=pitch, yaw=yaw)
                    self.assertAlmostEqual(pose[1], pitch)
                    self.assertAlmostEqual(pose[2], yaw)

    def test_tilt_nod_rearm_and_shake_after_offset_neutral_calibration(self):
        recognizer = self.recognizer()
        for neutral_roll in (-0.3, 0.0, 0.3):
            with self.subTest(neutral_roll=neutral_roll):
                neutral = self.pose(recognizer, roll=neutral_roll)
                detector = GestureStateDetector()
                events = []
                frame = 0

                def feed(count, roll=0.0, pitch=0.25, yaw=0.0):
                    nonlocal frame
                    measured = self.pose(recognizer, roll=neutral_roll + roll, pitch=pitch, yaw=yaw)
                    relative = tuple(value - baseline for value, baseline in zip(measured, neutral))
                    for _ in range(count):
                        event = detector.update(relative, frame * 0.04)
                        if event:
                            events.append(event)
                        frame += 1

                for roll in (0.55, 0.55, -0.55):
                    feed(4, roll=roll)
                    feed(25)
                    feed(4, pitch=0.32)
                    feed(25)
                feed(1, yaw=-0.08)
                feed(1, yaw=0.08)
                self.assertEqual(events, ["TILT_RIGHT", "NOD", "TILT_RIGHT", "NOD", "TILT_LEFT", "NOD", "SHAKE"])


if __name__ == "__main__":
    unittest.main()
