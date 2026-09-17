"""Local-only voice and gesture inputs; no media is written to disk."""

from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import queue
import sys
import time
from typing import Any, Callable

from model import normalise_command


def parse_vosk_result(payload: str, confidence_threshold: float = 0.65) -> str | None:
    """Parse a final Vosk JSON result using the bounded project grammar."""
    decision = parse_vosk_decision(payload, confidence_threshold)
    return str(decision["command"]) if decision["accepted"] else None


def parse_vosk_decision(payload: str, confidence_threshold: float = 0.65) -> dict[str, Any]:
    """Return non-audio trace evidence for one final Vosk result."""
    result = json.loads(payload)
    words = result.get("result", [])
    confidence = min((float(word.get("conf", 0.0)) for word in words), default=0.0)
    transcript = str(result.get("text", "")).strip()
    command = normalise_command(transcript)
    # Standalone START only activates the controller and cannot move the robot,
    # so it can safely use a slightly more tolerant threshold. Destination and
    # movement-affecting commands retain the stricter threshold plus gesture
    # confirmation where applicable.
    required_threshold = min(confidence_threshold, 0.50) if command == "start" else confidence_threshold
    accepted = bool(command and confidence >= required_threshold)
    if accepted:
        reason = "accepted"
    elif not transcript:
        reason = "empty_result"
    elif not command:
        reason = "outside_bounded_grammar"
    else:
        reason = "low_confidence"
    return {
        "transcript": transcript,
        "command": command,
        "confidence": round(confidence, 4),
        "word_confidences": [
            {"word": str(word.get("word", "")), "confidence": round(float(word.get("conf", 0.0)), 4)}
            for word in words
        ],
        "threshold": required_threshold,
        "accepted": accepted,
        "reason": reason,
    }


def classify_pose_history(history: list[tuple[float, float, float]]) -> str | None:
    """Classify a smoothed neutral-relative pose window without camera dependencies."""
    if len(history) < 2:
        return None
    roll = sum(sample[0] for sample in history) / len(history)
    pitch_span = max(sample[1] for sample in history) - min(sample[1] for sample in history)
    yaw_min = min(sample[2] for sample in history)
    yaw_max = max(sample[2] for sample in history)
    if (
        yaw_max - yaw_min >= 0.09
        and yaw_min <= -GestureStateDetector.NEUTRAL_YAW
        and yaw_max >= GestureStateDetector.NEUTRAL_YAW
    ):
        return "SHAKE"
    if pitch_span >= 0.065:
        return "NOD"
    if roll <= -0.20:
        return "TILT_LEFT"
    if roll >= 0.20:
        return "TILT_RIGHT"
    return None


class GestureStateDetector:
    """One-shot gesture detector operating on neutral-relative head pose.

    Tilts require a short sustained roll, nods a short sustained pitch
    excursion, and shakes rapid yaw excursions to both sides of neutral.
    After any event, tilt and nod detection re-arm only after a stable neutral
    pose. This prevents held
    gestures from producing repeated controller inputs.
    """

    TILT_THRESHOLD = 0.20
    TILT_STABLE_FRAMES = 4
    TILT_MAX_PITCH = 0.075
    TILT_MAX_YAW = 0.10
    PITCH_THRESHOLD = 0.050
    PITCH_STABLE_FRAMES = 4
    SHAKE_SPAN_THRESHOLD = 0.10
    SHAKE_WINDOW_FRAMES = 10
    NEUTRAL_ROLL = 0.10
    NEUTRAL_PITCH = 0.028
    NEUTRAL_YAW = 0.040
    REARM_NEUTRAL_FRAMES = 6
    def __init__(self, cooldown_seconds: float = 0.8) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.last_emitted = float("-inf")
        self.armed = True
        self.neutral_frames = 0
        self.tilt_sign = 0
        self.tilt_frames = 0
        self.pitch_sign = 0
        self.pitch_frames = 0
        self.pitch_peak_abs = 0.0
        self.yaw_history: deque[float] = deque(maxlen=self.SHAKE_WINDOW_FRAMES)
        self.shake_armed = True
        self.shake_neutral_frames = 0
        self.last_evidence: dict[str, float | int] = {}
        self.neutral_axes_outside: list[str] | None = None
        self.tilt_direction: str | None = None
        self.tilt_blocked_axes: list[str] | None = None

    def face_lost(self) -> None:
        """Discard incomplete motion so reacquisition cannot create a gesture."""
        self._clear_motion()
        self.armed = False
        self.shake_armed = False
        self.neutral_frames = 0
        self.shake_neutral_frames = 0
        self.neutral_axes_outside = None
        self.tilt_direction = None
        self.tilt_blocked_axes = None

    def update(self, pose: tuple[float, float, float], now: float | None = None) -> str | None:
        now = time.monotonic() if now is None else now
        roll, pitch, yaw = pose
        neutral = self._is_neutral(pose)
        # Only keep the derived reasons for a blocked re-arm. The dashboard
        # can explain how to return to the calibrated neutral pose without
        # storing camera frames or landmarks or changing gesture thresholds.
        self.neutral_axes_outside = [
            axis
            for axis, value, limit in (
                ("roll", roll, self.NEUTRAL_ROLL),
                ("pitch", pitch, self.NEUTRAL_PITCH),
                ("yaw", yaw, self.NEUTRAL_YAW),
            )
            if abs(value) > limit
        ]
        self.tilt_direction = (
            ("TILT_LEFT" if roll < 0 else "TILT_RIGHT")
            if abs(roll) >= self.TILT_THRESHOLD else None
        )
        self.tilt_blocked_axes = [
            axis for axis, value, limit in (
                ("pitch", pitch, self.TILT_MAX_PITCH),
                ("yaw", yaw, self.TILT_MAX_YAW),
            ) if abs(value) > limit
        ]

        # A shake must reach both sides of calibrated neutral. A single head
        # turn, including its return to neutral, is not a shake even when its
        # span is large. Pitch and roll stay outside the safety channel.
        if abs(roll) <= 0.16 and abs(pitch) <= 0.06:
            self.yaw_history.append(yaw)
        else:
            self.yaw_history.clear()
        if (
            self.shake_armed
            and len(self.yaw_history) >= 2
            and self._yaw_crosses_neutral()
            and (yaw_span := max(self.yaw_history) - min(self.yaw_history)) >= self.SHAKE_SPAN_THRESHOLD
            and self._cooldown_ready(now)
        ):
            return self._emit(
                "SHAKE",
                now,
                {
                    "yaw_span": round(yaw_span, 4),
                    "yaw_min": round(min(self.yaw_history), 4),
                    "yaw_max": round(max(self.yaw_history), 4),
                },
            )

        if not self.shake_armed:
            if neutral:
                self.shake_neutral_frames += 1
                if self.shake_neutral_frames >= self.REARM_NEUTRAL_FRAMES and self._cooldown_ready(now):
                    self.shake_armed = True
                    self.shake_neutral_frames = 0
                    self.yaw_history.clear()
            else:
                self.shake_neutral_frames = 0

        if not self.armed:
            if neutral:
                self.neutral_frames += 1
                if self.neutral_frames >= self.REARM_NEUTRAL_FRAMES and self._cooldown_ready(now):
                    self.armed = True
                    self.neutral_frames = 0
                    self._clear_motion()
            else:
                self.neutral_frames = 0
            return None

        if not self._cooldown_ready(now):
            return None

        if abs(pitch) >= self.PITCH_THRESHOLD and abs(roll) <= 0.16 and abs(yaw) <= 0.10:
            sign = -1 if pitch < 0 else 1
            if sign == self.pitch_sign:
                self.pitch_frames += 1
            else:
                self.pitch_sign = sign
                self.pitch_frames = 1
            self.pitch_peak_abs = max(self.pitch_peak_abs, abs(pitch))
            if self.pitch_frames >= self.PITCH_STABLE_FRAMES:
                return self._emit(
                    "NOD",
                    now,
                    {"pitch_peak_abs": round(self.pitch_peak_abs, 4), "stable_frames": self.pitch_frames},
                )
        else:
            self.pitch_sign = 0
            self.pitch_frames = 0
            self.pitch_peak_abs = 0.0

        if (
            abs(roll) >= self.TILT_THRESHOLD
            and abs(pitch) <= self.TILT_MAX_PITCH
            and abs(yaw) <= self.TILT_MAX_YAW
        ):
            sign = -1 if roll < 0 else 1
            if sign == self.tilt_sign:
                self.tilt_frames += 1
            else:
                self.tilt_sign = sign
                self.tilt_frames = 1
            if self.tilt_frames >= self.TILT_STABLE_FRAMES:
                return self._emit(
                    "TILT_LEFT" if sign < 0 else "TILT_RIGHT",
                    now,
                    {"roll": round(roll, 4), "stable_frames": self.tilt_frames},
                )
        else:
            self.tilt_sign = 0
            self.tilt_frames = 0
        return None

    def _emit(self, gesture: str, now: float, evidence: dict[str, float | int] | None = None) -> str:
        self.last_emitted = now
        self.last_evidence = evidence or {}
        self.armed = False
        if gesture == "SHAKE":
            self.shake_armed = False
            self.shake_neutral_frames = 0
        self.neutral_frames = 0
        self._clear_motion()
        return gesture

    def _clear_motion(self) -> None:
        self.tilt_sign = 0
        self.tilt_frames = 0
        self.pitch_sign = 0
        self.pitch_frames = 0
        self.pitch_peak_abs = 0.0
        self._clear_yaw()

    def _clear_yaw(self) -> None:
        self.yaw_history.clear()

    def _yaw_crosses_neutral(self) -> bool:
        return bool(self.yaw_history) and (
            min(self.yaw_history) <= -self.NEUTRAL_YAW
            and max(self.yaw_history) >= self.NEUTRAL_YAW
        )

    def _cooldown_ready(self, now: float) -> bool:
        return now - self.last_emitted >= self.cooldown_seconds

    def _tilt_gate(self, now: float) -> str:
        """Explain the existing tilt gates using only derived pose categories."""
        if self.tilt_blocked_axes is None:
            return "no_pose"
        if not self.armed:
            if self.neutral_frames >= self.REARM_NEUTRAL_FRAMES and not self._cooldown_ready(now):
                return "cooldown"
            return "waiting_for_neutral"
        if not self._cooldown_ready(now):
            return "cooldown"
        if self.tilt_direction is None:
            return "waiting_for_tilt"
        if "pitch" in self.tilt_blocked_axes:
            return "pitch_outside_range"
        if "yaw" in self.tilt_blocked_axes:
            return "yaw_outside_range"
        return "holding_tilt"

    def trace_status(self, now: float | None = None) -> dict[str, Any]:
        """Expose derived detector state without retaining face landmarks."""
        now = time.monotonic() if now is None else now
        candidate = None
        stable_frames = 0
        if self.pitch_frames:
            candidate, stable_frames = "NOD", self.pitch_frames
        elif self.tilt_frames:
            candidate = "TILT_LEFT" if self.tilt_sign < 0 else "TILT_RIGHT"
            stable_frames = self.tilt_frames
        elif self.shake_armed and self._yaw_crosses_neutral():
            candidate = "SHAKE"
            stable_frames = len(self.yaw_history)
        return {
            "candidate": candidate,
            "stable_frames": stable_frames,
            "armed": self.armed,
            "shake_armed": self.shake_armed,
            "neutral_frames": min(self.neutral_frames, self.REARM_NEUTRAL_FRAMES),
            "neutral_frames_required": self.REARM_NEUTRAL_FRAMES,
            "neutral_axes_outside": None if self.neutral_axes_outside is None else list(self.neutral_axes_outside),
            "tilt_gate": self._tilt_gate(now),
            "tilt_direction": self.tilt_direction,
            "tilt_blocked_axes": list(self.tilt_blocked_axes or []),
            "tilt_frames": self.tilt_frames,
            "tilt_frames_required": self.TILT_STABLE_FRAMES,
            "cooldown_remaining": round(max(0.0, self.cooldown_seconds - (now - self.last_emitted)), 3),
            "evidence": dict(self.last_evidence),
        }

    @classmethod
    def _is_neutral(cls, pose: tuple[float, float, float]) -> bool:
        roll, pitch, yaw = pose
        return (
            abs(roll) <= cls.NEUTRAL_ROLL
            and abs(pitch) <= cls.NEUTRAL_PITCH
            and abs(yaw) <= cls.NEUTRAL_YAW
        )


class ScenarioInput:
    """Feeds deterministic commands and gestures from a per-run scenario file."""

    def __init__(self, scenario_path: str | None) -> None:
        self.actions: list[dict[str, str]] = []
        self.index = 0
        self.expected_terminal = "return_to_base"
        self.expected_final_position = "S"
        if scenario_path:
            payload = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
            self.actions = list(payload.get("actions", []))
            self.expected_terminal = str(payload.get("expected_terminal", self.expected_terminal))
            self.expected_final_position = str(payload.get("expected_final_position", self.expected_final_position)).upper()

    def peek_action(self) -> dict[str, str] | None:
        if self.index >= len(self.actions):
            return None
        return self.actions[self.index]

    def next_action(self) -> dict[str, str] | None:
        action = self.peek_action()
        if action is not None:
            self.index += 1
        return action


class TranscriptReplayRecognizer:
    """Timed, already-transcribed commands for a clearly marked demo run."""

    def __init__(
        self,
        schedule_path: str,
        *,
        device: int | str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        del device
        payload = json.loads(Path(schedule_path).read_text(encoding="utf-8"))
        self.actions = sorted(list(payload.get("transcripts", [])), key=lambda item: float(item.get("at_seconds", 0.0)))
        self.index = 0
        self.clock = clock
        self.started_at = clock()
        self.device_name = "transcript replay - no microphone audio"
        self.sample_rate = 0
        self.last_trace: dict[str, Any] | None = None
        self.ready = True

    def poll(self) -> str | None:
        if self.index >= len(self.actions):
            return None
        action = self.actions[self.index]
        if self.clock() - self.started_at < float(action.get("at_seconds", 0.0)):
            return None
        self.index += 1
        transcript = str(action.get("transcript", "")).strip()
        command = normalise_command(transcript)
        confidence = float(action.get("confidence", 1.0))
        accepted = bool(command and confidence >= float(action.get("threshold", 0.65)))
        self.last_trace = {
            "transcript": transcript,
            "command": command,
            "confidence": round(confidence, 4),
            "threshold": float(action.get("threshold", 0.65)),
            "accepted": accepted,
            "reason": "accepted" if accepted else ("outside_bounded_grammar" if not command else "low_confidence"),
            "source": "transcript_replay",
        }
        return str(command) if accepted else None

    def close(self) -> None:
        self.ready = False


class GestureEventReplayRecognizer:
    """Replay gesture categories previously emitted by the production classifier.

    The manifest is created by replaying a consented video through
    ``MediaPipeGestureRecognizer``.  Webots can therefore consume the exact
    classified events and recorded timestamps without needing OpenCV or
    MediaPipe inside the deterministic Docker image.
    """

    def __init__(
        self,
        manifest_path: str,
        *args: Any,
        clock: Callable[[], float] = time.monotonic,
        **kwargs: Any,
    ) -> None:
        del args, kwargs
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if not payload.get("uses_production_classifier"):
            raise ValueError("gesture replay manifest was not produced by the production classifier")
        self.actions = sorted(
            list(payload.get("gesture_events", [])),
            key=lambda item: float(item.get("time_seconds", 0.0)),
        )
        if not self.actions:
            raise ValueError("gesture replay manifest contains no gesture events")
        self.index = 0
        self.clock = clock
        self.started_at = clock()
        self.ready = True
        self.face_present = True
        self.calibrated = bool(payload.get("calibration_completed"))
        self.camera_index = "classified gesture-video replay"
        self.camera_backend = "production_classifier_manifest"
        self.resolution: tuple[int, int] = ()
        self.last_gesture: str | None = None
        self.last_trace: dict[str, Any] | None = None

    def poll(self) -> str | None:
        if self.index >= len(self.actions):
            return None
        action = self.actions[self.index]
        elapsed = self.clock() - self.started_at
        if elapsed < float(action.get("time_seconds", 0.0)):
            return None
        self.index += 1
        gesture = str(action.get("gesture", "")).upper().strip()
        if gesture not in {"TILT_LEFT", "TILT_RIGHT", "NOD", "SHAKE"}:
            raise ValueError(f"unbounded replay gesture: {gesture}")
        self.last_gesture = gesture
        self.last_trace = {
            "source": "classified_gesture_video_replay",
            "gesture": gesture,
            "scheduled_seconds": round(float(action.get("time_seconds", 0.0)), 3),
            "section": action.get("section"),
            "source_time_seconds": action.get("source_time_seconds"),
            "evidence": dict(action.get("evidence", {})),
            "event_index": self.index - 1,
        }
        return gesture

    def trace_status(self) -> dict[str, Any]:
        return {
            "source": "classified_gesture_video_replay",
            "calibration_progress": 1.0 if self.calibrated else 0.0,
            "calibrated": self.calibrated,
            "face_present": self.face_present,
            "last_gesture": self.last_gesture,
            "last_event": self.last_trace,
            "events_consumed": self.index,
            "events_total": len(self.actions),
            "finished": self.index >= len(self.actions),
        }

    def consume_preview_frame(self) -> None:
        return None

    def close(self) -> None:
        self.ready = False


class VoskCommandRecognizer:
    """Bounded local Vosk recognition with an in-memory, size-limited buffer."""

    grammar = (
        '["start", "start a", "start b", "pickup", "pick up", "drop off", "return", "stop", '
        '"go to a", "go to alpha", "go to b", "go to c", "go to s", "forward", "reverse", '
        '"left", "right", "turn left", "turn right", "continue", "alternative route"]'
    )

    def __init__(
        self,
        model_path: str,
        sample_rate: int = 16000,
        confidence_threshold: float = 0.65,
        device: int | str | None = None,
        readiness_timeout: float = 1.5,
    ) -> None:
        try:
            import sounddevice as sd  # type: ignore
            from vosk import KaldiRecognizer, Model  # type: ignore
        except ImportError as error:  # pragma: no cover - hardware dependency
            raise RuntimeError("Live voice input needs local vosk and sounddevice packages.") from error
        if not Path(model_path).is_dir():
            raise RuntimeError(f"Local Vosk model directory was not found: {model_path}")
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=8)
        self._stream_error: str | None = None
        self._last_callback_at = time.monotonic()
        self.callback_count = 0
        self.audio_bytes_received = 0
        self.last_audio_peak = 0
        self.last_partial_transcript = ""
        self.callback_timeout = max(2.0, readiness_timeout * 2)
        self.confidence_threshold = confidence_threshold
        self.last_trace: dict[str, Any] | None = None
        self.last_final_trace: dict[str, Any] | None = None
        self.final_decision_count = 0
        try:
            device_info = sd.query_devices(device, "input")
        except Exception as error:
            raise RuntimeError(f"No usable microphone input was found: {error}") from error
        self.device_name = str(device_info.get("name", device if device is not None else "default"))
        rates = [int(sample_rate)]
        default_rate = int(float(device_info.get("default_samplerate", sample_rate)))
        if default_rate not in rates:
            rates.append(default_rate)
        model = Model(model_path)
        failures: list[str] = []
        self._stream = None
        self._recognizer = None
        self.sample_rate = sample_rate
        for candidate_rate in rates:
            stream = None
            try:
                self._queue = queue.Queue(maxsize=8)
                recognizer = KaldiRecognizer(model, candidate_rate, self.grammar)
                # Confidence filtering depends on Vosk's per-word ``result``
                # array. Some Vosk builds emit only ``text`` unless word output
                # is enabled explicitly, which would otherwise make every live
                # command appear to have zero confidence.
                recognizer.SetWords(True)
                if hasattr(recognizer, "SetPartialWords"):
                    recognizer.SetPartialWords(True)
                stream = sd.RawInputStream(
                    device=device,
                    samplerate=candidate_rate,
                    blocksize=max(800, candidate_rate // 4),
                    dtype="int16",
                    channels=1,
                    callback=self._capture,
                )
                stream.start()
                deadline = time.monotonic() + readiness_timeout
                while time.monotonic() < deadline and self._queue.empty() and stream.active:
                    time.sleep(0.025)
                if self._queue.empty() or not stream.active:
                    stream.stop()
                    stream.close()
                    raise RuntimeError("stream opened but delivered no audio callback data")
                self._queue.get_nowait()  # Prove delivery, then discard the transient readiness sample.
                self._recognizer = recognizer
                self._stream = stream
                self.sample_rate = candidate_rate
                break
            except Exception as error:
                failures.append(f"{candidate_rate} Hz: {error}")
                if stream is not None:
                    try:
                        stream.stop()
                    except Exception:
                        pass
                    try:
                        stream.close()
                    except Exception:
                        pass
        if self._stream is None or self._recognizer is None:
            raise RuntimeError(f"Microphone did not become ready ({'; '.join(failures)})")

    def _capture(self, data: Any, _frames: int, _time: Any, _status: Any) -> None:
        self._last_callback_at = time.monotonic()
        payload = bytes(data)
        self.callback_count += 1
        self.audio_bytes_received += len(payload)
        try:
            samples = memoryview(payload).cast("h")
            current_peak = max((abs(int(sample)) for sample in samples), default=0)
            self.last_audio_peak = max(current_peak, int(self.last_audio_peak * 0.70))
        except (TypeError, ValueError):
            self.last_audio_peak = 0
        if _status:
            self._stream_error = str(_status)
        try:
            self._queue.put_nowait(payload)
        except queue.Full:
            # Drop stale samples rather than retaining audio or delaying a stop.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(payload)
            except queue.Empty:
                pass

    def poll(self) -> str | None:
        """Return one accepted grammar command, discarding all processed samples."""
        if self._stream is None or not self._stream.active:
            raise RuntimeError(self._stream_error or "Microphone stream disconnected.")
        if time.monotonic() - self._last_callback_at > self.callback_timeout:
            raise RuntimeError("Microphone stream stopped delivering callback data.")
        for _ in range(2):
            try:
                audio = self._queue.get_nowait()
            except queue.Empty:
                return None
            if not self._recognizer.AcceptWaveform(audio):
                try:
                    partial = str(json.loads(self._recognizer.PartialResult()).get("partial", "")).strip()
                except (ValueError, AttributeError):
                    partial = ""
                if partial:
                    self.last_partial_transcript = partial
                    self.last_trace = {
                        "transcript": partial,
                        "command": normalise_command(partial),
                        "confidence": 0.0,
                        "accepted": False,
                        "reason": "partial_transcript",
                        "source": "local_vosk_microphone",
                    }
                continue
            self.last_trace = parse_vosk_decision(self._recognizer.Result(), self.confidence_threshold)
            self.last_trace["source"] = "local_vosk_microphone"
            self.last_trace["microphone_callbacks"] = self.callback_count
            self.last_trace["microphone_audio_peak"] = self.last_audio_peak
            if self.last_trace["transcript"]:
                # A later partial or silence can arrive in this same poll.
                # Retain the last spoken final decision so rejection evidence
                # remains visible without retaining any microphone audio.
                self.final_decision_count += 1
                self.last_trace["decision_id"] = self.final_decision_count
                self.last_final_trace = dict(self.last_trace)
            if self.last_trace["accepted"]:
                return str(self.last_trace["command"])
        return None

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
            finally:
                self._stream.close()
            self._stream = None

    @property
    def ready(self) -> bool:
        return self._stream is not None and bool(self._stream.active)


class MediaPipeGestureRecognizer:
    """Calibrated, smoothed head-gesture recogniser using transient webcam frames."""

    CALIBRATION_FRAMES = 45

    def __init__(self, camera_index: int | str = "auto", cooldown_seconds: float = 0.8) -> None:
        try:
            import cv2  # type: ignore
            import mediapipe as mp  # type: ignore
        except ImportError as error:  # pragma: no cover - hardware dependency
            raise RuntimeError("Live gesture input needs local mediapipe and opencv packages.") from error
        self.cv2 = cv2
        self.capture, self.camera_index, self.camera_backend, prefetched = self._open_camera(camera_index)
        self._prefetched_frames: deque[Any] = deque(prefetched)
        self.frame_read_failures = 0
        first_frame = prefetched[0]
        self.resolution = (int(first_frame.shape[1]), int(first_frame.shape[0]))
        try:
            self.face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5
            )
        except Exception:
            self.capture.release()
            raise
        self.calibration: list[tuple[float, float, float]] = []
        self.neutral: tuple[float, float, float] | None = None
        self.cooldown_seconds = cooldown_seconds
        self.detector = GestureStateDetector(cooldown_seconds)
        self.face_present = False
        self.relative_pose: tuple[float, float, float] | None = None
        self.face_box: tuple[float, float, float, float] | None = None
        self.last_gesture: str | None = None
        self.last_gesture_at: float | None = None
        self._preview_frame: Any | None = None

    def _open_camera(self, requested: int | str) -> tuple[Any, int | str, str, list[Any]]:
        numeric = isinstance(requested, int) or (isinstance(requested, str) and requested.strip().isdigit())
        is_auto = isinstance(requested, str) and requested.strip().lower() == "auto"
        sources: list[int | str]
        if is_auto:
            sources = list(range(5))
        elif numeric:
            sources = [int(requested)]
        else:
            sources = [requested]
        live_source = is_auto or numeric
        backends: list[int | None] = [None]
        if live_source and sys.platform == "win32":
            preferred = [getattr(self.cv2, "CAP_DSHOW", None), getattr(self.cv2, "CAP_MSMF", None), None]
            backends = []
            for backend in preferred:
                if backend not in backends:
                    backends.append(backend)
        failures: list[str] = []
        for source in sources:
            for backend in backends:
                backend_names = {
                    getattr(self.cv2, "CAP_DSHOW", -1): "DSHOW",
                    getattr(self.cv2, "CAP_MSMF", -2): "MSMF",
                }
                backend_label = backend_names.get(backend, "default")
                capture = self.cv2.VideoCapture(source) if backend is None else self.cv2.VideoCapture(source, backend)
                try:
                    if not capture.isOpened():
                        failures.append(f"source {source}/{backend_label}: did not open")
                        capture.release()
                        continue
                    try:
                        backend_label = str(capture.getBackendName())
                    except Exception:
                        backend_label = str(backend if backend is not None else "default")
                    frames: list[Any] = []
                    deadline = time.monotonic() + (1.5 if live_source else 3.0)
                    required_frames = 3 if live_source else 1
                    while time.monotonic() < deadline and len(frames) < required_frames:
                        ok, frame = capture.read()
                        if ok and frame is not None and getattr(frame, "size", 0):
                            frames.append(frame)
                    if len(frames) >= required_frames:
                        return capture, source, backend_label, frames
                    failures.append(f"source {source}/{backend_label}: opened but delivered no stable frames")
                except Exception as error:
                    failures.append(f"source {source}/{backend_label}: {error}")
                capture.release()
        raise RuntimeError(f"No usable webcam delivered frames ({'; '.join(failures)})")

    def _pose(self, landmarks: Any) -> tuple[float, float, float]:
        left, right, nose = landmarks[33], landmarks[263], landmarks[1]
        jaw_left, jaw_right = landmarks[234], landmarks[454]
        eye_x, eye_y = (left.x + right.x) / 2, (left.y + right.y) / 2
        # MediaPipe normalizes x and y by different image dimensions. Put
        # both in image-width units before measuring the physical roll angle.
        aspect_y = self.resolution[1] / self.resolution[0]
        roll = math.atan2((right.y - left.y) * aspect_y, right.x - left.x)
        cosine, sine = math.cos(roll), math.sin(roll)
        nose_x, nose_y = nose.x - eye_x, (nose.y - eye_y) * aspect_y
        jaw_x = jaw_right.x - jaw_left.x
        jaw_y = (jaw_right.y - jaw_left.y) * aspect_y
        # Measure nose displacement and jaw width along the eye line. A pure
        # ear-to-shoulder tilt must not invent yaw and reject itself at the
        # tilt's yaw gate. Convert pitch back to its existing upright scale.
        width = max(abs(jaw_x * cosine + jaw_y * sine), 1e-4)
        pitch = (-nose_x * sine + nose_y * cosine) / aspect_y / width
        yaw = (nose_x * cosine + nose_y * sine) / width
        return roll, pitch, yaw

    def poll(self, now: float | None = None) -> str | None:
        if self._prefetched_frames:
            frame = self._prefetched_frames.popleft()
            ok = True
        else:
            ok, frame = self.capture.read()
        if not ok or frame is None or not getattr(frame, "size", 0):
            self.face_present = False
            self.relative_pose = None
            self.face_box = None
            self._preview_frame = None
            self.detector.face_lost()
            self.frame_read_failures += 1
            if self.frame_read_failures >= 3:
                raise RuntimeError("Camera stopped delivering frames.")
            return None
        self.frame_read_failures = 0
        # Keep at most one transient frame. It is transferred to the dashboard
        # and cleared by consume_preview_frame(); no frame is written to disk.
        self._preview_frame = frame
        result = self.face_mesh.process(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB))
        if not result.multi_face_landmarks:
            self.face_present = False
            self.relative_pose = None
            self.face_box = None
            self.detector.face_lost()
            return None  # Absent face is deliberately not treated as a command.
        self.face_present = True
        landmarks = result.multi_face_landmarks[0].landmark
        pose = self._pose(landmarks)
        xs = [float(point.x) for point in landmarks]
        ys = [float(point.y) for point in landmarks]
        self.face_box = (max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys)))
        if self.neutral is None:
            self.calibration.append(pose)
            self.relative_pose = None
            if len(self.calibration) >= self.CALIBRATION_FRAMES:
                self.neutral = tuple(sum(values[i] for values in self.calibration) / len(self.calibration) for i in range(3))
            return None
        relative_pose = tuple(pose[i] - self.neutral[i] for i in range(3))
        self.relative_pose = relative_pose
        gesture = self.detector.update(relative_pose, now)
        if gesture:
            self.last_gesture = gesture
            self.last_gesture_at = time.monotonic() if now is None else now
        return gesture

    def close(self) -> None:
        self._preview_frame = None
        self.capture.release()
        self.face_mesh.close()

    def consume_preview_frame(self) -> Any | None:
        """Transfer ownership of the latest transient BGR frame."""
        frame = self._preview_frame
        self._preview_frame = None
        return frame

    def trace_status(self) -> dict[str, Any]:
        pose = self.relative_pose
        detector = self.detector.trace_status()
        return {
            "calibration_progress": round(min(1.0, len(self.calibration) / self.CALIBRATION_FRAMES), 3),
            "pose": None if pose is None else [round(float(value), 4) for value in pose],
            "face_box": None if self.face_box is None else [round(value, 4) for value in self.face_box],
            "last_gesture": self.last_gesture,
            "last_gesture_at": self.last_gesture_at,
            **detector,
        }

    @property
    def ready(self) -> bool:
        return self.capture.isOpened() and self.frame_read_failures < 3

    @property
    def calibrated(self) -> bool:
        return self.neutral is not None


class LocalMultimodalInput:
    """Combines speech and gestures with independent reconnect supervision."""

    def __init__(
        self,
        vosk_model_path: str,
        camera_index: int | str = "auto",
        microphone_device: int | str | None = None,
        retry_interval: float = 3.0,
        strict: bool = True,
        voice_factory: Callable[..., Any] = VoskCommandRecognizer,
        gesture_factory: Callable[..., Any] = MediaPipeGestureRecognizer,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.vosk_model_path = vosk_model_path
        self.camera_index = camera_index
        self.microphone_device = microphone_device
        self.retry_interval = retry_interval
        self.voice_factory = voice_factory
        self.gesture_factory = gesture_factory
        self.clock = clock
        self.voice: Any | None = None
        self.gesture: Any | None = None
        self.voice_error: str | None = None
        self.gesture_error: str | None = None
        self.next_voice_retry = float("-inf")
        self.next_gesture_retry = float("-inf")
        self.voice_reconnects = 0
        self.gesture_reconnects = 0
        self.active_input_source = "NONE"
        self.active_input_detail = "waiting for input"
        self.active_input_at: float | None = None
        try:
            self._connect_missing(force=True)
            if strict and not self.ready:
                errors = "; ".join(filter(None, [self.voice_error, self.gesture_error]))
                raise RuntimeError(errors or "Live microphone and camera are not ready.")
        except BaseException:
            # Construction may be interrupted after one adapter has opened;
            # the caller cannot close this instance until __init__ returns.
            self.close()
            raise

    def _connect_missing(self, force: bool = False) -> None:
        now = self.clock()
        if self.voice is not None and not getattr(self.voice, "ready", True):
            self._disconnect_voice(RuntimeError("microphone adapter is no longer ready"))
        if self.gesture is not None and not getattr(self.gesture, "ready", True):
            self._disconnect_gesture(RuntimeError("camera adapter is no longer ready"))
        if self.voice is None and (force or now >= self.next_voice_retry):
            try:
                self.voice = self.voice_factory(
                    self.vosk_model_path,
                    device=self.microphone_device,
                )
                self.voice_error = None
                self.voice_reconnects += 1
            except Exception as error:
                self.voice_error = f"microphone: {error}"
                self.next_voice_retry = now + self.retry_interval
        if self.gesture is None and (force or now >= self.next_gesture_retry):
            try:
                self.gesture = self.gesture_factory(self.camera_index)
                self.gesture_error = None
                self.gesture_reconnects += 1
            except Exception as error:
                self.gesture_error = f"camera: {error}"
                self.next_gesture_retry = now + self.retry_interval

    @staticmethod
    def _close_adapter(adapter: Any | None) -> None:
        if adapter is not None:
            try:
                adapter.close()
            except Exception:
                pass

    def _disconnect_voice(self, error: Exception) -> None:
        self._close_adapter(self.voice)
        self.voice = None
        self.voice_error = f"microphone: {error}"
        self.next_voice_retry = self.clock() + self.retry_interval

    def _disconnect_gesture(self, error: Exception) -> None:
        self._close_adapter(self.gesture)
        self.gesture = None
        self.gesture_error = f"camera: {error}"
        self.next_gesture_retry = self.clock() + self.retry_interval

    def poll(self) -> dict[str, str] | None:
        self._connect_missing()
        action: dict[str, str] = {}
        recognised_command: str | None = None
        recognised_gesture: str | None = None
        if self.voice is not None:
            try:
                command = self.voice.poll()
                if command:
                    action["command"] = command
                    recognised_command = command
            except Exception as error:
                self._disconnect_voice(error)
        if self.gesture is not None:
            try:
                gesture = self.gesture.poll()
                if gesture:
                    action["gesture"] = gesture
                    recognised_gesture = gesture
                    replay_trace = getattr(self.gesture, "last_trace", None)
                    if isinstance(replay_trace, dict):
                        action["gesture_source"] = str(replay_trace.get("source") or "gesture_adapter")
                        action["gesture_section"] = str(replay_trace.get("section") or "")
                        action["gesture_scheduled_seconds"] = str(replay_trace.get("scheduled_seconds") or "")
                        action["gesture_source_time_seconds"] = str(replay_trace.get("source_time_seconds") or "")
            except Exception as error:
                self._disconnect_gesture(error)
        # A global safety gesture remains highest priority. Otherwise a voice
        # command is the primary decision when microphone and camera produce
        # input in the same poll; the gesture is still retained for route
        # selection or nod confirmation.
        if recognised_gesture == "SHAKE":
            self.active_input_source = "CAMERA"
            self.active_input_detail = "SHAKE (safety stop)"
            self.active_input_at = self.clock()
        elif recognised_command:
            self.active_input_source = "MICROPHONE"
            self.active_input_detail = recognised_command
            self.active_input_at = self.clock()
        elif recognised_gesture:
            self.active_input_source = "CAMERA"
            self.active_input_detail = recognised_gesture
            self.active_input_at = self.clock()
        return action or None

    @property
    def face_present(self) -> bool:
        return bool(self.gesture is not None and self.gesture.face_present)

    @property
    def ready(self) -> bool:
        return bool(
            self.voice is not None
            and self.gesture is not None
            and getattr(self.voice, "ready", True)
            and getattr(self.gesture, "ready", True)
        )

    @property
    def voice_ready(self) -> bool:
        return bool(self.voice is not None and getattr(self.voice, "ready", True))

    @property
    def gesture_ready(self) -> bool:
        return bool(self.gesture is not None and getattr(self.gesture, "ready", True))

    @property
    def gesture_calibrated(self) -> bool:
        return bool(self.gesture is not None and getattr(self.gesture, "calibrated", False))

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "voice_ready": self.voice_ready,
            "camera_ready": self.gesture_ready,
            "face_present": self.face_present,
            "gesture_calibrated": self.gesture_calibrated,
            "voice_error": self.voice_error,
            "camera_error": self.gesture_error,
            "voice_reconnects": self.voice_reconnects,
            "camera_reconnects": self.gesture_reconnects,
        }

    def trace_status(self) -> dict[str, Any]:
        """Return JSON-safe technical telemetry; camera pixels stay separate."""
        trace = self.status()
        gesture_trace: dict[str, Any] = {}
        if self.gesture is not None:
            trace_provider = getattr(self.gesture, "trace_status", None)
            if callable(trace_provider):
                gesture_trace = trace_provider()
        trace.update(
            microphone_name=getattr(self.voice, "device_name", None),
            microphone_sample_rate=getattr(self.voice, "sample_rate", None),
            microphone_callbacks=getattr(self.voice, "callback_count", 0),
            microphone_audio_bytes=getattr(self.voice, "audio_bytes_received", 0),
            microphone_audio_peak=getattr(self.voice, "last_audio_peak", 0),
            microphone_partial=getattr(self.voice, "last_partial_transcript", ""),
            camera_index=getattr(self.gesture, "camera_index", None),
            camera_backend=getattr(self.gesture, "camera_backend", None),
            camera_resolution=list(getattr(self.gesture, "resolution", ())) or None,
            active_input_source=self.active_input_source,
            active_input_detail=self.active_input_detail,
            active_input_at=self.active_input_at,
            voice_decision=None if self.voice is None else getattr(self.voice, "last_trace", None),
            voice_final_decision=None if self.voice is None else getattr(self.voice, "last_final_trace", None),
            gesture_trace=gesture_trace,
        )
        return trace

    def consume_preview_frame(self) -> Any | None:
        if self.gesture is None:
            return None
        consumer = getattr(self.gesture, "consume_preview_frame", None)
        return consumer() if consumer else None

    def close(self) -> None:
        self._close_adapter(self.voice)
        self._close_adapter(self.gesture)
        self.voice = None
        self.gesture = None
