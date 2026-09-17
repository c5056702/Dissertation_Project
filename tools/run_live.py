"""Launch the project in real-time Webots using the isolated local environment."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
WORLD = PROJECT / "worlds" / "epuck_waypoint_navigation.wbt"


def live_environment(base: dict[str, str]) -> dict[str, str]:
    """Keep test/replay settings out of a physical live session."""
    return {
        key: value for key, value in base.items()
        if not key.upper().startswith("EPUCK_")
        and key.upper() not in {"PYTHONHOME", "PYTHONPATH", "MICROPHONE_DEVICE"}
    }


def resolve_webots(explicit: str | None = None) -> Path | None:
    """Find Webots on a new Windows client without relying on this PC's drive layout."""
    candidates: list[Path] = []
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None
    for value in (explicit, os.environ.get("WEBOTS_EXECUTABLE"), shutil.which("webots"), shutil.which("webots.exe")):
        if value:
            candidates.append(Path(value))
    for base in filter(None, [os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")]):
        root = Path(str(base))
        candidates.extend(
            [
                root / "Webots" / "msys64" / "mingw64" / "bin" / "webots.exe",
                root / "Webots" / "webots.exe",
            ]
        )
        candidates.extend(root.glob("Webots*/*/mingw64/bin/webots.exe"))
    # Retain the development machine path as a final compatibility candidate.
    candidates.append(Path(r"F:\Webots-R2025a\msys64\mingw64\bin\webots.exe"))
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="auto")
    parser.add_argument("--microphone")
    parser.add_argument("--webots", help="Explicit Webots executable if automatic discovery is unsuccessful.")
    parser.add_argument("--list-microphones", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=15.0,
                        help="Device retry window after initialization; imports/model loading/camera discovery take additional time.")
    parser.add_argument("--retry-seconds", type=float, default=3.0)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    if args.list_microphones:
        try:
            import sounddevice as sd  # type: ignore
        except ImportError as error:
            print(f"sounddevice is unavailable: {error}", file=sys.stderr)
            return 2
        devices = sd.query_devices()
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) > 0:
                marker = " (default input)" if index == sd.default.device[0] else ""
                print(f"{index}: {device.get('name')} — {int(device.get('default_samplerate', 0))} Hz{marker}")
        return 0
    venv_scripts = PROJECT / ".venv" / "Scripts"
    python = venv_scripts / "python.exe"
    model = PROJECT / "models" / "vosk-model-small-en-us-0.15"
    webots = resolve_webots(args.webots)
    if not python.is_file() or not model.is_dir() or webots is None:
        print(
            "Live launch prerequisites are missing. Create .venv, install requirements, keep the Vosk model under models/, "
            "and install Webots R2025a or pass --webots with its executable path.",
            file=sys.stderr,
        )
        return 2
    run_dir = PROJECT / "validation_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_live"
    run_dir.mkdir(parents=True, exist_ok=False)
    preflight_command = [
        str(python),
        str(PROJECT / "tools" / "check_live_inputs.py"),
        "--camera",
        str(args.camera),
        "--model",
        str(model),
        "--wait-seconds",
        str(args.wait_seconds),
        "--retry-seconds",
        str(args.retry_seconds),
        "--output",
        str(run_dir / "device_preflight.json"),
    ]
    if args.microphone:
        preflight_command.extend(["--microphone", args.microphone])
    print("Checking live inputs before starting Webots...", flush=True)
    try:
        preflight = subprocess.run(preflight_command, cwd=PROJECT)
    except KeyboardInterrupt:
        print("Live input check cancelled; Webots was not started.", file=sys.stderr, flush=True)
        return 130
    # Python's handled cancellation, SIGINT, and Windows STATUS_CONTROL_C_EXIT
    # (unsigned/signed forms) must never fall through to the retrying launch.
    if preflight.returncode in {130, -2, 0xC000013A, -1073741510}:
        print("Live input check cancelled; Webots was not started.", file=sys.stderr, flush=True)
        return 130
    if preflight.returncode and args.require_ready:
        return preflight.returncode
    if preflight.returncode:
        print(
            "Live devices are not both ready yet; Webots will start safely stopped and keep retrying.",
            file=sys.stderr,
        )
    environment = live_environment(dict(os.environ))
    environment["PATH"] = f"{venv_scripts}{os.pathsep}{environment.get('PATH', '')}"
    environment.update(
        VOSK_MODEL_PATH=str(model.resolve()),
        WEBCAM_INDEX=str(args.camera),
        INPUT_RETRY_SECONDS=str(args.retry_seconds),
        EPUCK_VALIDATION_DIR=str(run_dir.resolve()),
        WEBOTS_EXECUTABLE=str(webots),
    )
    if args.microphone:
        environment["MICROPHONE_DEVICE"] = args.microphone
    print(f"Launching Webots: {webots}", flush=True)
    print(f"Live evidence directory: {run_dir}", flush=True)
    # Forward controller messages to the launch terminal as well as Webots'
    # console, including every destination-specific tilt selection.
    try:
        return subprocess.call([str(webots), "--mode=realtime", "--stdout", "--stderr", str(WORLD)], cwd=PROJECT, env=environment)
    except KeyboardInterrupt:
        print("Live launcher interrupted.", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
