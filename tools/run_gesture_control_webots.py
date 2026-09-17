"""Run Docker Webots from production-classified gesture-video events."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


PROJECT = Path(__file__).resolve().parents[1]
WORLD = PROJECT / "worlds" / "epuck_waypoint_navigation.wbt"
WEBOTS = Path(os.environ.get("WEBOTS_EXECUTABLE", "/usr/local/webots/webots"))
EXPECTED_GESTURES = ["TILT_LEFT", "NOD", "TILT_LEFT", "NOD", "TILT_RIGHT", "NOD", "SHAKE"]
EXPECTED_COMMANDS = ["start A", "go to C", "go to B"]
EXPECTED_ROUTES = ["S_A_SHORT", "GRAPH_A_C_SHORTEST", "GRAPH_C_B_ALTERNATIVE"]


def run(manifest_path: Path, transcripts_path: Path, *, no_rendering: bool = False) -> tuple[bool, Path, dict[str, object]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    detected = [str(event.get("gesture")) for event in manifest.get("gesture_events", [])]
    if not manifest.get("uses_production_classifier") or detected != EXPECTED_GESTURES:
        raise ValueError(f"unverified gesture manifest: {detected}")
    if not WORLD.is_file() or not WEBOTS.is_file() or not transcripts_path.is_file():
        raise FileNotFoundError("Webots, world, manifest, or transcript schedule is missing")

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_gesture_video_control"
    run_dir = PROJECT / "validation_runs" / run_id
    run_dir.mkdir(parents=True)
    evidence_manifest = run_dir / "gesture_event_manifest.json"
    evidence_transcripts = run_dir / "gesture_control_transcripts.json"
    shutil.copy2(manifest_path, evidence_manifest)
    shutil.copy2(transcripts_path, evidence_transcripts)

    duration = float(manifest.get("duration_seconds", 18.4))
    completion_seconds = duration + 0.25
    raw_video = run_dir / "gesture_control_webots_raw.mp4"
    environment = os.environ.copy()
    environment.update(
        EPUCK_GESTURE_REPLAY=str(evidence_manifest),
        EPUCK_TRANSCRIPT_REPLAY=str(evidence_transcripts),
        EPUCK_VALIDATION_DIR=str(run_dir),
        EPUCK_DISABLE_DASHBOARD="1",
        EPUCK_REPLAY_COMPLETE_AFTER_SECONDS=f"{completion_seconds:.3f}",
        EPUCK_REPLAY_EXPECTED_STATE="STOPPED",
        EPUCK_TIMEOUT_SECONDS=f"{duration + 12.0:.3f}",
    )
    if no_rendering:
        environment["EPUCK_DISABLE_SIM_CAMERA"] = "1"
    else:
        environment.update(
            EPUCK_CAPTURE_OVERVIEW="1",
            EPUCK_RECORD_MOVIE=str(raw_video),
            EPUCK_MOVIE_ACCELERATION="4",
        )
    command = [str(WEBOTS), "--batch", "--mode=fast", "--stdout", "--stderr", str(WORLD)]
    if no_rendering:
        command.insert(-1, "--no-rendering")
    stdout_path = run_dir / "webots.stdout.log"
    stderr_path = run_dir / "webots.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=PROJECT, env=environment, stdout=stdout, stderr=stderr)
        (run_dir / "process.json").write_text(
            json.dumps({"pid": process.pid, "command": command}, indent=2),
            encoding="utf-8",
        )
        result_path = run_dir / "result.json"
        deadline = time.monotonic() + 480.0
        while time.monotonic() < deadline and not result_path.is_file() and process.poll() is None:
            time.sleep(0.25)
        if not result_path.is_file() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)

    if not (run_dir / "result.json").is_file():
        verification = {"passed": False, "reason": "missing_result", "run_dir": str(run_dir)}
    else:
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        events = result.get("events", [])
        gestures = [
            str(event.get("gesture"))
            for event in events
            if event.get("event") == "gesture_recognised"
        ]
        commands = [
            str(event.get("command"))
            for event in events
            if event.get("event") == "command_recognised" and event.get("accepted")
        ]
        sources = [
            str(event.get("gesture_source"))
            for event in events
            if event.get("event") == "gesture_recognised"
        ]
        route_starts = [
            str(event.get("route"))
            for event in events
            if event.get("event") == "route_started"
        ]
        def first_index(predicate) -> int:
            return next((index for index, event in enumerate(events) if predicate(event)), -1)

        command_c_index = first_index(
            lambda event: event.get("event") == "command_recognised"
            and event.get("accepted")
            and event.get("command") == "go to C"
        )
        arrival_a_index = first_index(
            lambda event: event.get("event") == "waypoint_reached"
            and event.get("transition") == "pickup_waypoint_reached"
        )
        command_b_index = first_index(
            lambda event: event.get("event") == "command_recognised"
            and event.get("accepted")
            and event.get("command") == "go to B"
        )
        arrival_c_index = first_index(lambda event: event.get("event") == "destination_reached")
        shake_index = first_index(
            lambda event: event.get("event") == "gesture_recognised" and event.get("gesture") == "SHAKE"
        )
        staged_order_verified = (
            -1 not in (arrival_a_index, command_c_index, arrival_c_index, command_b_index, shake_index)
            and arrival_a_index < command_c_index < arrival_c_index < command_b_index < shake_index
        )
        passed = bool(
            result.get("pass_result")
            and result.get("final_state") == "STOPPED"
            and gestures == EXPECTED_GESTURES
            and commands == EXPECTED_COMMANDS
            and all(source == "classified_gesture_video_replay" for source in sources)
            and route_starts == EXPECTED_ROUTES
            and staged_order_verified
            and (no_rendering or raw_video.is_file())
        )
        verification = {
            "passed": passed,
            "run_dir": str(run_dir),
            "source_manifest": str(evidence_manifest),
            "detected_gestures": detected,
            "controller_gestures": gestures,
            "gesture_sources": sources,
            "accepted_commands": commands,
            "route_starts": route_starts,
            "expected_routes": EXPECTED_ROUTES,
            "staged_order_verified": staged_order_verified,
            "event_order_indices": {
                "arrival_A": arrival_a_index,
                "command_go_to_C": command_c_index,
                "arrival_C": arrival_c_index,
                "command_go_to_B": command_b_index,
                "interrupt_shake": shake_index,
            },
            "final_state": result.get("final_state"),
            "result_reason": result.get("reason"),
            "raw_video": str(raw_video),
            "raw_video_bytes": raw_video.stat().st_size if raw_video.is_file() else 0,
            "no_rendering": no_rendering,
            "microphone_audio_used": False,
            "uses_production_classifier_manifest": True,
        }
    (run_dir / "integration_verification.json").write_text(
        json.dumps(verification, indent=2) + "\n",
        encoding="utf-8",
    )
    return bool(verification["passed"]), run_dir, verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--transcripts", type=Path, required=True)
    parser.add_argument("--no-rendering", action="store_true")
    args = parser.parse_args()
    passed, _run_dir, verification = run(
        args.manifest.resolve(),
        args.transcripts.resolve(),
        no_rendering=args.no_rendering,
    )
    print(json.dumps(verification, indent=2))
    return 0 if passed else 4


if __name__ == "__main__":
    raise SystemExit(main())
