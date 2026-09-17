"""Replay a recorded camera clip through the production gesture recogniser.

Only technical summary data and emitted gesture categories are written. Video
frames and face landmarks remain transient and are never saved by this tool.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time


PROJECT = Path(__file__).resolve().parents[1]
CONTROLLER = PROJECT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(CONTROLLER))

from input_adapters import MediaPipeGestureRecognizer  # noqa: E402


def analyze(video: Path, output: Path | None, realtime: bool = True) -> dict[str, object]:
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video}")

    recognizer = MediaPipeGestureRecognizer(str(video), cooldown_seconds=0.8)
    capture = recognizer.capture
    cv2 = recognizer.cv2
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS)) or 25.0
    gestures: list[dict[str, object]] = []
    face_absence_segments: list[dict[str, object]] = []
    absence_started: int | None = None
    face_frames = 0
    processed_frames = 0
    started = time.monotonic()

    try:
        while capture.isOpened() and (frame_count <= 0 or processed_frames < frame_count):
            if realtime:
                due = started + processed_frames / fps
                delay = due - time.monotonic()
                if delay > 0:
                    time.sleep(delay)

            gesture = recognizer.poll(now=processed_frames / fps)
            position = int(capture.get(cv2.CAP_PROP_POS_FRAMES))
            if position <= processed_frames:
                break
            processed_frames = position
            if recognizer.face_present:
                face_frames += 1
                if absence_started is not None:
                    face_absence_segments.append(
                        {
                            "start_seconds": round(absence_started / fps, 3),
                            "end_seconds": round(processed_frames / fps, 3),
                            "duration_seconds": round((processed_frames - absence_started) / fps, 3),
                        }
                    )
                    absence_started = None
            elif absence_started is None:
                absence_started = max(processed_frames - 1, 0)
            if gesture:
                gestures.append(
                    {
                        "gesture": gesture,
                        "frame": processed_frames,
                        "time_seconds": round(processed_frames / fps, 3),
                        "evidence": dict(recognizer.detector.last_evidence),
                    }
                )
    finally:
        calibration_completed = recognizer.neutral is not None
        recognizer.close()

    if absence_started is not None:
        face_absence_segments.append(
            {
                "start_seconds": round(absence_started / fps, 3),
                "end_seconds": round(processed_frames / fps, 3),
                "duration_seconds": round((processed_frames - absence_started) / fps, 3),
            }
        )

    counts = Counter(str(event["gesture"]) for event in gestures)
    report: dict[str, object] = {
        "video": str(video.resolve()),
        "duration_seconds": round(processed_frames / fps, 3),
        "fps": round(fps, 3),
        "frames_processed": processed_frames,
        "calibration_frames_required": MediaPipeGestureRecognizer.CALIBRATION_FRAMES,
        "calibration_completed": calibration_completed,
        "face_detected_frames": face_frames,
        "face_detection_rate_percent": round(100.0 * face_frames / max(processed_frames, 1), 2),
        "face_absence_segments": face_absence_segments,
        "longest_face_absence_seconds": max(
            (float(segment["duration_seconds"]) for segment in face_absence_segments), default=0.0
        ),
        "gesture_counts": dict(sorted(counts.items())),
        "gesture_events": gestures,
        "uses_production_classifier": True,
        "replayed_at_camera_timing": realtime,
        "uses_recorded_frame_timestamps": True,
        "retained_media_or_landmarks": False,
    }

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Recorded webcam-compatible video file")
    parser.add_argument("--output", type=Path, help="Optional technical JSON report")
    parser.add_argument(
        "--no-realtime",
        action="store_true",
        help="Process quickly while preserving recorded timestamps for cooldown behavior",
    )
    args = parser.parse_args()
    report = analyze(args.video, args.output, realtime=not args.no_realtime)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
