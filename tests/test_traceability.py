from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(CONTROLLER))

from input_adapters import GestureEventReplayRecognizer, LocalMultimodalInput, TranscriptReplayRecognizer, parse_vosk_decision, parse_vosk_result
from validation import ValidationLogger


class FakeVoice:
    ready = True
    device_name = "fixture microphone"
    sample_rate = 16000
    last_trace = {"transcript": "stop", "command": "stop", "confidence": 1.0, "accepted": True, "reason": "accepted"}

    def poll(self):
        return None

    def close(self):
        pass


class FakeGesture:
    ready = True
    face_present = True
    calibrated = True
    camera_index = "fixture.mp4"
    camera_backend = "fixture"
    resolution = (30, 20)

    def __init__(self):
        self.frame = [["transient pixels"]]

    def poll(self):
        return None

    def trace_status(self):
        return {"calibration_progress": 1.0, "pose": [0.0, 0.0, 0.0]}

    def consume_preview_frame(self):
        frame, self.frame = self.frame, None
        return frame

    def close(self):
        self.frame = None


class TraceabilityTests(unittest.TestCase):
    def test_vosk_trace_keeps_decision_evidence_without_audio(self):
        accepted_payload = json.dumps({"text": "start a", "result": [{"word": "start", "conf": 0.91}, {"word": "a", "conf": 0.89}]})
        rejected_payload = json.dumps({"text": "start a", "result": [{"word": "start", "conf": 0.60}, {"word": "a", "conf": 0.92}]})
        accepted = parse_vosk_decision(accepted_payload)
        rejected = parse_vosk_decision(rejected_payload)
        self.assertEqual(parse_vosk_result(accepted_payload), "start A")
        self.assertTrue(accepted["accepted"])
        self.assertEqual(rejected["reason"], "low_confidence")
        self.assertNotIn("audio", accepted)

    def test_input_trace_keeps_pixels_out_of_json_status(self):
        inputs = LocalMultimodalInput("unused", strict=True, voice_factory=lambda *_args, **_kwargs: FakeVoice(), gesture_factory=lambda *_args, **_kwargs: FakeGesture())
        trace = inputs.trace_status()
        json.dumps(trace)
        self.assertEqual(inputs.consume_preview_frame(), [["transient pixels"]])
        self.assertIsNone(inputs.consume_preview_frame())
        self.assertNotIn("frame", trace)
        inputs.close()

    def test_live_logger_appends_across_reset_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            first = ValidationLogger(run_dir, append=True)
            first.event("dashboard_reset_requested")
            second = ValidationLogger(run_dir, append=True)
            second.event("controller_started")
            lines = (run_dir / "controller_events.ndjson").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertNotEqual(json.loads(lines[0])["session_id"], json.loads(lines[1])["session_id"])

    def test_transcript_replay_uses_text_timing_without_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            schedule = Path(directory) / "schedule.json"
            schedule.write_text(json.dumps({"transcripts": [
                {"at_seconds": 1.0, "transcript": "start a", "confidence": 0.95},
                {"at_seconds": 2.0, "transcript": "drop off", "confidence": 0.4},
            ]}), encoding="utf-8")
            times = iter([10.0, 10.5, 11.0, 12.0])
            recognizer = TranscriptReplayRecognizer(str(schedule), clock=lambda: next(times))
            self.assertIsNone(recognizer.poll())
            self.assertEqual(recognizer.poll(), "start A")
            self.assertIsNone(recognizer.poll())
            self.assertEqual(recognizer.last_trace["reason"], "low_confidence")
            self.assertEqual(recognizer.sample_rate, 0)

    def test_classified_gesture_manifest_replays_exact_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "gestures.json"
            manifest.write_text(json.dumps({
                "uses_production_classifier": True,
                "calibration_completed": True,
                "gesture_events": [
                    {"time_seconds": 1.0, "gesture": "TILT_LEFT", "section": "left"},
                    {"time_seconds": 2.0, "gesture": "NOD", "section": "confirm"},
                ],
            }), encoding="utf-8")
            current = [10.0]
            recognizer = GestureEventReplayRecognizer(str(manifest), clock=lambda: current[0])
            current[0] = 10.9
            self.assertIsNone(recognizer.poll())
            current[0] = 11.0
            self.assertEqual(recognizer.poll(), "TILT_LEFT")
            self.assertEqual(recognizer.last_trace["source"], "classified_gesture_video_replay")
            current[0] = 12.0
            self.assertEqual(recognizer.poll(), "NOD")
            self.assertTrue(recognizer.trace_status()["finished"])

    def test_unverified_gesture_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "gestures.json"
            manifest.write_text(json.dumps({"gesture_events": [{"time_seconds": 1, "gesture": "NOD"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                GestureEventReplayRecognizer(str(manifest))


if __name__ == "__main__":
    unittest.main()
