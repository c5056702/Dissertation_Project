"""Automatic, non-recording OpenCV dashboard for live host operation."""

from __future__ import annotations

from collections import deque
import math
import time
from typing import Any, Callable

import numpy as np

from route_feedback import MOVING_STATES, pending_route_destination, route_status_text


class DashboardAction:
    STOP = "STOP"
    RESET = "RESET"


class LiveTraceDashboard:
    """Display one transient camera frame plus JSON-safe controller telemetry."""

    WIDTH = 1280
    HEIGHT = 760
    PREVIEW = (20, 66, 650, 426)
    STOP_BUTTON = (990, 682, 1115, 735)
    RESET_BUTTON = (1130, 682, 1260, 735)

    BG = (24, 27, 32)
    PANEL = (36, 41, 48)
    WHITE = (238, 241, 245)
    GREY = (145, 153, 164)
    GREEN = (91, 205, 145)
    AMBER = (58, 190, 245)
    RED = (85, 92, 235)
    BLUE = (235, 175, 75)

    def __init__(
        self,
        cv2_module: Any | None = None,
        *,
        window_name: str = "E-puck Live Input and Traceability",
        fps: float = 8.0,
        show_window: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if cv2_module is None:
            import cv2 as cv2_module  # type: ignore
        self.cv2 = cv2_module
        self.window_name = window_name
        self.interval = 1.0 / max(1.0, fps)
        self.show_window = show_window
        self.clock = clock
        self.created = False
        self.closed = False
        self._close_stop_queued = False
        self.last_render_at = float("-inf")
        self._pending_frame: Any | None = None
        self._latest_snapshot: dict[str, Any] = {}
        self._actions: deque[str] = deque()
        self.events: deque[str] = deque(maxlen=8)
        self.last_canvas: Any | None = None
        self.render_durations_ms: deque[float] = deque(maxlen=120)

    def _create_window(self) -> None:
        if self.created or not self.show_window:
            return
        self.cv2.namedWindow(self.window_name, self.cv2.WINDOW_NORMAL)
        self.cv2.resizeWindow(self.window_name, self.WIDTH, self.HEIGHT)
        self.cv2.setMouseCallback(self.window_name, self._mouse_callback)
        self.created = True

    @staticmethod
    def _inside(x: int, y: int, box: tuple[int, int, int, int]) -> bool:
        x1, y1, x2, y2 = box
        return x1 <= x <= x2 and y1 <= y <= y2

    def _mouse_callback(self, event: int, x: int, y: int, _flags: int, _data: Any) -> None:
        if event != self.cv2.EVENT_LBUTTONUP:
            return
        self.handle_click(x, y)

    def handle_click(self, x: int, y: int) -> str | None:
        """Queue a tested dashboard action from a screen coordinate."""
        action = None
        if self._inside(x, y, self.STOP_BUTTON):
            action = DashboardAction.STOP
        elif self._inside(x, y, self.RESET_BUTTON):
            action = DashboardAction.RESET
        if action:
            self._actions.append(action)
        return action

    def poll_action(self) -> str | None:
        return self._actions.popleft() if self._actions else None

    def record_event(self, entry: dict[str, Any]) -> None:
        """Keep a short, technical, in-memory event timeline."""
        if entry.get("event") == "gesture_detection_status":
            return  # Frequent posture diagnostics must not bury route choices.
        if entry.get("event") == "gesture_recognised" and str(entry.get("gesture", "")).startswith("TILT_"):
            return  # The following route_selection event includes its result.
        name = str(entry.get("event", "event")).replace("_", " ")
        detail = entry.get("source") or entry.get("command") or entry.get("route") or entry.get("reason")
        event_time = float(entry.get("time", time.time()))
        if event_time < 1_000_000_000:
            timestamp = f"T+{int(event_time) // 60:02d}:{int(event_time) % 60:02d}"
        else:
            timestamp = time.strftime("%H:%M:%S", time.localtime(event_time))
        if entry.get("event") in {"route_selection", "route_selection_unavailable"}:
            detail = entry.get("message", name)
            if entry.get("event") == "route_selection" and entry.get("selected"):
                detail = (f"{str(entry.get('gesture', 'tilt')).replace('_', ' ')} -> TO {entry.get('destination', '?')}: "
                          f"{str(entry.get('route_choice', '')).upper()} selected")
            self.events.appendleft(f"{timestamp}  {detail}")
        else:
            self.events.appendleft(f"{timestamp}  {name}" + (f" - {detail}" if detail else ""))

    def update(self, snapshot: dict[str, Any], frame: Any | None = None, *, force: bool = False) -> bool:
        """Refresh the dashboard when due and return whether it remains open."""
        self._latest_snapshot = dict(snapshot)
        if frame is not None:
            self._pending_frame = frame
        if self.closed:
            self._pending_frame = None
            return False
        self._create_window()
        now = self.clock()
        if force or now - self.last_render_at >= self.interval:
            started = time.perf_counter()
            self.last_canvas = self.render(self._latest_snapshot, self._pending_frame)
            self._pending_frame = None
            self.last_render_at = now
            self.render_durations_ms.append((time.perf_counter() - started) * 1000.0)
            if self.show_window:
                self.cv2.imshow(self.window_name, self.last_canvas)
        if self.show_window and self.created:
            self.cv2.waitKey(1)
            try:
                visible = self.cv2.getWindowProperty(self.window_name, self.cv2.WND_PROP_VISIBLE)
            except Exception:
                visible = 1
            if visible < 1:
                self.closed = True
                self._pending_frame = None
                if not self._close_stop_queued:
                    self._actions.append(DashboardAction.STOP)
                    self._close_stop_queued = True
        return not self.closed

    def render(self, snapshot: dict[str, Any], frame: Any | None = None) -> Any:
        canvas = np.full((self.HEIGHT, self.WIDTH, 3), self.BG, dtype=np.uint8)
        cv = self.cv2
        cv.putText(canvas, "E-PUCK LIVE INPUT & TRACEABILITY", (20, 36), cv.FONT_HERSHEY_SIMPLEX, 0.82, self.WHITE, 2, cv.LINE_AA)
        session = str(snapshot.get("session_id", "live"))[-8:]
        cv.putText(canvas, f"SESSION {session}", (1060, 34), cv.FONT_HERSHEY_SIMPLEX, 0.46, self.GREY, 1, cv.LINE_AA)

        self._draw_preview(canvas, frame, snapshot)
        self._draw_input_panel(canvas, snapshot)
        self._draw_robot_panel(canvas, snapshot)
        self._draw_next_step(canvas, snapshot)
        self._draw_events(canvas, snapshot)
        self._draw_buttons(canvas)
        return canvas

    def _draw_preview(self, canvas: Any, frame: Any | None, snapshot: dict[str, Any]) -> None:
        cv = self.cv2
        x1, y1, x2, y2 = self.PREVIEW
        width, height = x2 - x1, y2 - y1
        cv.rectangle(canvas, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), self.PANEL, -1)
        if frame is None or not getattr(frame, "size", 0):
            preview = np.full((height, width, 3), (18, 20, 24), dtype=np.uint8)
            cv.putText(preview, "WAITING FOR CAMERA", (165, 175), cv.FONT_HERSHEY_SIMPLEX, 0.72, self.GREY, 2, cv.LINE_AA)
        else:
            source_height, source_width = frame.shape[:2]
            scale = min(width / source_width, height / source_height)
            drawn_width, drawn_height = max(1, int(source_width * scale)), max(1, int(source_height * scale))
            resized = cv.resize(frame, (drawn_width, drawn_height), interpolation=cv.INTER_AREA)
            preview = np.full((height, width, 3), (12, 14, 17), dtype=np.uint8)
            offset_x, offset_y = (width - drawn_width) // 2, (height - drawn_height) // 2
            preview[offset_y:offset_y + drawn_height, offset_x:offset_x + drawn_width] = resized
        gesture_trace = snapshot.get("gesture_trace") or {}
        face_box = gesture_trace.get("face_box")
        if face_box and len(face_box) == 4:
            bx1, by1, bx2, by2 = face_box
            if frame is None or not getattr(frame, "size", 0):
                offset_x = offset_y = 0
                drawn_width, drawn_height = width, height
            p1 = (max(0, min(width - 1, offset_x + int(bx1 * drawn_width))), max(0, min(height - 1, offset_y + int(by1 * drawn_height))))
            p2 = (max(0, min(width - 1, offset_x + int(bx2 * drawn_width))), max(0, min(height - 1, offset_y + int(by2 * drawn_height))))
            cv.rectangle(preview, p1, p2, self.GREEN, 2)
            pose = gesture_trace.get("pose")
            if pose and len(pose) == 3:
                cx, cy = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
                roll, pitch, yaw = (float(value) for value in pose)
                length = 55
                cv.line(preview, (cx, cy), (cx + int(length * math.cos(roll)), cy + int(length * math.sin(roll))), self.BLUE, 3)
                cv.line(preview, (cx, cy), (cx + int(180 * yaw), cy + int(180 * pitch)), self.AMBER, 3)
        canvas[y1:y2, x1:x2] = preview
        cv.rectangle(canvas, (x1 + 10, y1 + 10), (x1 + 205, y1 + 38), (15, 18, 21), -1)
        cv.putText(canvas, "LIVE - NOT RECORDED", (x1 + 18, y1 + 31), cv.FONT_HERSHEY_SIMPLEX, 0.48, self.GREEN, 1, cv.LINE_AA)

    def _draw_input_panel(self, canvas: Any, snapshot: dict[str, Any]) -> None:
        cv = self.cv2
        cv.rectangle(canvas, (680, 66), (1260, 286), self.PANEL, -1)
        cv.putText(canvas, "INPUT DECISIONS", (698, 94), cv.FONT_HERSHEY_SIMPLEX, 0.56, self.WHITE, 1, cv.LINE_AA)
        source = str(snapshot.get("active_input_source") or "NONE").upper()
        source_color = self.BLUE if source == "MICROPHONE" else self.GREEN if source == "CAMERA" else self.GREY
        source_label = "VOICE" if source == "MICROPHONE" else source
        cv.rectangle(canvas, (1015, 73), (1248, 101), (18, 21, 25), -1)
        cv.putText(canvas, f"MODE: {source_label}", (1026, 93), cv.FONT_HERSHEY_SIMPLEX, 0.45, source_color, 1, cv.LINE_AA)
        gesture = snapshot.get("gesture_trace") or {}
        voice = snapshot.get("voice_decision") or {}
        final_voice = snapshot.get("voice_final_decision") or voice
        pose = gesture.get("pose")
        pose_text = "not calibrated" if not pose else f"R {pose[0]:+.3f}  P {pose[1]:+.3f}  Y {pose[2]:+.3f}"
        calibration = int(float(gesture.get("calibration_progress", 0.0)) * 100)
        microphone_name = str(snapshot.get("microphone_name") or "local Vosk microphone")
        microphone_text = (
            "transcript replay; no microphone audio"
            if "replay" in microphone_name.lower()
            else f"{self._ready_text(snapshot.get('voice_ready'))}; level {snapshot.get('microphone_audio_peak', 0)}; callbacks {snapshot.get('microphone_callbacks', 0)}"
        )
        voice_text = str(voice.get("transcript") or snapshot.get("microphone_partial") or "-")
        if voice.get("reason") == "partial_transcript" or (not voice.get("transcript") and snapshot.get("microphone_partial")):
            voice_text = f"hearing: {voice_text}"
        rows = [
            ("Camera", self._ready_text(snapshot.get("camera_ready")), self._ready_color(snapshot.get("camera_ready"))),
            (
                "Microphone",
                microphone_text,
                self._ready_color(snapshot.get("voice_ready")),
            ),
            ("Currently using", str(snapshot.get("active_input_detail") or "waiting for input"), source_color),
            ("Face / calibration", f"{'present' if snapshot.get('face_present') else 'absent'} / {calibration}%", self.GREEN if snapshot.get("face_present") else self.RED),
            ("Head pose", pose_text, self.WHITE),
            ("Gesture", f"last {gesture.get('last_gesture') or '-'}; candidate {gesture.get('candidate') or '-'}", self.AMBER if gesture.get("candidate") else self.WHITE),
            ("Detector", f"{'armed' if gesture.get('armed') else 'rearming'}; cooldown {gesture.get('cooldown_remaining', 0)}s", self.WHITE),
            ("Voice", voice_text, self.AMBER if voice_text.startswith("hearing:") else self.WHITE),
            ("Last speech", str(final_voice.get("transcript") or "-"), self.WHITE),
            ("Decision", self._voice_decision_text(final_voice), self.GREEN if final_voice.get("accepted") else self.GREY),
            ("Recovery", self._recovery_text(snapshot), self.RED if snapshot.get("voice_error") or snapshot.get("camera_error") else self.GREY),
        ]
        self._draw_rows(canvas, rows, 700, 111, 16, label_width=145)

    def _draw_robot_panel(self, canvas: Any, snapshot: dict[str, Any]) -> None:
        cv = self.cv2
        cv.rectangle(canvas, (680, 300), (1260, 568), self.PANEL, -1)
        cv.putText(canvas, "ROBOT, ROUTE & SAFETY", (698, 328), cv.FONT_HERSHEY_SIMPLEX, 0.56, self.WHITE, 1, cv.LINE_AA)
        position = snapshot.get("position") or [0.0, 0.0]
        target = snapshot.get("next_waypoint")
        target_text = "-" if not target else f"({target[0]:.2f}, {target[1]:.2f})"
        safety = str(snapshot.get("last_safety_stop") or "clear")
        safety_color = self.RED if safety != "clear" else self.GREEN
        rows = [
            ("State", str(snapshot.get("state", "-")), self.AMBER if snapshot.get("pending_command") else self.WHITE),
            ("Pending", str(snapshot.get("pending_command") or "-"), self.AMBER if snapshot.get("pending_command") else self.GREY),
            ("Route status", self.selected_route_text(snapshot), self.AMBER if snapshot.get("pending_command") else self.GREEN),
            ("Confirmation", "nod required" if snapshot.get("confirmation_required") else "none", self.AMBER if snapshot.get("confirmation_required") else self.GREY),
            ("Previous route" if snapshot.get("pending_command") else ("Active route" if snapshot.get("active_destination") and snapshot.get("state") in MOVING_STATES | {"PAUSED"} else "Last route"), str(snapshot.get("active_route_name") or snapshot.get("route") or "-"), self.GREY if snapshot.get("pending_command") else self.WHITE),
            ("Origin -> destination", f"{snapshot.get('origin') or '-'} -> {snapshot.get('destination') or '-'}", self.WHITE),
            ("GPS", f"({position[0]:.2f}, {position[1]:.2f})", self.WHITE),
            ("Next waypoint", target_text, self.WHITE),
            ("Distance", "-" if snapshot.get("distance") is None else f"{float(snapshot['distance']):.3f} m", self.WHITE),
            ("Sensor peak", f"{float(snapshot.get('sensor_peak', 0.0)):.1f}", self.WHITE),
            ("Safety", safety, safety_color),
        ]
        self._draw_rows(canvas, rows, 700, 347, 20, label_width=175)

    @staticmethod
    def pending_route_destination(snapshot: dict[str, Any]) -> str | None:
        return pending_route_destination(snapshot)

    @staticmethod
    def selected_route_text(snapshot: dict[str, Any]) -> str:
        return route_status_text(snapshot)

    def _draw_next_step(self, canvas: Any, snapshot: dict[str, Any]) -> None:
        cv = self.cv2
        cv.rectangle(canvas, (680, 580), (1260, 665), self.PANEL, -1)
        cv.putText(canvas, "NEXT STEP", (698, 606), cv.FONT_HERSHEY_SIMPLEX, 0.56, self.WHITE, 1, cv.LINE_AA)
        instruction = self.next_step_instruction(snapshot)
        words = instruction.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > 66 and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        for index, line in enumerate(lines[:2]):
            cv.putText(canvas, line, (700, 631 + index * 23), cv.FONT_HERSHEY_SIMPLEX, 0.45, self.AMBER, 1, cv.LINE_AA)

    @staticmethod
    def next_step_instruction(snapshot: dict[str, Any]) -> str:
        """Return a short, state-aware instruction for the live operator."""
        state = str(snapshot.get("state") or "IDLE").upper()
        gesture = snapshot.get("gesture_trace") or {}
        pending = str(snapshot.get("pending_command") or "")
        route_choice = str(snapshot.get("pending_route_choice") or snapshot.get("route_choice") or "")
        safety = str(snapshot.get("last_safety_stop") or "clear")
        if state == "STOPPED" or safety != "clear":
            return "VOICE MODE: say START to reactivate; the robot will remain still until a destination is given."
        if not snapshot.get("voice_ready"):
            return "Reconnect or allow the microphone; the robot remains stopped while voice input is unavailable."
        if state == "IDLE":
            return "ROBOT LOCKED AT S - say START. It will activate but remain stationary."
        if not snapshot.get("camera_ready"):
            return "Reconnect or allow the camera; the robot remains stopped while gesture input is unavailable."
        if not snapshot.get("face_present"):
            return "Look toward the camera and hold still so your face can be detected safely."
        if float(gesture.get("calibration_progress", 0.0)) < 1.0:
            return "Hold your head neutral and still until camera calibration reaches 100%."
        if snapshot.get("route_selection_error"):
            return str(snapshot["route_selection_error"]) + ". Say a destination, select a route, then NOD."
        moving_states = {"NAVIGATING", "TO_PICKUP", "TO_DROPOFF", "TO_RETURN"}
        if pending or state in moving_states or state == "PAUSED":
            rearm = LiveTraceDashboard.gesture_rearm_instruction(gesture)
            if rearm:
                if state in moving_states:
                    destination = snapshot.get("active_destination") or snapshot.get("destination") or "?"
                    axes = gesture.get("neutral_axes_outside") or []
                    adjustments = {"roll": "straighten your head", "pitch": "level your chin", "yaw": "face the camera"}
                    adjustment = adjustments.get(axes[0], "hold neutral") if len(axes) == 1 else "hold your starting posture"
                    return f"Travelling to {destination}. For next gesture: {adjustment}; hold still to re-arm. Say STOP to stop."
                return rearm
            tilt_help = LiveTraceDashboard.tilt_detection_instruction(gesture, moving=state in moving_states)
            if tilt_help:
                return tilt_help
        if pending:
            if pending.startswith("start ") or pending.startswith("go to "):
                if pending.startswith("start ") and not route_choice:
                    return f"TO {LiveTraceDashboard.pending_route_destination(snapshot)}: LEFT selects shortest; RIGHT selects alternative. Return neutral, then NOD."
                destination = LiveTraceDashboard.pending_route_destination(snapshot)
                if route_choice in {"alternative", "long"}:
                    return f"TO {destination}: ALTERNATIVE selected. NOD to start; TILT LEFT selects shortest. SHAKE stops."
                return f"TO {destination}: SHORTEST selected. NOD to start; TILT RIGHT selects alternative. Return neutral before NOD."
            return f"NOD to confirm {pending.upper()}, or SHAKE your head to cancel and stop."
        if state == "READY":
            return "Say GO TO A, B, C, or S (GO TO ALPHA also selects A). Wait for the destination prompt, then tilt or NOD."
        if state in moving_states:
            return "TILT LEFT/RIGHT: hold ear toward shoulder to pause; neutral, NOD. SHAKE stops. Say GO TO A/B/C/S to change destination."
        if state == "PAUSED":
            return "TILT LEFT/RIGHT: shortest/alternative, then neutral and NOD. Or say CONTINUE, REVERSE, GO TO A/B/C/S, or STOP."
        if state == "AT_PICKUP":
            return "Say PICKUP, DROP OFF, or GO TO A, B, C, or S, then NOD to confirm."
        if state == "AT_DROPOFF":
            return "Say RETURN or GO TO A, B, C, or S, then NOD to confirm."
        return "Say GO TO A, B, C, or S for the next destination, then NOD to confirm."

    @staticmethod
    def gesture_rearm_instruction(gesture: dict[str, Any]) -> str | None:
        """Explain the existing neutral gate without changing recognition."""
        cooldown = float(gesture.get("cooldown_remaining", 0.0))
        if gesture.get("armed", True) and cooldown <= 0.0:
            return None
        axes = gesture.get("neutral_axes_outside")
        adjustments = {"roll": "straighten your head", "pitch": "level your chin", "yaw": "face the camera"}
        if axes:
            steps = ", ".join(adjustments[axis] for axis in axes if axis in adjustments)
            return f"To re-arm: {steps}. Match your starting posture and hold still."
        if axes == []:
            if cooldown > 0.0:
                return f"Head is neutral. Hold still for {cooldown:.1f}s more and wait for the detector to re-arm."
            return "Head is neutral. Keep still briefly until the detector is armed, then make your next gesture."
        return "Return your head to neutral and wait for the camera gesture detector to re-arm."

    @staticmethod
    def tilt_detection_instruction(gesture: dict[str, Any], *, moving: bool) -> str | None:
        """Explain why an armed detector has not yet accepted a tilt."""
        gate = gesture.get("tilt_gate")
        if gate == "waiting_for_tilt" and "roll" in (gesture.get("neutral_axes_outside") or []):
            return "Tilt a little farther, ear toward shoulder, while facing the camera. Hold steady until the tilt is accepted."
        if gate in {"pitch_outside_range", "yaw_outside_range"}:
            axes = gesture.get("tilt_blocked_axes") or []
            if "pitch" in axes and "yaw" in axes:
                return "Tilt seen: keep your chin level and face the camera while moving your ear toward your shoulder. Hold still."
            if gate == "pitch_outside_range":
                return "Tilt seen: keep your chin at its starting height while moving your ear toward your shoulder. Hold still."
            return "Tilt seen: keep looking toward the camera instead of turning your face. Move your ear toward your shoulder."
        if gate == "holding_tilt":
            direction = "LEFT" if gesture.get("tilt_direction") == "TILT_LEFT" else "RIGHT"
            outcome = "robot pauses" if moving else "route is selected"
            return f"{direction} tilt detected: keep it steady until the {outcome}. Then return neutral, wait for armed, and NOD."
        return None

    def _draw_events(self, canvas: Any, snapshot: dict[str, Any]) -> None:
        cv = self.cv2
        cv.rectangle(canvas, (20, 445), (660, 735), self.PANEL, -1)
        cv.putText(canvas, "RECENT TECHNICAL EVENTS", (38, 476), cv.FONT_HERSHEY_SIMPLEX, 0.56, self.WHITE, 1, cv.LINE_AA)
        events = list(self.events) or ["No event transitions yet"]
        events = [f"Now: {self.selected_route_text(snapshot)}", *events]
        for index, event in enumerate(events[:8]):
            text = event if len(event) <= 72 else event[:69] + "..."
            cv.putText(canvas, text, (40, 508 + index * 27), cv.FONT_HERSHEY_SIMPLEX, 0.43, self.GREY, 1, cv.LINE_AA)

    def _draw_buttons(self, canvas: Any) -> None:
        cv = self.cv2
        cv.putText(canvas, "Dashboard controls", (690, 706), cv.FONT_HERSHEY_SIMPLEX, 0.45, self.GREY, 1, cv.LINE_AA)
        for box, color, label in ((self.STOP_BUTTON, self.RED, "STOP"), (self.RESET_BUTTON, self.BLUE, "RESET AT S")):
            x1, y1, x2, y2 = box
            cv.rectangle(canvas, (x1, y1), (x2, y2), color, -1)
            size = cv.getTextSize(label, cv.FONT_HERSHEY_SIMPLEX, 0.52, 2)[0]
            cv.putText(canvas, label, (x1 + (x2 - x1 - size[0]) // 2, y1 + 33), cv.FONT_HERSHEY_SIMPLEX, 0.52, self.WHITE, 2, cv.LINE_AA)

    def _draw_rows(self, canvas: Any, rows: list[tuple[str, str, tuple[int, int, int]]], x: int, y: int, spacing: int, *, label_width: int) -> None:
        cv = self.cv2
        for index, (label, value, color) in enumerate(rows):
            baseline = y + index * spacing
            cv.putText(canvas, label, (x, baseline), cv.FONT_HERSHEY_SIMPLEX, 0.42, self.GREY, 1, cv.LINE_AA)
            cv.putText(canvas, value[:48], (x + label_width, baseline), cv.FONT_HERSHEY_SIMPLEX, 0.43, color, 1, cv.LINE_AA)

    @staticmethod
    def _ready_text(value: Any) -> str:
        return "ready" if value else "waiting / reconnecting"

    def _ready_color(self, value: Any) -> tuple[int, int, int]:
        return self.GREEN if value else self.RED

    @staticmethod
    def _voice_decision_text(voice: dict[str, Any]) -> str:
        if not voice:
            return "-"
        confidence = float(voice.get("confidence", 0.0))
        command = voice.get("command") or "rejected"
        if voice.get("reason") == "low_confidence":
            words = voice.get("word_confidences") or []
            weakest = min(words, key=lambda word: word["confidence"]) if words else None
            detail = f" '{weakest['word']}'" if weakest else ""
            return f"Unclear{detail}: {confidence:.2f}; repeat command"
        return f"{command}; {confidence:.2f}; {voice.get('reason', 'unknown')}"

    @staticmethod
    def _recovery_text(snapshot: dict[str, Any]) -> str:
        error = snapshot.get("camera_error") or snapshot.get("voice_error")
        if error:
            return str(error)
        return f"mic {snapshot.get('voice_reconnects', 0)}; cam {snapshot.get('camera_reconnects', 0)}"

    @property
    def mean_render_ms(self) -> float | None:
        if not self.render_durations_ms:
            return None
        return sum(self.render_durations_ms) / len(self.render_durations_ms)

    def close(self) -> None:
        self._pending_frame = None
        if self.created and self.show_window:
            try:
                self.cv2.destroyWindow(self.window_name)
                self.cv2.waitKey(1)
            except Exception:
                pass
        self.closed = True
