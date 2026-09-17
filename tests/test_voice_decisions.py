from pathlib import Path
import json
import queue
import sys
import time
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import VoskCommandRecognizer, parse_vosk_decision
from model import TaskMachine, TaskState, live_startup_gate, normalise_command


def final_result(transcript, confidences):
    return json.dumps({
        "text": transcript,
        "result": [{"word": word, "conf": confidence}
                   for word, confidence in zip(transcript.split(), confidences)],
    })


class VoiceDecisionTests(unittest.TestCase):
    def test_alpha_alias_requires_activation_and_separate_nod(self):
        self.assertIn("go to alpha", json.loads(VoskCommandRecognizer.grammar))
        decision = parse_vosk_decision(final_result("go to alpha", (0.92, 0.91, 0.89)))
        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["command"], "go to A")
        self.assertEqual(normalise_command(" GO  TO Alpha "), "go to A")
        machine = TaskMachine()
        self.assertEqual(machine.accept_command(decision["command"]), (False, "inactive_start_required"))
        self.assertEqual(machine.state, TaskState.IDLE)
        self.assertEqual(live_startup_gate("go to alpha", TaskState.IDLE), "go to A")
        machine.accept_command("start")
        self.assertEqual(machine.accept_command(decision["command"]), (True, "pending_confirmation"))
        self.assertEqual(machine.state, TaskState.READY)
        self.assertEqual(machine.pending_command, "go to A")
        self.assertEqual(machine.accept_gesture("TILT_RIGHT"), ("route_alternative_selected", None))
        outcome, route = machine.accept_gesture("NOD")
        self.assertEqual(outcome, "route_started")
        self.assertEqual(route.destination, "A")
        self.assertTrue(route.alternative)

    def test_alpha_alias_keeps_confidence_and_bounded_grammar(self):
        decision = parse_vosk_decision(final_result("go to alpha", (0.99, 0.99, 0.64)))
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["threshold"], 0.65)
        for transcript in ("alpha", "go to", "go to a please", "go to unknown"):
            self.assertIsNone(normalise_command(transcript))

    def test_destination_letters_keep_the_same_confidence_boundary(self):
        for destination in "abcs":
            for confidence, accepted in ((0.64, False), (0.65, True)):
                with self.subTest(destination=destination, confidence=confidence):
                    decision = parse_vosk_decision(final_result(
                        f"go to {destination}", (0.99, 0.99, confidence)))
                    self.assertEqual(decision["command"], f"go to {destination.upper()}")
                    self.assertEqual(decision["accepted"], accepted)
                    self.assertEqual(decision["threshold"], 0.65)

    def test_rejection_identifies_uncertain_word_without_audio(self):
        decision = parse_vosk_decision(final_result("go to a", (0.94, 0.92, 0.51)))
        self.assertEqual(decision["reason"], "low_confidence")
        self.assertEqual(decision["word_confidences"], [
            {"word": "go", "confidence": 0.94},
            {"word": "to", "confidence": 0.92},
            {"word": "a", "confidence": 0.51},
        ])
        self.assertNotIn("audio", decision)

    @staticmethod
    def recognizer_with_results(results):
        class FakeKaldi:
            def AcceptWaveform(self, audio):
                self.current = results[int(audio)]
                return "partial" not in self.current

            def Result(self):
                return json.dumps(self.current)

            def PartialResult(self):
                return json.dumps(self.current)

        recognizer = VoskCommandRecognizer.__new__(VoskCommandRecognizer)
        recognizer._stream = types.SimpleNamespace(active=True)
        recognizer._stream_error = None
        recognizer._last_callback_at = time.monotonic()
        recognizer.callback_timeout = 2.0
        recognizer._queue = queue.Queue()
        recognizer._recognizer = FakeKaldi()
        recognizer.callback_count = 0
        recognizer.last_audio_peak = 0
        recognizer.last_partial_transcript = ""
        recognizer.confidence_threshold = 0.65
        recognizer.last_trace = None
        recognizer.last_final_trace = None
        recognizer.final_decision_count = 0
        for index in range(len(results)):
            recognizer._queue.put(str(index).encode("ascii"))
        return recognizer

    def test_rejected_final_survives_next_partial_and_silence(self):
        recognizer = self.recognizer_with_results([
            json.loads(final_result("go to a", (0.94, 0.92, 0.51))),
            {"partial": "go to"},
            {"text": ""},
        ])
        self.assertIsNone(recognizer.poll())
        self.assertEqual(recognizer.last_trace["reason"], "partial_transcript")
        self.assertIsNotNone(recognizer.last_final_trace)
        self.assertEqual(recognizer.last_final_trace["transcript"], "go to a")
        self.assertEqual(recognizer.last_final_trace["reason"], "low_confidence")
        self.assertEqual(recognizer.last_final_trace["decision_id"], 1)
        self.assertIsNone(recognizer.poll())
        self.assertEqual(recognizer.last_final_trace["decision_id"], 1)
        self.assertEqual(recognizer.last_final_trace["transcript"], "go to a")

    def test_repeated_identical_final_results_have_distinct_decision_ids(self):
        result = json.loads(final_result("go to a", (0.91, 0.92, 0.93)))
        recognizer = self.recognizer_with_results([result, result])
        self.assertEqual(recognizer.poll(), "go to A")
        self.assertEqual(recognizer.last_final_trace["decision_id"], 1)
        self.assertEqual(recognizer.poll(), "go to A")
        self.assertEqual(recognizer.last_final_trace["decision_id"], 2)


if __name__ == "__main__":
    unittest.main()
