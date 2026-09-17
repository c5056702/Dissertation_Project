"""Create and verify a machine-local Windows environment. No device recording."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import venv

PROJECT = Path(__file__).resolve().parents[1]


def verify_manifest(root: Path) -> int:
    manifest = root / "SHA256SUMS.txt"
    if not manifest.is_file():
        print("No archive manifest in development folder; source tests will still run.")
        return 0
    checked = 0
    for line in manifest.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError(f"Unsafe manifest path: {relative}")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected.lower():
            raise ValueError(f"Package checksum mismatch: {relative}. Extract a fresh ZIP before setup.")
        checked += 1
    print(f"Verified {checked} packaged file checksums.")
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Verify an existing environment without installing packages.")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or platform.architecture()[0] != "64bit":
        print("Use 64-bit Python 3.12 on Windows: py -3.12 tools/setup_client.py", file=sys.stderr)
        return 2
    verify_manifest(PROJECT)
    python = PROJECT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        if args.check_only:
            raise RuntimeError("No .venv found. Run setup without --check-only.")
        venv.EnvBuilder(with_pip=True).create(PROJECT / ".venv")
    check = subprocess.run([str(python), "-c", "import sys,struct; assert sys.version_info[:2]==(3,12) and struct.calcsize('P')==8"], cwd=PROJECT)
    if check.returncode:
        raise RuntimeError("Existing .venv is incompatible. Preserve it under a new name, then rerun setup with Python 3.12.")
    if not args.check_only:
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(PROJECT / "requirements.txt")], cwd=PROJECT, check=True)
    subprocess.run([str(python), "-m", "pip", "check"], cwd=PROJECT, check=True)
    subprocess.run([str(python), "-c", "import cv2,mediapipe,numpy,sounddevice,vosk; assert hasattr(mediapipe,'solutions'); print('Recognition and GUI imports passed')"], cwd=PROJECT, check=True)
    subprocess.run([str(python), "-m", "unittest", "discover", "-s", "tests"], cwd=PROJECT, check=True)
    from run_live import resolve_webots
    webots = resolve_webots()
    report = {"python": str(python), "webots": str(webots) if webots else None,
              "software_tests_passed": True, "physical_devices_verified": False,
              "next_step": "run_live.py --list-microphones, then run_live.py --microphone INDEX --require-ready"}
    output = PROJECT / "validation_runs" / "client_setup.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not webots:
        print("Install Webots R2025a or set WEBOTS_EXECUTABLE to its executable, then run the live launcher.")
        return 2
    print("Software ready. Check microphone/camera on this laptop before the demonstration.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        raise SystemExit(2)
