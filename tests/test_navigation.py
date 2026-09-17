from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from navigation import WaypointNavigator


class Motor:
    def __init__(self):
        self.velocity = None

    def setVelocity(self, value):
        self.velocity = value


class Device:
    def __init__(self, values):
        self.values = values

    def getValues(self):
        return self.values


class Sensor:
    def __init__(self, value):
        self.value = value

    def getValue(self):
        return self.value


class NavigatorTests(unittest.TestCase):
    def make_navigator(self, gps=(0.0, 0.0, 0.0), compass=(1.0, 0.0, 0.0), sensor=0.0):
        left, right = Motor(), Motor()
        navigator = WaypointNavigator(left, right, Device(gps), Device(compass), [Sensor(sensor) for _ in range(8)])
        navigator.start([(0.0, 0.0), (0.0, 1.0)])
        return navigator, left, right

    def test_obstacle_stops_both_motors(self):
        navigator, left, right = self.make_navigator(sensor=5000.0)
        outcome, details = navigator.step()
        self.assertEqual(outcome, "obstacle")
        self.assertEqual(details["sensor_peak"], 5000.0)
        self.assertEqual((left.velocity, right.velocity), (0.0, 0.0))

    def test_lost_gps_stops_both_motors(self):
        navigator, left, right = self.make_navigator(gps=(math.nan, 0.0, 0.0))
        outcome, _ = navigator.step()
        self.assertEqual(outcome, "localisation_lost")
        self.assertEqual((left.velocity, right.velocity), (0.0, 0.0))

    def test_valid_navigation_commands_forward_motion(self):
        navigator, left, right = self.make_navigator()
        outcome, details = navigator.step()
        self.assertEqual(outcome, "moving")
        self.assertAlmostEqual(details["distance"], 1.0)
        self.assertGreater(left.velocity, 0.0)
        self.assertGreater(right.velocity, 0.0)


if __name__ == "__main__":
    unittest.main()
