"""Route choices must survive repeats and represent distinct physical paths."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'controllers' / 'epuck_waypoint_controller'))
from model import ROUTE_GRAPH, RouteGraph, TaskMachine, WAYPOINTS, route_length


class RouteChoiceConsistencyTests(unittest.TestCase):
    def test_repeating_pending_destination_keeps_explicit_right_tilt(self):
        for destination in WAYPOINTS:
            with self.subTest(destination=destination):
                machine = TaskMachine()
                machine.accept_command('start')
                machine.accept_command(f'go to {destination}')
                machine.accept_gesture('TILT_RIGHT')
                machine.accept_command(f'go to {destination}')
                self.assertEqual(machine.route_choice, 'alternative')
                self.assertEqual(machine.pending_command, f'go to {destination}')
                origin = 'A' if destination == 'S' else 'S'
                outcome, request = machine.accept_gesture('NOD', WAYPOINTS[origin])
                self.assertEqual(outcome, 'route_started')
                self.assertTrue(request.alternative)
                self.assertEqual(request.destination, destination)

    def test_changed_destination_defaults_to_shortest_then_right_selects_alternative(self):
        machine = TaskMachine()
        machine.accept_command('start')
        machine.accept_command('go to A')
        machine.accept_gesture('TILT_RIGHT')
        machine.accept_command('go to B')
        self.assertEqual(machine.route_choice, 'shortest')
        machine.accept_gesture('TILT_RIGHT')
        _, request = machine.accept_gesture('NOD', WAYPOINTS['S'])
        self.assertEqual(request.destination, 'B')
        self.assertTrue(request.alternative)

    def test_mid_edge_alternative_never_retraces_its_first_edge(self):
        for edge in ROUTE_GRAPH.edges:
            current = tuple((a + b) / 2 for a, b in zip(edge.start, edge.end))
            for destination in WAYPOINTS:
                with self.subTest(current=current, destination=destination):
                    shortest = ROUTE_GRAPH.plan(current, destination)
                    alternative = ROUTE_GRAPH.plan(current, destination, alternative=True)
                    self.assertTrue(alternative.alternative)
                    self.assertNotEqual(alternative.points, shortest.points)
                    self.assertGreaterEqual(route_length(alternative.points) + 1e-8, route_length(shortest.points))
                    for a, b, c in zip(alternative.points, alternative.points[1:], alternative.points[2:]):
                        # A genuine alternative must not begin with a detour
                        # backwards along an edge it immediately retraces.
                        incoming = (b[0] - a[0], b[1] - a[1])
                        outgoing = (c[0] - b[0], c[1] - b[1])
                        cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
                        dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
                        self.assertFalse(abs(cross) < 1e-8 and dot < -1e-8, (a, b, c))

    def test_unavailable_alternative_never_falls_back_to_shortest(self):
        graph = RouteGraph()
        graph.edges = [edge for edge in graph.edges if 'S_A_SHORT' in edge.route_ids]
        self.assertFalse(graph.plan(WAYPOINTS['S'], 'A').alternative)
        with self.assertRaisesRegex(ValueError, 'alternative_route_unavailable'):
            graph.plan(WAYPOINTS['S'], 'A', alternative=True)

    def test_alternative_at_destination_cannot_start_a_route(self):
        with self.assertRaisesRegex(ValueError, 'already_at_destination'):
            ROUTE_GRAPH.plan(WAYPOINTS['A'], 'A', alternative=True)

    def test_legacy_long_route_reports_alternative_consistently(self):
        for destination in ('A', 'B'):
            machine = TaskMachine()
            machine.accept_command(f'start {destination}')
            machine.accept_gesture('TILT_RIGHT')
            _, request = machine.accept_gesture('NOD')
            self.assertTrue(request.alternative)
            self.assertIn('LONG', request.name)


if __name__ == '__main__':
    unittest.main()
