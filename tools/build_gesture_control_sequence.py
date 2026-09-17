"""Cut the consented gesture clip into a verified controller-ready sequence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import cv2


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from analyze_gesture_video import analyze  # noqa: E402


EXPECTED_SEQUENCE = ["TILT_LEFT", "NOD", "TILT_LEFT", "NOD", "TILT_RIGHT", "NOD", "SHAKE"]

# Brief black separators intentionally cause face-loss reset.  A neutral source
# section then provides enough frames to re-arm the one-shot detector.  This
# prevents a discontinuous edit between two valid poses from looking like a
# false shake.
SECTIONS: list[dict[str, object]] = [
    {"name": "neutral_calibration", "role": "calibration", "source_start": 0.0, "source_end": 2.7},
    {"name": "left_tilt_select_shortest", "role": "TILT_LEFT", "source_start": 2.7, "source_end": 4.8},
    {"name": "separator_1", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_1", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "nod_confirm_first_route", "role": "NOD", "source_start": 14.5, "source_end": 16.7},
    {"name": "separator_2", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_2", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "wait_for_a_arrival", "role": "neutral_wait", "freeze_source": 2.0, "duration": 49.86},
    {"name": "left_tilt_select_shortest_to_c", "role": "TILT_LEFT", "source_start": 6.5, "source_end": 8.5},
    {"name": "separator_3", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_3", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "nod_confirm_second_route", "role": "NOD", "source_start": 39.6, "source_end": 42.0},
    {"name": "separator_4", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_4", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "wait_for_c_arrival", "role": "neutral_wait", "freeze_source": 2.0, "duration": 42.76},
    {"name": "right_tilt_select_alternative_to_b", "role": "TILT_RIGHT", "source_start": 9.4, "source_end": 11.5},
    {"name": "separator_5", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_5", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "nod_confirm_third_route", "role": "NOD", "source_start": 58.5, "source_end": 60.8},
    {"name": "separator_6", "role": "face_loss_reset", "duration": 0.32},
    {"name": "neutral_rearm_6", "role": "neutral_rearm", "source_start": 1.7, "source_end": 2.5},
    {"name": "wait_before_interrupt", "role": "neutral_wait", "freeze_source": 2.0, "duration": 13.76},
    {"name": "shake_emergency_stop", "role": "SHAKE", "source_start": 43.8, "source_end": 46.2},
]


def build(source: Path, output: Path, manifest_path: Path) -> dict[str, object]:
    if not source.is_file():
        raise FileNotFoundError(source)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required")

    capture = cv2.VideoCapture(str(source))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if width <= 0 or height <= 0:
        raise RuntimeError("could not inspect source video dimensions")

    filters: list[str] = []
    labels: list[str] = []
    timeline: list[dict[str, object]] = []
    cursor = 0.0
    for index, original in enumerate(SECTIONS):
        section = dict(original)
        label = f"s{index}"
        if "freeze_source" in section:
            duration = float(section["duration"])
            source_frame = float(section["freeze_source"])
            filters.append(
                f"[0:v]trim=start={source_frame}:end={source_frame + 0.04},"
                f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={duration - 0.04}[{label}]"
            )
        elif "duration" in section:
            duration = float(section["duration"])
            filters.append(f"color=c=black:s={width}x{height}:r=25:d={duration}[{label}]")
        else:
            start = float(section["source_start"])
            end = float(section["source_end"])
            duration = end - start
            filters.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[{label}]")
        section["output_start"] = round(cursor, 3)
        cursor += duration
        section["output_end"] = round(cursor, 3)
        timeline.append(section)
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0,fps=25,format=yuv420p[outv]")

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outv]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )

    report = analyze(output, None, realtime=False)
    detected = [str(item["gesture"]) for item in report["gesture_events"]]
    if detected != EXPECTED_SEQUENCE:
        raise RuntimeError(f"gesture sequence mismatch: expected {EXPECTED_SEQUENCE}, detected {detected}")

    gesture_events: list[dict[str, object]] = []
    for event in report["gesture_events"]:
        event = dict(event)
        event_time = float(event["time_seconds"])
        matching = next(
            (
                section
                for section in timeline
                if float(section["output_start"]) <= event_time < float(section["output_end"])
            ),
            None,
        )
        if not matching or matching.get("role") != event["gesture"]:
            raise RuntimeError(f"gesture {event['gesture']} was emitted outside its intended section")
        event["section"] = matching["name"]
        event["source_time_seconds"] = round(
            float(matching["source_start"]) + event_time - float(matching["output_start"]),
            3,
        )
        gesture_events.append(event)

    manifest: dict[str, object] = {
        **report,
        "video": str(output.resolve()),
        "source_video": str(source.resolve()),
        "source_video_packaged": False,
        "subject_consent_confirmed_by_user": True,
        "expected_sequence": EXPECTED_SEQUENCE,
        "detected_sequence": detected,
        "sequence_verified": True,
        "sections": timeline,
        "gesture_events": gesture_events,
        "uses_production_classifier": True,
        "controller_replay_ready": True,
        "microphone_audio_used": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROJECT.parent / "tilt_gesture.mp4")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT / "validation_runs" / "gesture_video_control" / "gesture_control_sequence.mp4",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT / "validation_runs" / "gesture_video_control" / "gesture_event_manifest.json",
    )
    args = parser.parse_args()
    manifest = build(args.source.resolve(), args.output.resolve(), args.manifest.resolve())
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
