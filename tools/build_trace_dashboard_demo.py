"""Build a consented, derived dashboard demo; the source clip is never packaged."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import cv2


PROJECT = Path(__file__).resolve().parents[1]
CONTROLLER = PROJECT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(CONTROLLER))

from input_adapters import MediaPipeGestureRecognizer, TranscriptReplayRecognizer  # noqa: E402
from live_dashboard import LiveTraceDashboard  # noqa: E402
from model import TaskMachine, WAYPOINTS  # noqa: E402


def build(video: Path, transcripts: Path, output: Path, preview: Path, report_path: Path) -> dict[str, object]:
    if not video.is_file() or not transcripts.is_file():
        raise FileNotFoundError(f"Missing video or transcript fixture: {video}; {transcripts}")
    output.parent.mkdir(parents=True, exist_ok=True)
    preview.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    fixture = json.loads(transcripts.read_text(encoding="utf-8"))
    state_events = sorted(fixture.get("dashboard_state_events", []), key=lambda item: float(item["at_seconds"]))
    reset_at = fixture.get("dashboard_reset_at_seconds")
    current_time = [0.0]
    voice = TranscriptReplayRecognizer(str(transcripts), clock=lambda: current_time[0])
    gesture_input = MediaPipeGestureRecognizer(str(video), cooldown_seconds=0.8)
    dashboard = LiveTraceDashboard(show_window=False, fps=1000.0, clock=lambda: current_time[0])
    machine = TaskMachine()
    capture = gesture_input.capture
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 25.0
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    gesture_events: list[dict[str, object]] = []
    voice_events: list[dict[str, object]] = []
    active_route = None
    reset_emitted = False
    state_event_index = 0
    applied_state_events: list[dict[str, object]] = []
    last_voice_index = 0
    processed = 0
    calibration_completed = False
    active_input_source = "MICROPHONE"
    active_input_detail = "VOICE MODE: waiting for START"

    with tempfile.TemporaryDirectory() as temporary:
        intermediate = Path(temporary) / "dashboard_mjpg.avi"
        writer = cv2.VideoWriter(str(intermediate), cv2.VideoWriter_fourcc(*"MJPG"), fps, (dashboard.WIDTH, dashboard.HEIGHT))
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the dashboard demo intermediate video.")
        try:
            while capture.isOpened() and (total_frames <= 0 or processed < total_frames):
                current_time[0] = processed / fps
                gesture = gesture_input.poll(now=current_time[0])
                position = int(capture.get(cv2.CAP_PROP_POS_FRAMES))
                if position <= processed:
                    break
                processed = position
                current_time[0] = processed / fps
                command = voice.poll()
                voice_changed = False
                if voice.index != last_voice_index:
                    voice_changed = True
                    last_voice_index = voice.index
                    decision = dict(voice.last_trace or {})
                    active_input_source = "MICROPHONE"
                    active_input_detail = str(decision.get("command") or decision.get("transcript") or "voice decision")
                    voice_events.append({"time_seconds": round(current_time[0], 3), **decision})
                    dashboard.record_event({"event": "voice_decision", "time": current_time[0], **decision})
                if command:
                    accepted, status = machine.accept_command(command)
                    dashboard.record_event({"event": "command_recognised", "time": current_time[0], "command": command, "accepted": accepted, "reason": status})
                if gesture:
                    if gesture == "SHAKE" or not voice_changed:
                        active_input_source = "CAMERA"
                        active_input_detail = gesture
                    outcome, request = machine.accept_gesture(gesture, WAYPOINTS.get(machine.current_location, WAYPOINTS["S"]))
                    if request is not None:
                        active_route = request.name
                    gesture_events.append({"time_seconds": round(current_time[0], 3), "gesture": gesture, "outcome": outcome})
                    dashboard.record_event({"event": "gesture_recognised", "time": current_time[0], "source": gesture, "reason": outcome})
                while state_event_index < len(state_events) and current_time[0] >= float(state_events[state_event_index]["at_seconds"]):
                    state_event = dict(state_events[state_event_index])
                    state_event_index += 1
                    if state_event.get("event") != "route_finished":
                        raise ValueError(f"unsupported dashboard state event: {state_event}")
                    transition = machine.route_finished()
                    actual_location = machine.current_location
                    expected_location = state_event.get("expected_location")
                    if expected_location and actual_location != expected_location:
                        raise RuntimeError(
                            f"dashboard route completion mismatch: expected {expected_location}, got {actual_location}"
                        )
                    active_route = None
                    applied = {
                        "time_seconds": round(current_time[0], 3),
                        "transition": transition,
                        "location": actual_location,
                    }
                    applied_state_events.append(applied)
                    dashboard.record_event({"event": transition, "time": current_time[0], "location": actual_location})
                if reset_at is not None and not reset_emitted and current_time[0] >= float(reset_at):
                    machine = TaskMachine()
                    active_route = None
                    reset_emitted = True
                    dashboard.record_event({"event": "dashboard_reset_requested", "time": current_time[0], "source": "RESET AT S"})

                trace = gesture_input.trace_status()
                frame = gesture_input.consume_preview_frame()
                if active_input_source == "CAMERA" and machine.pending_command:
                    displayed_input_detail = "CAMERA MODE: tilt for route choice or NOD to confirm"
                elif active_input_source == "CAMERA" and machine.state.value in {"NAVIGATING", "TO_PICKUP", "TO_DROPOFF", "TO_RETURN"}:
                    displayed_input_detail = "CAMERA MODE: SHAKE stops; a voice command switches mode"
                elif active_input_source == "MICROPHONE" and machine.pending_command:
                    displayed_input_detail = "VOICE MODE: make a gesture to switch back to camera confirmation"
                elif active_input_source == "MICROPHONE" and machine.state.value in {"NAVIGATING", "TO_PICKUP", "TO_DROPOFF", "TO_RETURN"}:
                    displayed_input_detail = "VOICE MODE: listening for destination override or STOP"
                else:
                    displayed_input_detail = active_input_detail
                snapshot = {
                    "session_id": "CONSENTED-DEMO",
                    "camera_ready": gesture_input.ready,
                    "voice_ready": True,
                    "microphone_name": voice.device_name,
                    "face_present": gesture_input.face_present,
                    "gesture_trace": trace,
                    "voice_decision": voice.last_trace,
                    "active_input_source": active_input_source,
                    "active_input_detail": displayed_input_detail,
                    "control_mode": active_input_source,
                    "state": machine.state.value,
                    "pending_command": machine.pending_command,
                    "confirmation_required": machine.pending_command is not None,
                    "route": active_route,
                    "origin": machine.active_origin,
                    "destination": machine.active_destination or machine.destination,
                    "position": list(WAYPOINTS.get(machine.current_location, WAYPOINTS["S"])),
                    "next_waypoint": None,
                    "distance": None,
                    "sensor_peak": 0.0,
                    "last_safety_stop": "head_shake" if machine.state.value == "STOPPED" else "clear",
                }
                canvas = dashboard.render(snapshot, frame)
                writer.write(canvas)
                if processed == min(total_frames - 1, int(10.5 * fps)):
                    cv2.imwrite(str(preview), canvas)
            calibration_completed = gesture_input.calibrated
        finally:
            writer.release()
            gesture_input.close()
            voice.close()
            dashboard.close()

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is required to encode the dashboard demo as H.264.")
        subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-i", str(intermediate), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)],
            check=True,
        )

    counts = Counter(str(event["gesture"]) for event in gesture_events)
    report: dict[str, object] = {
        "source_video": str(video.resolve()),
        "source_video_packaged": False,
        "subject_consent_confirmed_by_user": True,
        "output_video": str(output.resolve()),
        "frames_processed": processed,
        "fps": round(fps, 3),
        "calibration_completed": calibration_completed,
        "gesture_counts": dict(sorted(counts.items())),
        "gesture_events": gesture_events,
        "voice_events": voice_events,
        "state_events": applied_state_events,
        "microphone_audio_used": False,
        "runtime_recording_enabled": False,
        "derived_demo_media_created_explicitly": True,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, default=PROJECT.parent / "tilt_gesture.mp4")
    parser.add_argument("--transcripts", type=Path, default=PROJECT / "tools" / "trace_demo_transcripts.json")
    parser.add_argument("--output", type=Path, default=PROJECT / "demo" / "traceability_dashboard_demo.mp4")
    parser.add_argument("--preview", type=Path, default=PROJECT / "demo" / "traceability_dashboard_preview.jpg")
    parser.add_argument("--report", type=Path, default=PROJECT / "validation_runs" / "gesture_video_clip" / "traceability_dashboard_demo.json")
    args = parser.parse_args()
    report = build(args.clip.resolve(), args.transcripts.resolve(), args.output.resolve(), args.preview.resolve(), args.report.resolve())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
