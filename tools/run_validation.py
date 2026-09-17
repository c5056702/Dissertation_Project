"""Run isolated, evidence-producing Webots validation scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("EPUCK_WORLD", PROJECT / "worlds" / "epuck_waypoint_navigation.wbt"))
WEBOTS = Path(os.environ.get("WEBOTS_EXECUTABLE", r"F:\Webots-R2025a\msys64\mingw64\bin\webots.exe"))

SCENARIOS = {
    "baseline_short": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
    ],
    "baseline_long": [
        {"command": "start A", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
    ],
    "expanded_b_short": [
        {"command": "start B", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
    ],
    "expanded_b_long": [
        {"command": "start B", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
    ],
    "goto_a_shortest": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
    ],
    "goto_a_alternative": [
        {"command": "start"},
        {"command": "go to A", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
    ],
    "goto_b_shortest": [
        {"command": "start"},
        {"command": "go to B", "gesture": "NOD"},
    ],
    "goto_b_alternative": [
        {"command": "start"},
        {"command": "go to B", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
    ],
    "goto_a_to_s": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "go to S", "gesture": "NOD"},
    ],
    "goto_a_to_b": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "go to B", "gesture": "NOD"},
    ],
    "goto_b_to_a": [
        {"command": "start"},
        {"command": "go to B", "gesture": "NOD"},
        {"command": "go to A", "gesture": "NOD"},
    ],
    "midroute_destination_change": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "go to B", "gesture": "NOD", "confirmation_delay_seconds": "2", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "2"},
    ],
    "midroute_alternative": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "turn left", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "1"},
        {"command": "alternative route", "gesture": "NOD"},
    ],
    "midroute_continue": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "turn right", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "2"},
        {"command": "continue"},
    ],
    "midroute_reverse": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "reverse", "gesture": "NOD", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "1"},
    ],
    "midroute_forward": [
        {"command": "start"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "forward", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "1"},
    ],
    "demo_showcase": [
        {"command": "start"},
        {"command": "go to A", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"command": "turn right", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "1"},
        {"command": "continue"},
        {"command": "go to B", "gesture": "NOD"},
        {"command": "alternative route", "gesture": "NOD", "wait_for_route": "GRAPH_A_B", "minimum_waypoint_index": "2"},
        {"command": "go to C", "gesture": "NOD"},
        {"command": "go to S", "gesture": "NOD", "wait_for_route": "GRAPH_B_C", "minimum_waypoint_index": "2"},
        {"command": "go to A", "gesture": "NOD"},
        {"command": "reverse", "gesture": "NOD", "wait_for_route": "GRAPH_S_A", "minimum_waypoint_index": "2"},
    ],
    # These inputs represent text already produced by a recogniser. They test
    # the production command normaliser and controller without synthetic audio.
    "transcribed_a_short": [
        {"command": "  START   A  ", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pick up", "gesture": "NOD"},
        {"command": "dropoff", "gesture": "NOD"},
        {"command": " RETURN ", "gesture": "NOD"},
    ],
    "transcribed_b_long": [
        {"command": "START B", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"command": "PICKUP", "gesture": "NOD"},
        {"command": "DROP OFF", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
    ],
    "transcribed_unbounded": [
        {"command": "drive away", "gesture": "NOD"},
    ],
    "transcribed_wrong_state": [
        {"command": "pickup", "gesture": "NOD"},
    ],
    "transcribed_stop": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "  STOP  "},
    ],
    "voice_stop": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "stop"},
    ],
    "head_shake": [
        {"command": "start A", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"gesture": "SHAKE"},
    ],
    "keyboard_stop": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
    ],
    "obstacle_stop": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
    ],
    "localisation_loss": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
    ],
    "invalid_command": [
        {"command": "drop off", "gesture": "NOD"},
    ],
    "conflicting_stop": [
        {"command": "start A", "route_gesture": "TILT_RIGHT", "gesture": "NOD"},
        {"command": "stop", "gesture": "SHAKE"},
    ],
    "blocked_corridor": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
    ],
    "face_absent": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
    ],
    "controller_failure": [],
    "stop_on_s_a": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "stop", "wait_for_route": "S_A"},
    ],
    "stop_on_a_b": [
        {"command": "start B", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"gesture": "SHAKE", "wait_for_route": "S_A_SHORT_B", "minimum_waypoint_index": "3"},
    ],
    "stop_on_a_c": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "stop", "wait_for_route": "A_C"},
    ],
    "stop_on_b_c": [
        {"command": "start B", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"gesture": "SHAKE", "wait_for_route": "B_C"},
    ],
    "stop_on_c_a": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
        {"command": "stop", "wait_for_route": "C_A_S"},
    ],
    "stop_on_a_s": [
        {"command": "start A", "route_gesture": "TILT_LEFT", "gesture": "NOD"},
        {"command": "pickup", "gesture": "NOD"},
        {"command": "drop off", "gesture": "NOD"},
        {"command": "return", "gesture": "NOD"},
        {"gesture": "SHAKE", "wait_for_route": "C_A_S", "minimum_waypoint_index": "1"},
    ],
}

EXPECTED_TERMINALS = {
    "voice_stop": "safe_stop",
    "head_shake": "safe_stop",
    "keyboard_stop": "safe_stop",
    "obstacle_stop": "safe_obstacle_stop",
    "localisation_loss": "safe_localisation_stop",
    "invalid_command": "safe_rejection",
    "conflicting_stop": "safe_stop",
    "blocked_corridor": "safe_obstacle_stop",
    "face_absent": "safe_face_stop",
    "controller_failure": "safe_controller_failure",
    "stop_on_s_a": "safe_stop",
    "stop_on_a_b": "safe_stop",
    "stop_on_a_c": "safe_stop",
    "stop_on_b_c": "safe_stop",
    "stop_on_c_a": "safe_stop",
    "stop_on_a_s": "safe_stop",
    "transcribed_unbounded": "safe_rejection",
    "transcribed_wrong_state": "safe_rejection",
    "transcribed_stop": "safe_stop",
}

NAVIGATION_CHANGE_SCENARIOS = [
    "goto_a_shortest",
    "goto_a_alternative",
    "goto_b_shortest",
    "goto_b_alternative",
    "goto_a_to_s",
    "goto_a_to_b",
    "goto_b_to_a",
    "midroute_destination_change",
    "midroute_alternative",
    "midroute_continue",
    "midroute_reverse",
    "midroute_forward",
]
EXPECTED_TERMINALS.update({name: "destination_reached" for name in NAVIGATION_CHANGE_SCENARIOS})
EXPECTED_TERMINALS["demo_showcase"] = "destination_reached"

EXPECTED_FINAL_POSITIONS = {
    "goto_a_shortest": "A",
    "goto_a_alternative": "A",
    "goto_b_shortest": "B",
    "goto_b_alternative": "B",
    "goto_a_to_s": "S",
    "goto_a_to_b": "B",
    "goto_b_to_a": "A",
    "midroute_destination_change": "B",
    "midroute_alternative": "A",
    "midroute_continue": "A",
    "midroute_reverse": "S",
    "midroute_forward": "A",
    "demo_showcase": "S",
}

SCENARIO_ENVIRONMENT = {
    "keyboard_stop": {"EPUCK_INJECT_KEYBOARD_STOP": "1"},
    "obstacle_stop": {"EPUCK_OBSTACLE_THRESHOLD": "0"},
    "localisation_loss": {"EPUCK_FORCE_LOCALISATION_LOSS": "1"},
    "blocked_corridor": {"EPUCK_BLOCK_SHORT_CORRIDOR": "1", "EPUCK_OBSTACLE_THRESHOLD": "200"},
    "face_absent": {"EPUCK_FORCE_FACE_ABSENT": "1"},
    "controller_failure": {"EPUCK_FORCE_CONTROLLER_FAILURE": "1"},
}


def preflight() -> bool:
    """Check the project wiring before an expensive Webots run."""
    controller = PROJECT / "controllers" / "epuck_waypoint_controller" / "epuck_waypoint_controller.py"
    if not WORLD.is_file() or not WEBOTS.is_file() or not controller.is_file():
        return False
    world_text = WORLD.read_text(encoding="utf-8")
    required = [
        'controller "epuck_waypoint_controller"',
        "DEF EPUCK E-puck",
        "DEF WAYPOINT_S",
        "DEF WAYPOINT_A",
        "DEF WAYPOINT_B",
        "DEF WAYPOINT_C",
        'GPS { name "gps" }',
        'Compass { name "compass" }',
    ]
    return all(item in world_text for item in required)


def run_tests() -> bool:
    suite = unittest.defaultTestLoader.discover(str(PROJECT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def run_scenario(name: str, index: int, visible: bool, record_demo: bool = False) -> tuple[bool, Path]:
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{name}_{index:02d}"
    run_dir = PROJECT / "validation_runs" / run_id
    run_dir.mkdir(parents=True)
    scenario_path = run_dir / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "name": name,
                "expected_terminal": EXPECTED_TERMINALS.get(name, "return_to_base"),
                "expected_final_position": EXPECTED_FINAL_POSITIONS.get(name, "S"),
                "actions": SCENARIOS[name],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment.update(
        EPUCK_SCENARIO_FILE=str(scenario_path),
        EPUCK_VALIDATION_DIR=str(run_dir),
        EPUCK_TIMEOUT_SECONDS="300",
    )
    environment.update(SCENARIO_ENVIRONMENT.get(name, {}))
    if visible:
        environment["EPUCK_CAPTURE_OVERVIEW"] = "1"
    if record_demo:
        environment["EPUCK_RECORD_MOVIE"] = str(run_dir / "demo_raw.mp4")
    command = [str(WEBOTS), "--batch", "--mode=fast", "--stdout", "--stderr"]
    if not visible:
        command.append("--no-rendering")
    command.append(str(WORLD))
    with (run_dir / "webots.stdout.log").open("w", encoding="utf-8") as stdout, (run_dir / "webots.stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=PROJECT, env=environment, stdout=stdout, stderr=stderr)
        (run_dir / "process.json").write_text(json.dumps({"pid": process.pid, "command": command}, indent=2), encoding="utf-8")
        result_path = run_dir / "result.json"
        # Mesa software rendering in the Docker/Xvfb path is much slower than
        # headless physics. Keep the process bound, but allow rendered evidence
        # runs enough wall time to finish the same deterministic workflow.
        # Complete B/long transcription workflows cover the longest route in the
        # map and can exceed two host minutes under Docker software rendering.
        # Keep the controller's own 300-second fail-safe as the upper bound while
        # giving all full transcription journeys the same deterministic allowance
        # as expanded navigation scenarios.
        extended_headless = name in NAVIGATION_CHANGE_SCENARIOS or name in {
            "transcribed_a_short",
            "transcribed_b_long",
        }
        default_runner_timeout = 600 if record_demo else (360 if visible else (240 if extended_headless else 120))
        runner_timeout = float(os.environ.get("WEBOTS_RUNNER_TIMEOUT_SECONDS", default_runner_timeout))
        deadline = time.monotonic() + runner_timeout
        while time.monotonic() < deadline and not result_path.is_file() and process.poll() is None:
            time.sleep(0.25)
        if not result_path.is_file() and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
            time.sleep(1.0)
            return False, run_dir
        if process.poll() is None:
            process.terminate()  # Stop only the PID created for this validation run.
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
    if not result_path.is_file():
        time.sleep(1.0)
        return False, run_dir
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if name == "midroute_destination_change":
        events = payload.get("events", [])
        pending = next((e for e in events if e["event"] == "voice_destination_override_pending"), None)
        confirmed = next((e for e in events if e["event"] == "command_confirmed" and e.get("command") == "go to B"), None)
        modes = [e.get("mode") for e in events if e["event"] == "input_mode_changed"]
        checks = {"pending_and_confirmation_present": bool(pending and confirmed)}
        if pending and confirmed:
            start_position = next(e["position"] for e in events if e["event"] == "command_confirmed" and e.get("command") == "go to A")
            checks["travelled_before_override"] = sum((a-b)**2 for a, b in zip(pending["position"], start_position)) ** .5 > .2
            checks["waited_for_separate_confirmation"] = confirmed["simulation_seconds"] - pending["simulation_seconds"] >= 2.0
            settled = next((e for e in events if e["event"] == "pending_stop_sample"), None)
            checks["zero_motor_targets_while_pending"] = bool(settled and settled["motor_targets"] == [0, 0])
            checks["stationary_after_braking"] = bool(settled and sum((a-b)**2 for a, b in zip(settled["position"], confirmed["position"])) ** .5 < .001)
            checks["braking_drift_below_5cm"] = sum((a-b)**2 for a, b in zip(pending["position"], confirmed["position"])) ** .5 < .05
            checks["voice_then_camera_mode"] = modes[-2:] == ["MICROPHONE", "CAMERA"]
            checks["confirmed_destination_b"] = confirmed.get("destination") == "B"
        (run_dir / "override_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        if not all(checks.values()):
            return False, run_dir
    # Webots releases its controller and rendering resources asynchronously on
    # Windows. Avoid immediately reusing them for the next isolated run.
    time.sleep(1.0)
    return bool(payload.get("pass_result")), run_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=[*SCENARIOS, "workflows", "navigation_changes", "transcriptions", "safety", "all"],
        default="baseline_short",
    )
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--record-demo", action="store_true")
    args = parser.parse_args()
    if args.repeat < 1 or not preflight():
        return 2
    if not run_tests():
        return 3
    workflow_names = ["baseline_short", "baseline_long", "expanded_b_short", "expanded_b_long"]
    transcription_names = [
        "transcribed_a_short",
        "transcribed_b_long",
        "transcribed_unbounded",
        "transcribed_wrong_state",
        "transcribed_stop",
    ]
    if args.scenario == "all":
        names = list(SCENARIOS)
    elif args.scenario == "workflows":
        names = workflow_names
    elif args.scenario == "navigation_changes":
        names = NAVIGATION_CHANGE_SCENARIOS
    elif args.scenario == "transcriptions":
        names = transcription_names
    elif args.scenario == "safety":
        names = [name for name in SCENARIOS if name not in workflow_names + transcription_names + NAVIGATION_CHANGE_SCENARIOS]
    else:
        names = [args.scenario]
    visible = args.visible or args.record_demo
    records = []
    for name in names:
        for index in range(1, args.repeat + 1):
            passed, run_dir = run_scenario(name, index, visible, args.record_demo)
            records.append({"scenario": name, "run": index, "passed": passed, "run_dir": str(run_dir)})
    postflight_ok = run_tests()
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scenario_selection": args.scenario,
        "repeat": args.repeat,
        "visible": visible,
        "record_demo": args.record_demo,
        "passed": sum(record["passed"] for record in records),
        "total": len(records),
        "postflight_tests": postflight_ok,
        "records": records,
    }
    summary_dir = PROJECT / "validation_runs" / "suite_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{args.scenario}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    print(json.dumps(summary, indent=2))
    return 0 if all(record["passed"] for record in records) and postflight_ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
