from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import parse_vosk_result
from model import TaskMachine, TaskState


class TranscribedCommandWorkflowTests(unittest.TestCase):
    def run_workflow(self, destination, route_gesture, transcripts):
        machine = TaskMachine()
        self.assertTrue(machine.accept_command(transcripts[0])[0])
        machine.accept_gesture(route_gesture)
        route = machine.accept_gesture("NOD")[1]
        self.assertIsNotNone(route)
        self.assertEqual(machine.route_finished(), "pickup_waypoint_reached")
        self.assertTrue(machine.accept_command(transcripts[1])[0])
        self.assertEqual(machine.accept_gesture("NOD")[0], "pickup_completed")
        self.assertTrue(machine.accept_command(transcripts[2])[0])
        self.assertIsNotNone(machine.accept_gesture("NOD")[1])
        self.assertEqual(machine.route_finished(), "dropoff_waypoint_reached")
        self.assertTrue(machine.accept_command(transcripts[3])[0])
        self.assertIsNotNone(machine.accept_gesture("NOD")[1])
        self.assertEqual(machine.route_finished(), "execution_completed")
        self.assertEqual(machine.state, TaskState.READY)
        self.assertEqual(machine.destination, None)
        return route.name

    def test_a_workflow_accepts_transcript_format_variations(self):
        route = self.run_workflow("A", "TILT_LEFT", ["  START   A ", "pick up", "dropoff", " RETURN "])
        self.assertEqual(route, "S_A_SHORT")

    def test_b_workflow_accepts_transcript_case_variations(self):
        route = self.run_workflow("B", "TILT_RIGHT", ["START B", "PICKUP", "DROP OFF", "return"])
        self.assertEqual(route, "S_A_LONG_B")

    def test_unbounded_and_wrong_state_transcripts_fail_closed(self):
        machine = TaskMachine()
        self.assertEqual(machine.accept_command("drive away"), (False, "inactive_start_required"))
        self.assertEqual(machine.accept_command("pickup"), (False, "inactive_start_required"))
        self.assertEqual(machine.state, TaskState.IDLE)

    def test_transcribed_stop_is_global_after_normalisation(self):
        machine = TaskMachine()
        machine.accept_command("start A")
        machine.accept_gesture("TILT_LEFT")
        machine.accept_gesture("NOD")
        self.assertEqual(machine.state, TaskState.TO_PICKUP)
        self.assertEqual(machine.accept_command("  STOP  "), (True, "emergency_stop"))
        self.assertEqual(machine.state, TaskState.STOPPED)

    def test_vosk_json_confidence_boundary_uses_transcribed_words(self):
        accepted = json.dumps({
            "text": "drop off",
            "result": [{"word": "drop", "conf": 0.80}, {"word": "off", "conf": 0.70}],
        })
        rejected = json.dumps({
            "text": "drop off",
            "result": [{"word": "drop", "conf": 0.80}, {"word": "off", "conf": 0.60}],
        })
        self.assertEqual(parse_vosk_result(accepted, confidence_threshold=0.65), "drop off")
        self.assertIsNone(parse_vosk_result(rejected, confidence_threshold=0.65))


if __name__ == "__main__":
    unittest.main()
