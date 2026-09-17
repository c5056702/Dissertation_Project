from pathlib import Path
from collections import deque
import queue
import json
import struct
import sys
import time
import types
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "controllers" / "epuck_waypoint_controller"))

from input_adapters import LocalMultimodalInput, MediaPipeGestureRecognizer, VoskCommandRecognizer


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class SequenceFactory:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeVoice:
    def __init__(self, events=None):
        self.events = list(events or [])
        self.ready = True
        self.closed = False

    def poll(self):
        if not self.events:
            return None
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    def close(self):
        self.closed = True
        self.ready = False


class FakeGesture:
    def __init__(self, events=None, calibrated=False):
        self.events = list(events or [])
        self.ready = True
        self.face_present = False
        self.calibrated = calibrated
        self.closed = False

    def poll(self):
        if not self.events:
            return None
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    def close(self):
        self.closed = True
        self.ready = False


class DeviceRecoveryTests(unittest.TestCase):
    def test_voice_and_gesture_from_same_poll_are_fused(self):
        inputs = LocalMultimodalInput(
            "model",
            strict=False,
            voice_factory=SequenceFactory([FakeVoice(["go to A"])]),
            gesture_factory=SequenceFactory([FakeGesture(["NOD"], calibrated=True)]),
        )
        self.assertEqual(inputs.poll(), {"command": "go to A", "gesture": "NOD"})
        self.assertEqual(inputs.trace_status()["active_input_source"], "MICROPHONE")
        self.assertEqual(inputs.trace_status()["active_input_detail"], "go to A")

    def test_camera_indicator_is_used_for_gesture_only_and_safety_shake(self):
        inputs = LocalMultimodalInput(
            "model",
            strict=False,
            voice_factory=SequenceFactory([FakeVoice([None, "go to B"])]),
            gesture_factory=SequenceFactory([FakeGesture(["TILT_LEFT", "SHAKE"], calibrated=True)]),
        )
        self.assertEqual(inputs.poll(), {"gesture": "TILT_LEFT"})
        self.assertEqual(inputs.trace_status()["active_input_source"], "CAMERA")
        self.assertEqual(inputs.poll(), {"command": "go to B", "gesture": "SHAKE"})
        self.assertEqual(inputs.trace_status()["active_input_source"], "CAMERA")
        self.assertIn("safety stop", inputs.trace_status()["active_input_detail"])

    def test_missing_camera_connects_automatically_after_retry(self):
        clock = FakeClock()
        voice = FakeVoice()
        camera = FakeGesture(calibrated=False)
        voice_factory = SequenceFactory([voice])
        camera_factory = SequenceFactory([RuntimeError("not connected"), camera])
        inputs = LocalMultimodalInput(
            "model",
            "auto",
            retry_interval=2.0,
            strict=False,
            voice_factory=voice_factory,
            gesture_factory=camera_factory,
            clock=clock,
        )
        self.assertTrue(inputs.voice_ready)
        self.assertFalse(inputs.gesture_ready)
        inputs.poll()
        self.assertEqual(camera_factory.calls, 1)
        clock.advance(2.0)
        inputs.poll()
        self.assertTrue(inputs.ready)
        self.assertEqual(camera_factory.calls, 2)
        self.assertFalse(inputs.gesture_calibrated)

    def test_microphone_disconnect_is_closed_then_reconnected(self):
        clock = FakeClock()
        failed_voice = FakeVoice([RuntimeError("device removed")])
        replacement = FakeVoice(["stop"])
        voice_factory = SequenceFactory([failed_voice, replacement])
        camera = FakeGesture()
        inputs = LocalMultimodalInput(
            "model",
            retry_interval=1.0,
            strict=False,
            voice_factory=voice_factory,
            gesture_factory=SequenceFactory([camera]),
            clock=clock,
        )
        self.assertIsNone(inputs.poll())
        self.assertTrue(failed_voice.closed)
        self.assertFalse(inputs.voice_ready)
        clock.advance(1.0)
        self.assertEqual(inputs.poll(), {"command": "stop"})
        self.assertTrue(inputs.ready)
        self.assertEqual(inputs.voice_reconnects, 2)

    def test_camera_disconnect_requires_new_adapter_and_recalibration(self):
        clock = FakeClock()
        failed_camera = FakeGesture([RuntimeError("frames stopped")], calibrated=True)
        replacement = FakeGesture(["TILT_LEFT"], calibrated=False)
        inputs = LocalMultimodalInput(
            "model",
            retry_interval=1.0,
            strict=False,
            voice_factory=SequenceFactory([FakeVoice()]),
            gesture_factory=SequenceFactory([failed_camera, replacement]),
            clock=clock,
        )
        self.assertIsNone(inputs.poll())
        self.assertTrue(failed_camera.closed)
        self.assertFalse(inputs.gesture_ready)
        clock.advance(1.0)
        self.assertEqual(inputs.poll(), {"gesture": "TILT_LEFT"})
        self.assertFalse(inputs.gesture_calibrated)

    def test_strict_preflight_fails_closed_and_releases_partial_device(self):
        voice = FakeVoice()
        with self.assertRaisesRegex(RuntimeError, "camera"):
            LocalMultimodalInput(
                "model",
                strict=True,
                voice_factory=SequenceFactory([voice]),
                gesture_factory=SequenceFactory([RuntimeError("camera absent")]),
            )
        self.assertTrue(voice.closed)

    def test_interrupted_camera_initialization_closes_voice_and_reraises(self):
        for strict in (False, True):
            with self.subTest(strict=strict):
                voice = FakeVoice()
                interruption = KeyboardInterrupt()
                with self.assertRaises(KeyboardInterrupt) as raised:
                    LocalMultimodalInput(
                        "model",
                        strict=strict,
                        voice_factory=SequenceFactory([voice]),
                        gesture_factory=mock.Mock(side_effect=interruption),
                    )
                self.assertIs(raised.exception, interruption)
                self.assertTrue(voice.closed)
                self.assertFalse(voice.ready)

    def test_adapter_that_becomes_inactive_is_replaced(self):
        clock = FakeClock()
        first = FakeVoice()
        replacement = FakeVoice(["return"])
        inputs = LocalMultimodalInput(
            "model",
            retry_interval=1.0,
            strict=False,
            voice_factory=SequenceFactory([first, replacement]),
            gesture_factory=SequenceFactory([FakeGesture()]),
            clock=clock,
        )
        first.ready = False
        self.assertIsNone(inputs.poll())
        self.assertTrue(first.closed)
        clock.advance(1.0)
        self.assertEqual(inputs.poll(), {"command": "return"})

    def test_camera_frame_failure_is_reported_as_disconnect(self):
        class FailedCapture:
            def read(self):
                return False, None

        class Detector:
            def __init__(self):
                self.losses = 0

            def face_lost(self):
                self.losses += 1

        recognizer = MediaPipeGestureRecognizer.__new__(MediaPipeGestureRecognizer)
        recognizer._prefetched_frames = deque()
        recognizer.capture = FailedCapture()
        recognizer.detector = Detector()
        recognizer.face_present = True
        recognizer.frame_read_failures = 0
        self.assertIsNone(recognizer.poll())
        self.assertIsNone(recognizer.poll())
        with self.assertRaisesRegex(RuntimeError, "stopped delivering frames"):
            recognizer.poll()
        self.assertFalse(recognizer.face_present)
        self.assertEqual(recognizer.detector.losses, 3)

    def test_microphone_callback_stall_is_reported_as_disconnect(self):
        class ActiveStream:
            active = True

        recognizer = VoskCommandRecognizer.__new__(VoskCommandRecognizer)
        recognizer._stream = ActiveStream()
        recognizer._stream_error = None
        recognizer._last_callback_at = time.monotonic() - 5.0
        recognizer.callback_timeout = 2.0
        recognizer._queue = queue.Queue()
        with self.assertRaisesRegex(RuntimeError, "stopped delivering callback data"):
            recognizer.poll()

    def test_microphone_callback_and_partial_transcript_reach_vosk_trace(self):
        class ActiveStream:
            active = True

        class PartialRecognizer:
            def AcceptWaveform(self, _audio):
                return False

            def PartialResult(self):
                return json.dumps({"partial": "start"})

        recognizer = VoskCommandRecognizer.__new__(VoskCommandRecognizer)
        recognizer._stream = ActiveStream()
        recognizer._stream_error = None
        recognizer._last_callback_at = time.monotonic()
        recognizer.callback_timeout = 2.0
        recognizer._queue = queue.Queue(maxsize=8)
        recognizer._recognizer = PartialRecognizer()
        recognizer.callback_count = 0
        recognizer.audio_bytes_received = 0
        recognizer.last_audio_peak = 0
        recognizer.last_partial_transcript = ""
        recognizer.confidence_threshold = 0.65
        recognizer.last_trace = None
        payload = struct.pack("<4h", 0, 1200, -2400, 800)
        recognizer._capture(payload, 4, None, None)
        self.assertEqual(recognizer.callback_count, 1)
        self.assertEqual(recognizer.audio_bytes_received, len(payload))
        self.assertEqual(recognizer.last_audio_peak, 2400)
        self.assertIsNone(recognizer.poll())
        self.assertEqual(recognizer.last_partial_transcript, "start")
        self.assertEqual(recognizer.last_trace["reason"], "partial_transcript")

    def test_live_vosk_enables_word_confidence_output(self):
        class FakeKaldiRecognizer:
            last = None

            def __init__(self, _model, _rate, _grammar):
                type(self).last = self
                self.words_enabled = False
                self.partial_words_enabled = False

            def SetWords(self, enabled):
                self.words_enabled = enabled

            def SetPartialWords(self, enabled):
                self.partial_words_enabled = enabled

        class FakeStream:
            def __init__(self, *, callback, **_kwargs):
                self.callback = callback
                self.active = False

            def start(self):
                self.active = True
                self.callback(b"\x00" * 1600, 800, None, None)

            def stop(self):
                self.active = False

            def close(self):
                self.active = False

        fake_sounddevice = types.SimpleNamespace(
            query_devices=lambda _device, _kind: {"name": "test microphone", "default_samplerate": 16000},
            RawInputStream=FakeStream,
        )
        fake_vosk = types.SimpleNamespace(Model=lambda _path: object(), KaldiRecognizer=FakeKaldiRecognizer)
        model_path = ROOT / "models" / "vosk-model-small-en-us-0.15"
        with mock.patch.dict(sys.modules, {"sounddevice": fake_sounddevice, "vosk": fake_vosk}):
            recognizer = VoskCommandRecognizer(str(model_path), readiness_timeout=0.1)
        try:
            self.assertTrue(FakeKaldiRecognizer.last.words_enabled)
            self.assertTrue(FakeKaldiRecognizer.last.partial_words_enabled)
        finally:
            recognizer.close()


if __name__ == "__main__":
    unittest.main()
