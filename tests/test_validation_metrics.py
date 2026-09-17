from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from validation import ValidationLogger


class ValidationMetricTests(unittest.TestCase):
    def test_metrics_separate_activation_rejection_and_confirmed_response(self):
        with tempfile.TemporaryDirectory() as directory, patch("validation.time.time", side_effect=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
            logger = ValidationLogger(Path(directory))
            logger.event("command_recognised", command="start", accepted=True, status="activated")
            logger.event("command_recognised", command="go to A", accepted=True, status="pending_confirmation")
            logger.event("command_confirmed", command="go to A")
            logger.event("command_recognised", command="unknown", accepted=False, status="invalid_state_command")
            logger.result(pass_result=True)
            payload = json.loads((Path(directory) / "result.json").read_text(encoding="utf-8"))
        metrics = payload["metrics"]
        self.assertEqual(metrics["accepted_command_events"], 2)
        self.assertEqual(metrics["rejected_command_events"], 1)
        self.assertAlmostEqual(metrics["command_acceptance_rate"], 2 / 3, places=4)
        self.assertEqual(metrics["confirmation_response_seconds"], [1.0])
        self.assertTrue(metrics["successful_execution"])


if __name__ == "__main__":
    unittest.main()
