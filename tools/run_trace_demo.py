"""Launch Webots with the consented gesture clip and text-only voice fixtures."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]
WORLD = PROJECT / "worlds" / "epuck_waypoint_navigation.wbt"
DEFAULT_CLIP = PROJECT.parent / "tilt_gesture.mp4"
DEFAULT_TRANSCRIPTS = PROJECT / "tools" / "trace_demo_transcripts.json"
DEFAULT_WEBOTS = Path(os.environ.get("WEBOTS_EXECUTABLE", r"F:\Webots-R2025a\msys64\mingw64\bin\webots.exe"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", type=Path, default=DEFAULT_CLIP)
    parser.add_argument("--transcripts", type=Path, default=DEFAULT_TRANSCRIPTS)
    parser.add_argument("--webots", type=Path, default=DEFAULT_WEBOTS)
    args = parser.parse_args()
    clip = args.clip.resolve()
    transcripts = args.transcripts.resolve()
    webots = args.webots.resolve()
    missing = [path for path in (clip, transcripts, webots, WORLD) if not path.is_file()]
    if missing:
        print("Missing required trace-demo file(s): " + ", ".join(str(path) for path in missing), file=sys.stderr)
        return 2

    venv_scripts = PROJECT / ".venv" / "Scripts"
    run_dir = PROJECT / "validation_runs" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_trace_dashboard_demo"
    run_dir.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment["PATH"] = f"{venv_scripts}{os.pathsep}{environment.get('PATH', '')}"
    environment.update(
        WEBCAM_INDEX=str(clip),
        EPUCK_TRANSCRIPT_REPLAY=str(transcripts),
        EPUCK_VALIDATION_DIR=str(run_dir.resolve()),
        EPUCK_DASHBOARD_FPS="8",
    )
    print("Trace demo uses a consented video file and already-transcribed text; no microphone is opened.")
    print(f"Technical log: {run_dir}")
    return subprocess.call([str(webots), "--mode=realtime", str(WORLD)], cwd=PROJECT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())

