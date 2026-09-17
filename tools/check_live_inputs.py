"""Non-recording preflight for the optional live microphone/webcam workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


PROJECT = Path(__file__).resolve().parents[1]
CONTROLLER = PROJECT / "controllers" / "epuck_waypoint_controller"
sys.path.insert(0, str(CONTROLLER))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="auto")
    parser.add_argument("--microphone")
    parser.add_argument("--wait-seconds", type=float, default=15.0,
                        help="Device retry window after initialization; imports/model loading/camera discovery take additional time.")
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    parser.add_argument("--model", type=Path, default=PROJECT / "models" / "vosk-model-small-en-us-0.15")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {"python": sys.executable, "model": str(args.model.resolve())}
    live_input = None
    cancelled = False
    started = time.monotonic()
    try:
        from input_adapters import LocalMultimodalInput, MediaPipeGestureRecognizer, VoskCommandRecognizer

        def open_microphone(*factory_args, **factory_kwargs):
            print("[preflight] Loading Vosk and opening the microphone...", file=sys.stderr, flush=True)
            return VoskCommandRecognizer(*factory_args, **factory_kwargs)

        def open_camera(*factory_args, **factory_kwargs):
            print("[preflight] Loading MediaPipe/OpenCV and opening the camera...", file=sys.stderr, flush=True)
            return MediaPipeGestureRecognizer(*factory_args, **factory_kwargs)

        print("[preflight] Initialization can take longer than --wait-seconds. Ctrl+C cancels.",
              file=sys.stderr, flush=True)
        microphone = int(args.microphone) if args.microphone and args.microphone.isdigit() else args.microphone
        live_input = LocalMultimodalInput(
            str(args.model.resolve()),
            args.camera,
            microphone_device=microphone,
            retry_interval=max(0.25, args.retry_seconds),
            strict=False,
            voice_factory=open_microphone,
            gesture_factory=open_camera,
        )
        print(f"[preflight] Initialization finished after {time.monotonic() - started:.1f}s; "
              f"checking device data (retry window {max(0.0, args.wait_seconds):g}s).",
              file=sys.stderr, flush=True)
        deadline = time.monotonic() + max(0.0, args.wait_seconds)
        while not live_input.ready and time.monotonic() < deadline:
            live_input.poll()
            time.sleep(0.05)
        report.update(live_input.status())
        report["voice"] = "ready" if live_input.voice_ready else "waiting"
        report["gesture"] = "ready" if live_input.gesture_ready else "waiting"
        if live_input.voice is not None:
            report["microphone_name"] = live_input.voice.device_name
            report["microphone_sample_rate"] = live_input.voice.sample_rate
            report["microphone_callbacks"] = getattr(live_input.voice, "callback_count", 0)
            report["microphone_audio_bytes"] = getattr(live_input.voice, "audio_bytes_received", 0)
            report["microphone_audio_peak"] = getattr(live_input.voice, "last_audio_peak", 0)
            report["microphone_signal_detected"] = bool(getattr(live_input.voice, "last_audio_peak", 0) >= 80)
            report["microphone_partial"] = getattr(live_input.voice, "last_partial_transcript", "")
            report["last_voice_decision"] = getattr(live_input.voice, "last_trace", None)
            report["microphone_pipeline_verified"] = bool(
                getattr(live_input.voice, "callback_count", 0) > 0
                and getattr(live_input.voice, "audio_bytes_received", 0) > 0
            )
        if live_input.gesture is not None:
            report["camera_index"] = live_input.gesture.camera_index
            report["camera_backend"] = live_input.gesture.camera_backend
            report["camera_resolution"] = list(live_input.gesture.resolution)
    except KeyboardInterrupt:
        cancelled = True
        report.update(ready=False, cancelled=True)
        print("[preflight] Cancelled by keyboard interrupt.", file=sys.stderr, flush=True)
    except Exception as error:
        report["ready"] = False
        report["probe_error"] = str(error)
    finally:
        if live_input is not None:
            live_input.close()
    report["media_saved"] = False
    if not report.get("voice_ready"):
        report["microphone_help"] = "Run tools/run_live.py --list-microphones, then relaunch with --microphone INDEX."
    report_text = json.dumps(report, indent=2)
    if args.output:
        output = args.output if args.output.is_absolute() else PROJECT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_text + "\n", encoding="utf-8")
    print(report_text)
    return 130 if cancelled else (0 if report.get("ready") else 2)


if __name__ == "__main__":
    raise SystemExit(main())
