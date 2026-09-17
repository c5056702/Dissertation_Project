from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from model import TaskMachine, TaskState, is_emergency_key, normalise_command, route_length


class TaskMachineTests(unittest.TestCase):
    def test_baseline_route_sequence(self):
        machine = TaskMachine()
        self.assertEqual(machine.accept_command("start A"), (True, "pending_confirmation"))
        self.assertEqual(machine.accept_gesture("TILT_LEFT")[0], "route_short_selected")
        outcome, route = machine.accept_gesture("NOD")
        self.assertEqual(outcome, "route_started")
        self.assertEqual(route.name, "S_A_SHORT")
        self.assertGreater(route_length(route.points), 0)
        self.assertEqual(machine.route_finished(), "pickup_waypoint_reached")
        self.assertEqual(machine.state, TaskState.AT_PICKUP)
        self.assertEqual(machine.accept_command("pickup"), (True, "pending_confirmation"))
        self.assertEqual(machine.accept_gesture("NOD")[0], "pickup_completed")
        self.assertEqual(machine.accept_command("drop off"), (True, "pending_confirmation"))
        self.assertEqual(machine.accept_gesture("NOD")[1].name, "A_C")
        self.assertEqual(machine.route_finished(), "dropoff_waypoint_reached")
        self.assertEqual(machine.accept_command("return"), (True, "pending_confirmation"))
        self.assertIn("C_A_S", machine.accept_gesture("NOD")[1].name)
        self.assertEqual(machine.route_finished(), "execution_completed")
        self.assertEqual(machine.state, TaskState.READY)

    def test_invalid_command_fails_closed(self):
        machine = TaskMachine()
        self.assertEqual(machine.accept_command("drop off"), (False, "inactive_start_required"))
        self.assertEqual(machine.state, TaskState.IDLE)

    def test_shake_stops_and_resets(self):
        machine = TaskMachine()
        machine.accept_command("start B")
        self.assertEqual(machine.accept_gesture("SHAKE"), ("emergency_stop", None))
        self.assertEqual(machine.state, TaskState.STOPPED)

    def test_expanded_b_route_uses_long_selection(self):
        machine = TaskMachine()
        self.assertEqual(machine.accept_command("start B"), (True, "pending_confirmation"))
        self.assertEqual(machine.accept_gesture("TILT_RIGHT")[0], "route_long_selected")
        _, route = machine.accept_gesture("NOD")
        self.assertEqual(route.name, "S_A_LONG_B")
        self.assertEqual(machine.route_finished(), "pickup_waypoint_reached")
        self.assertEqual(machine.accept_command("pickup"), (True, "pending_confirmation"))
        machine.accept_gesture("NOD")
        self.assertEqual(machine.accept_command("drop off"), (True, "pending_confirmation"))
        _, route = machine.accept_gesture("NOD")
        self.assertEqual(route.name, "B_C")

    def test_voice_stop_resets_any_pending_state(self):
        machine = TaskMachine()
        machine.accept_command("start A")
        self.assertEqual(machine.accept_command("stop"), (True, "emergency_stop"))
        self.assertEqual(machine.state, TaskState.STOPPED)
        self.assertIsNone(machine.pending_command)

    def test_command_normalisation_is_bounded(self):
        self.assertEqual(normalise_command("  DROP   OFF "), "drop off")
        self.assertEqual(normalise_command(" TURN LEFT "), "left")
        self.assertEqual(normalise_command("Go To B"), "go to B")
        self.assertIsNone(normalise_command("go somewhere"))

    def test_keyboard_emergency_keys_are_bounded(self):
        self.assertTrue(is_emergency_key(ord("K"), 999))
        self.assertTrue(is_emergency_key(ord("k"), 999))
        self.assertTrue(is_emergency_key(999, 999))
        self.assertFalse(is_emergency_key(ord("A"), 999))

    def test_start_requires_route_selection_before_nod(self):
        machine = TaskMachine()
        machine.accept_command("start A")
        self.assertEqual(machine.accept_gesture("NOD"), ("route_selection_required", None))
        self.assertEqual(machine.state, TaskState.READY)
        self.assertEqual(machine.accept_gesture("TILT_LEFT")[0], "route_short_selected")
        self.assertEqual(machine.accept_gesture("NOD")[0], "route_started")


if __name__ == "__main__":
    unittest.main()
