"""Pure task, command, and route model used by Webots and offline tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import heapq
import math
from typing import Iterable, Sequence


Point = tuple[float, float]

WAYPOINTS: dict[str, Point] = {
    "S": (-2.55, 2.05),
    "A": (2.25, 1.95),
    "B": (-2.20, -2.05),
    "C": (2.25, -2.05),
}

# Canonical physical corridors. Reverse traversal is generated from these
# definitions so the two directions cannot drift apart.
ROUTES: dict[str, list[Point]] = {
    "S_A_SHORT": [WAYPOINTS["S"], (-1.20, 2.02), (1.10, 2.00), WAYPOINTS["A"]],
    "S_A_LONG": [WAYPOINTS["S"], (-2.55, 1.20), (-0.95, 1.20), (1.20, 1.20), WAYPOINTS["A"]],
    "A_C": [WAYPOINTS["A"], WAYPOINTS["C"]],
    "A_B": [WAYPOINTS["A"], (1.20, 1.20), (-0.95, 1.20), (-0.95, -0.80), (-1.05, -0.80), WAYPOINTS["B"]],
    "B_C": [WAYPOINTS["B"], (-0.80, -2.05), (0.80, -2.05), WAYPOINTS["C"]],
}
ROUTES.update(
    {
        "C_A": list(reversed(ROUTES["A_C"])),
        "B_A": list(reversed(ROUTES["A_B"])),
        "C_B": list(reversed(ROUTES["B_C"])),
    }
)


class TaskState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    NAVIGATING = "NAVIGATING"
    TO_PICKUP = "TO_PICKUP"
    AT_PICKUP = "AT_PICKUP"
    TO_DROPOFF = "TO_DROPOFF"
    AT_DROPOFF = "AT_DROPOFF"
    TO_RETURN = "TO_RETURN"
    PAUSED = "PAUSED"
    ARRIVED = "ARRIVED"
    STOPPED = "STOPPED"


@dataclass(frozen=True)
class RouteRequest:
    name: str
    points: tuple[Point, ...]
    segment_ids: tuple[str, ...] = ()
    origin: str | None = None
    destination: str | None = None
    alternative: bool = False


@dataclass(frozen=True)
class _GraphEdge:
    start: Point
    end: Point
    cost: float
    route_ids: tuple[str, ...]


def route_length(points: Iterable[Point]) -> float:
    points = list(points)
    return sum(math.dist(points[index - 1], points[index]) for index in range(1, len(points)))


def _segment_key(start: Point, end: Point) -> tuple[Point, Point]:
    return tuple(sorted((start, end)))  # type: ignore[return-value]


class RouteGraph:
    """Undirected route graph with measured current-position insertion."""

    MAX_CURRENT_DISTANCE = 0.60

    def __init__(self) -> None:
        segments: dict[tuple[Point, Point], set[str]] = {}
        for route_name in ("S_A_SHORT", "S_A_LONG", "A_C", "A_B", "B_C"):
            points = ROUTES[route_name]
            for start, end in zip(points, points[1:]):
                segments.setdefault(_segment_key(start, end), set()).add(route_name)
        self.edges = [
            _GraphEdge(start, end, math.dist(start, end), tuple(sorted(route_ids)))
            for (start, end), route_ids in segments.items()
        ]

    @staticmethod
    def _node_id(point: Point) -> str:
        return f"{point[0]:.6f},{point[1]:.6f}"

    @staticmethod
    def _project(point: Point, start: Point, end: Point) -> tuple[Point, float]:
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return start, 0.0
        factor = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
        factor = max(0.0, min(1.0, factor))
        return (start[0] + factor * dx, start[1] + factor * dy), factor

    def _adjacency(self, current: Point) -> tuple[dict[str, list[tuple[str, float, tuple[Point, ...], tuple[str, ...]]]], str]:
        adjacency: dict[str, list[tuple[str, float, tuple[Point, ...], tuple[str, ...]]]] = {}

        def add(start: Point, end: Point, points: Sequence[Point], cost: float, route_ids: tuple[str, ...]) -> None:
            start_id, end_id = self._node_id(start), self._node_id(end)
            adjacency.setdefault(start_id, []).append((end_id, cost, tuple(points), route_ids))

        for edge in self.edges:
            add(edge.start, edge.end, (edge.start, edge.end), edge.cost, edge.route_ids)
            add(edge.end, edge.start, (edge.end, edge.start), edge.cost, edge.route_ids)

        for waypoint in WAYPOINTS.values():
            if math.dist(current, waypoint) <= 0.10:
                return adjacency, self._node_id(waypoint)

        nearest_edge: _GraphEdge | None = None
        nearest_projection: Point | None = None
        nearest_distance = float("inf")
        for edge in self.edges:
            projection, _ = self._project(current, edge.start, edge.end)
            distance = math.dist(current, projection)
            if distance < nearest_distance:
                nearest_edge = edge
                nearest_projection = projection
                nearest_distance = distance
        if nearest_edge is None or nearest_projection is None or nearest_distance > self.MAX_CURRENT_DISTANCE:
            raise ValueError("current_position_outside_route_network")

        # Insert the projection into the physical edge. Keeping the unsplit
        # edge would let a supposed alternative retrace the current position
        # and then follow the shortest path in the opposite direction.
        projection = nearest_projection
        for endpoint in (nearest_edge.start, nearest_edge.end):
            if math.dist(projection, endpoint) <= 1e-6:
                projection = endpoint
                break
        else:
            start_id, end_id = self._node_id(nearest_edge.start), self._node_id(nearest_edge.end)
            adjacency[start_id] = [entry for entry in adjacency[start_id] if entry[0] != end_id]
            adjacency[end_id] = [entry for entry in adjacency[end_id] if entry[0] != start_id]
            for endpoint in (nearest_edge.start, nearest_edge.end):
                cost = math.dist(projection, endpoint)
                add(projection, endpoint, (projection, endpoint), cost, nearest_edge.route_ids)
                add(endpoint, projection, (endpoint, projection), cost, nearest_edge.route_ids)
        source_id = self._node_id(projection)
        if math.dist(current, projection) > 1e-6:
            adjacency["__CURRENT__"] = [(source_id, math.dist(current, projection), (current, projection), ())]
            source_id = "__CURRENT__"
        return adjacency, source_id

    @staticmethod
    def _enumerate_paths(
        adjacency: dict[str, list[tuple[str, float, tuple[Point, ...], tuple[str, ...]]]],
        source: str,
        target: str,
        limit: int = 8,
    ) -> list[tuple[float, tuple[Point, ...], tuple[str, ...]]]:
        queue: list[tuple[float, int, str, frozenset[str], tuple[Point, ...], tuple[str, ...]]] = []
        heapq.heappush(queue, (0.0, 0, source, frozenset({source}), (), ()))
        serial = 0
        results: list[tuple[float, tuple[Point, ...], tuple[str, ...]]] = []
        signatures: set[tuple[Point, ...]] = set()
        while queue and len(results) < limit:
            cost, _, node, visited, points, route_ids = heapq.heappop(queue)
            if node == target:
                signature = tuple((round(point[0], 4), round(point[1], 4)) for point in points)
                if signature not in signatures:
                    signatures.add(signature)
                    results.append((cost, points, tuple(dict.fromkeys(route_ids))))
                continue
            for next_node, edge_cost, edge_points, edge_route_ids in adjacency.get(node, []):
                if next_node in visited:
                    continue
                combined = list(points)
                if not combined:
                    combined.extend(edge_points)
                else:
                    combined.extend(edge_points[1:] if combined[-1] == edge_points[0] else edge_points)
                serial += 1
                heapq.heappush(
                    queue,
                    (
                        cost + edge_cost,
                        serial,
                        next_node,
                        visited | {next_node},
                        tuple(combined),
                        tuple(dict.fromkeys((*route_ids, *edge_route_ids))),
                    ),
                )
        return results

    def _display_route_ids(self, points: Sequence[Point]) -> tuple[str, ...]:
        """Return canonical route identities used by a computed point path.

        Some physical graph edges belong to more than one canonical route
        (notably the horizontal section shared by S-A-long and A-B). Those
        memberships are useful for connectivity, but reporting every member
        would name an unrelated route. A route earns an identity only when the
        selected path traverses one of its unique edges; shared memberships are
        retained only as a defensive fallback. These IDs feed status/logging;
        the world intentionally contains no floor route geometry.
        """
        unique_ids: set[str] = set()
        shared_ids: set[str] = set()
        for start, end in zip(points, points[1:]):
            if math.dist(start, end) <= 1e-9:
                continue
            for edge in self.edges:
                start_projection, _ = self._project(start, edge.start, edge.end)
                end_projection, _ = self._project(end, edge.start, edge.end)
                if math.dist(start, start_projection) > 1e-5 or math.dist(end, end_projection) > 1e-5:
                    continue
                if len(edge.route_ids) == 1:
                    unique_ids.add(edge.route_ids[0])
                else:
                    shared_ids.update(edge.route_ids)
                break
        return tuple(sorted(unique_ids or shared_ids))

    def plan(self, current: Point, destination: str, alternative: bool = False) -> RouteRequest:
        destination = destination.upper()
        if destination not in WAYPOINTS:
            raise ValueError("unknown_destination")
        if math.dist(current, WAYPOINTS[destination]) <= 0.10:
            if alternative:
                raise ValueError("already_at_destination")
            return RouteRequest(
                f"GRAPH_{destination}_{destination}_ARRIVED",
                (current,),
                (),
                destination,
                destination,
                alternative,
            )
        adjacency, source_id = self._adjacency(current)
        target_id = self._node_id(WAYPOINTS[destination])
        paths = self._enumerate_paths(adjacency, source_id, target_id)
        if not paths:
            raise ValueError("no_route_available")
        if alternative and len(paths) < 2:
            raise ValueError("alternative_route_unavailable")
        selected_index = 1 if alternative else 0
        _, points, _ = paths[selected_index]
        if not points or math.dist(points[0], current) > 1e-6:
            points = (current, *points)
        route_ids = self._display_route_ids(points)
        origin = min(WAYPOINTS, key=lambda name: math.dist(current, WAYPOINTS[name]))
        mode = "ALTERNATIVE" if selected_index else "SHORTEST"
        return RouteRequest(
            f"GRAPH_{origin}_{destination}_{mode}",
            points,
            route_ids,
            origin,
            destination,
            bool(selected_index),
        )


ROUTE_GRAPH = RouteGraph()


def normalise_command(text: str) -> str | None:
    """Map recogniser output to the intentionally bounded command grammar."""
    compact = " ".join(text.lower().strip().split())
    aliases = {
        "start": "start",
        "activate": "start",
        "start a": "start A",
        "start b": "start B",
        "pickup": "pickup",
        "pick up": "pickup",
        "drop off": "drop off",
        "dropoff": "drop off",
        "return": "return",
        "stop": "stop",
        "go to a": "go to A",
        "go to alpha": "go to A",
        "goto a": "go to A",
        "go to b": "go to B",
        "goto b": "go to B",
        "go to c": "go to C",
        "goto c": "go to C",
        "go to s": "go to S",
        "goto s": "go to S",
        "forward": "forward",
        "continue": "continue",
        "continue route": "continue",
        "reverse": "reverse",
        "left": "left",
        "turn left": "left",
        "right": "right",
        "turn right": "right",
        "alternative": "alternative route",
        "alternative route": "alternative route",
        "change route": "alternative route",
    }
    return aliases.get(compact)


def live_startup_gate(command: str, state: TaskState) -> str | None:
    """Make physical live startup activation-only and tolerant of Vosk suffixes.

    With the bounded grammar, a short spoken ``start`` can occasionally be
    finalised as ``start a`` or ``start b``. At the live startup gate those
    variants must never select a destination. They are safely reduced to the
    stationary standalone START action. Once active, their legacy meanings are
    preserved.
    """
    normalised = normalise_command(command)
    if state in {TaskState.IDLE, TaskState.STOPPED} and normalised in {"start", "start A", "start B"}:
        return "start"
    return normalised


class TaskMachine:
    """State-valid fusion of task, point-to-point, and intervention commands."""

    MOVING_STATES = {TaskState.NAVIGATING, TaskState.TO_PICKUP, TaskState.TO_DROPOFF, TaskState.TO_RETURN}

    def __init__(self) -> None:
        self.state = TaskState.IDLE
        self.pending_command: str | None = None
        self.destination: str | None = None
        self.route_choice: str | None = None
        self.pickup_confirmed = False
        self.current_location = "S"
        self.active_origin: str | None = None
        self.active_destination: str | None = None
        self.active_mode: str | None = None
        self.paused_from_state: TaskState | None = None
        self.pending_route_state: TaskState | None = None
        self.clarification_direction: str | None = None

    def reset(self, *, activated: bool = True, stopped: bool = False) -> None:
        self.state = TaskState.STOPPED if stopped else (TaskState.READY if activated else TaskState.IDLE)
        self.pending_command = None
        self.destination = None
        self.route_choice = None
        self.pickup_confirmed = False
        self.active_origin = None
        self.active_destination = None
        self.active_mode = None
        self.paused_from_state = None
        self.pending_route_state = None
        self.clarification_direction = None

    def _pause(self, direction: str | None = None) -> None:
        if self.state in self.MOVING_STATES:
            self.paused_from_state = self.state
        self.state = TaskState.PAUSED
        self.clarification_direction = direction

    @staticmethod
    def _command_destination(command: str) -> str | None:
        return command[-1] if command.startswith("go to ") else None

    def accept_command(self, command: str) -> tuple[bool, str]:
        command = normalise_command(command) or ""
        # Repeating the same pending request is a reminder, not a new route
        # choice. Keep an explicit tilt and its legacy task continuation.
        if command.startswith("go to ") and command == self.pending_command:
            return True, "pending_confirmation"
        # Spoken replacements use their normal task/destination semantics.
        self.pending_route_state = None
        if command == "stop":
            self.reset(activated=False, stopped=True)
            return True, "emergency_stop"
        if command == "start":
            if self.state in {TaskState.IDLE, TaskState.STOPPED}:
                self.state = TaskState.READY
                return True, "activated"
            return True, "already_active"

        # Destination-bearing legacy starts also activate the system.
        if self.state in {TaskState.IDLE, TaskState.STOPPED}:
            if command not in {"start A", "start B"}:
                return False, "inactive_start_required"
            self.state = TaskState.READY

        if self.state in self.MOVING_STATES:
            if command in {"left", "right"}:
                self._pause(command)
                return True, "clarification_required"
            if command in {"forward", "continue"}:
                return True, "continue_navigation"
            if command == "reverse":
                target = self.active_origin or self.current_location
                self._pause()
                self.pending_command = f"go to {target}"
                self.destination = target
                self.route_choice = "shortest"
                return True, "pending_confirmation"
            if command.startswith("go to "):
                self._pause()
                self.pending_command = command
                self.destination = self._command_destination(command)
                self.route_choice = "shortest"
                return True, "pending_confirmation"
            if command == "alternative route" and self.active_destination:
                self._pause()
                self.pending_command = f"go to {self.active_destination}"
                self.destination = self.active_destination
                self.route_choice = "alternative"
                return True, "pending_confirmation"
            return False, "invalid_in_motion_command"

        if self.state == TaskState.PAUSED:
            if command in {"forward", "continue"}:
                self.state = self.paused_from_state or TaskState.NAVIGATING
                self.paused_from_state = None
                self.clarification_direction = None
                return True, "resume_navigation"
            if command in {"left", "right"}:
                self.clarification_direction = command
                return True, "clarification_required"
            if command == "reverse":
                target = self.active_origin or self.current_location
                self.pending_command = f"go to {target}"
                self.destination = target
                self.route_choice = "shortest"
                return True, "pending_confirmation"
            if command.startswith("go to "):
                self.pending_command = command
                self.destination = self._command_destination(command)
                self.route_choice = "shortest"
                return True, "pending_confirmation"
            if command == "alternative route" and self.active_destination:
                self.pending_command = f"go to {self.active_destination}"
                self.destination = self.active_destination
                self.route_choice = "alternative"
                return True, "pending_confirmation"
            return False, "invalid_paused_command"

        if command.startswith("go to ") and self.state in {
            TaskState.READY,
            TaskState.ARRIVED,
            TaskState.AT_PICKUP,
            TaskState.AT_DROPOFF,
        }:
            self.pending_command = command
            self.destination = self._command_destination(command)
            self.route_choice = "shortest"
            return True, "pending_confirmation"

        valid = {
            TaskState.READY: {"start A", "start B"},
            TaskState.ARRIVED: {"start A", "start B"},
            TaskState.AT_PICKUP: ({"pickup", "drop off"} if not self.pickup_confirmed else {"drop off"}),
            TaskState.AT_DROPOFF: {"return"},
        }
        if command not in valid.get(self.state, set()):
            return False, "invalid_state_command"
        self.pending_command = command
        return True, "pending_confirmation"

    def accept_gesture(self, gesture: str, current_position: Point | None = None) -> tuple[str, RouteRequest | None]:
        gesture = gesture.upper().strip()
        if gesture == "SHAKE":
            self.reset(activated=False, stopped=True)
            return "emergency_stop", None
        if (
            gesture in {"TILT_LEFT", "TILT_RIGHT"}
            and not self.pending_command
            and self.active_destination
            and (self.state in self.MOVING_STATES or self.state == TaskState.PAUSED)
        ):
            # A route-selection tilt during travel has the same confirmation
            # gate as a spoken replan: pause, keep the destination, then nod.
            route_state = self.paused_from_state if self.state == TaskState.PAUSED else self.state
            self.accept_command(f"go to {self.active_destination}")
            # Changing only the route must preserve a pickup/dropoff/return
            # task, including its arrival transition and next valid command.
            if route_state in {TaskState.TO_PICKUP, TaskState.TO_DROPOFF, TaskState.TO_RETURN}:
                self.pending_route_state = route_state
        if self.pending_command and (self.pending_command.startswith("start ") or self.pending_command.startswith("go to ")):
            if gesture == "TILT_LEFT":
                self.route_choice = "short" if self.pending_command.startswith("start ") else "shortest"
                return "route_short_selected", None
            if gesture == "TILT_RIGHT":
                self.route_choice = "long" if self.pending_command.startswith("start ") else "alternative"
                return (
                    "route_long_selected" if self.pending_command.startswith("start ") else "route_alternative_selected"
                ), None
        if gesture != "NOD" or not self.pending_command:
            return "ignored_gesture", None
        command = self.pending_command
        if command.startswith("start ") and self.route_choice not in {"short", "long"}:
            return "route_selection_required", None
        self.pending_command = None
        route_state = self.pending_route_state
        self.pending_route_state = None

        if command.startswith("start "):
            self.destination = command[-1]
            self.active_origin = self.current_location
            self.active_destination = self.destination
            self.active_mode = "legacy"
            self.state = TaskState.TO_PICKUP
            return "route_started", self._pickup_route()
        if command.startswith("go to "):
            destination = command[-1]
            position = current_position or WAYPOINTS.get(self.current_location, WAYPOINTS["S"])
            try:
                request = ROUTE_GRAPH.plan(position, destination, alternative=self.route_choice == "alternative")
            except ValueError as error:
                self.state = TaskState.PAUSED if self.paused_from_state else TaskState.READY
                return str(error), None
            self.destination = destination
            self.active_origin = request.origin or self.current_location
            self.active_destination = destination
            self.active_mode = "legacy" if route_state else "general"
            self.state = route_state or TaskState.NAVIGATING
            self.paused_from_state = None
            self.clarification_direction = None
            return "route_started", request
        if command == "pickup":
            self.pickup_confirmed = True
            return "pickup_completed", None
        if command == "drop off":
            self.active_origin = self.current_location
            self.active_destination = "C"
            self.state = TaskState.TO_DROPOFF
            return "route_started", self._dropoff_route()
        if command == "return":
            self.active_origin = self.current_location
            self.active_destination = "S"
            self.state = TaskState.TO_RETURN
            return "route_started", self._return_route()
        return "ignored_gesture", None

    def route_finished(self) -> str:
        if self.state == TaskState.NAVIGATING:
            self.current_location = self.active_destination or self.current_location
            self.state = TaskState.ARRIVED
            self.active_origin = None
            self.active_destination = None
            self.active_mode = None
            self.destination = None
            self.route_choice = None
            return "destination_reached"
        if self.state == TaskState.TO_PICKUP:
            self.current_location = self.destination or self.current_location
            self.state = TaskState.AT_PICKUP
            return "pickup_waypoint_reached"
        if self.state == TaskState.TO_DROPOFF:
            self.current_location = "C"
            self.state = TaskState.AT_DROPOFF
            return "dropoff_waypoint_reached"
        if self.state == TaskState.TO_RETURN:
            self.current_location = "S"
            self.reset(activated=True)
            return "execution_completed"
        return "unexpected_route_completion"

    def _pickup_route(self) -> RouteRequest:
        assert self.route_choice in {"short", "long"}
        first_name = f"S_A_{self.route_choice.upper()}"
        first = ROUTES[first_name]
        if self.destination == "A":
            return RouteRequest(first_name, tuple(first), (first_name,), "S", "A", self.route_choice == "long")
        return RouteRequest(
            f"{first_name}_B",
            tuple(first + ROUTES["A_B"][1:]),
            (first_name, "A_B"),
            "S",
            "B",
            self.route_choice == "long",
        )

    def _dropoff_route(self) -> RouteRequest:
        route = "A_C" if self.current_location == "A" else "B_C"
        return RouteRequest(route, tuple(ROUTES[route]), (route,), self.current_location, "C")

    def _return_route(self) -> RouteRequest:
        choice = self.route_choice if self.route_choice in {"short", "long"} else "short"
        return_to_s_name = f"S_A_{choice.upper()}"
        return_to_s = list(reversed(ROUTES[return_to_s_name]))
        points = ROUTES["C_A"] + return_to_s[1:]
        return RouteRequest(
            f"C_A_S_{choice.upper()}",
            tuple(points),
            ("A_C", return_to_s_name),
            "C",
            "S",
            choice == "long",
        )


def is_emergency_key(key: int, end_key: int) -> bool:
    """Keep the independently testable keyboard safety rule in one place."""
    return key in (ord("K"), ord("k"), end_key)
