"""GPS/compass waypoint navigator used by the real Webots controller."""

from __future__ import annotations

import math
from collections.abc import Sequence

from model import Point


def wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class WaypointNavigator:
    def __init__(self, left_motor, right_motor, gps, compass, proximity_sensors) -> None:
        self.left_motor = left_motor
        self.right_motor = right_motor
        self.gps = gps
        self.compass = compass
        self.proximity_sensors = proximity_sensors
        self.points: list[Point] = []
        self.index = 0
        self.max_speed = 6.0
        self.tolerance = 0.09
        # The e-puck's infrared readings are high when an object is extremely
        # close. The start marker is intentionally near the boundary wall, so
        # use a conservative threshold that does not treat normal corridor
        # clearance as a collision hazard.
        self.obstacle_threshold = 4050.0
        self.maximum_sensor_peak = 0.0
        self.actual_path_length = 0.0
        self._last_position: Point | None = None
        self.force_localisation_loss = False

    def start(self, points: Sequence[Point]) -> None:
        self.points = list(points)[1:]
        self.index = 0
        if self._last_position is None:
            self._last_position = self.position()

    def stop(self) -> None:
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

    def position(self) -> Point:
        values = self.gps.getValues()
        return float(values[0]), float(values[1])

    def step(self) -> tuple[str, dict[str, float | int | Point]]:
        readings = [float(sensor.getValue()) for sensor in self.proximity_sensors]
        maximum = max(readings) if readings else 0.0
        self.maximum_sensor_peak = max(self.maximum_sensor_peak, maximum)
        position = self.position()
        north = self.compass.getValues()
        localisation_values = (*position, *(float(value) for value in north))
        if self.force_localisation_loss or not all(math.isfinite(value) for value in localisation_values):
            self.stop()
            return "localisation_lost", {"position": position}
        if self._last_position is not None:
            self.actual_path_length += math.dist(self._last_position, position)
        self._last_position = position
        if maximum >= self.obstacle_threshold:
            self.stop()
            return "obstacle", {
                "sensor_peak": maximum,
                "sensor_index": readings.index(maximum),
                "position": position,
            }
        if self.index >= len(self.points):
            self.stop()
            return "complete", {"position": self.position()}
        target = self.points[self.index]
        distance = math.dist(position, target)
        if distance <= self.tolerance:
            self.index += 1
            if self.index >= len(self.points):
                self.stop()
                return "complete", {"position": position}
            return "waypoint", {"position": position, "index": self.index}
        # The e-puck moves along local +x. In Webots' ENU world, the compass
        # returns global north (+y) in robot coordinates.
        heading = wrap_angle(math.pi / 2 - math.atan2(float(north[1]), float(north[0])))
        desired = math.atan2(target[1] - position[1], target[0] - position[0])
        error = wrap_angle(desired - heading)
        turn = max(-2.8, min(2.8, 3.2 * error))
        forward = self.max_speed * max(0.15, 1.0 - min(abs(error) / 1.4, 0.85))
        self.left_motor.setVelocity(max(-self.max_speed, min(self.max_speed, forward - turn)))
        self.right_motor.setVelocity(max(-self.max_speed, min(self.max_speed, forward + turn)))
        return "moving", {
            "position": position,
            "target": target,
            "distance": distance,
            "heading": heading,
            "desired_heading": desired,
            "heading_error": error,
            "compass": [float(value) for value in north],
        }
