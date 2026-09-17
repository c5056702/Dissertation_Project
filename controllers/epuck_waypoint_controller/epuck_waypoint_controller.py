"""Webots controller for the local, multimodal e-puck navigation prototype."""

from __future__ import annotations

import json
import math
import os
import sys
import faulthandler
from pathlib import Path
from time import monotonic
from typing import Any

# Use the environment created on this computer even when Webots preferences
# point at a different Python installation. Preserve Webots' controller paths.
PROJECT = Path(__file__).resolve().parents[2]
client_python = PROJECT / ".venv" / "Scripts" / "python.exe"
if sys.platform == "win32" and client_python.is_file() and Path(sys.executable).resolve() != client_python.resolve():
    os.execv(str(client_python), [str(client_python), *sys.argv])

from controller import Keyboard, Supervisor

from input_adapters import GestureEventReplayRecognizer, LocalMultimodalInput, ScenarioInput, TranscriptReplayRecognizer
from model import RouteRequest, TaskMachine, TaskState, WAYPOINTS, is_emergency_key, live_startup_gate, normalise_command, route_length
from navigation import WaypointNavigator
from route_feedback import route_status_text
from validation import ValidationLogger


TIME_STEP = 32


def main() -> int:
    stall_trace_seconds = float(os.environ.get("EPUCK_TRACE_STALL_SECONDS", "0"))
    if stall_trace_seconds > 0:
        faulthandler.dump_traceback_later(stall_trace_seconds, repeat=True)
    robot = Supervisor()
    left = robot.getDevice("left wheel motor")
    right = robot.getDevice("right wheel motor")
    left.setPosition(float("inf"))
    right.setPosition(float("inf"))
    # Lock the robot before input adapters, the dashboard, or the simulation
    # loop start. This also protects a world reload after non-zero velocities.
    left.setVelocity(0.0)
    right.setVelocity(0.0)
    gps = robot.getDevice("gps")
    compass = robot.getDevice("compass")
    camera = robot.getDevice("camera")
    gps.enable(TIME_STEP)
    compass.enable(TIME_STEP)
    # Webots' e-puck camera is needed for live/rendered evidence only. Keeping
    # it active during long --no-rendering runs wastes simulator resources and
    # can stall software-rendered Docker validation after extended simulation.
    camera_enabled = (
        os.environ.get("EPUCK_DISABLE_SIM_CAMERA") != "1"
        and (
        not os.environ.get("EPUCK_SCENARIO_FILE")
        or os.environ.get("EPUCK_CAPTURE_OVERVIEW") == "1"
        or bool(os.environ.get("EPUCK_RECORD_MOVIE"))
        )
    )
    if camera_enabled:
        camera.enable(TIME_STEP)
    sensors = [robot.getDevice(f"ps{index}") for index in range(8)]
    for sensor in sensors:
        sensor.enable(TIME_STEP)
    keyboard = Keyboard()
    keyboard.enable(TIME_STEP)

    run_dir = Path(os.environ.get("EPUCK_VALIDATION_DIR", PROJECT / "validation_runs" / "manual"))
    scenario_path = os.environ.get("EPUCK_SCENARIO_FILE")
    logger = ValidationLogger(run_dir, append=not bool(scenario_path))
    scenario = ScenarioInput(scenario_path)
    live_input = None
    if not scenario_path:
        microphone_value = os.environ.get("MICROPHONE_DEVICE")
        microphone_device = int(microphone_value) if microphone_value and microphone_value.isdigit() else microphone_value
        transcript_replay = os.environ.get("EPUCK_TRANSCRIPT_REPLAY")
        gesture_replay = os.environ.get("EPUCK_GESTURE_REPLAY")
        voice_factory = (
            (lambda _model_path, device=None: TranscriptReplayRecognizer(transcript_replay, device=device, clock=robot.getTime))
            if transcript_replay
            else None
        )
        gesture_factory = (
            (lambda _camera_index: GestureEventReplayRecognizer(gesture_replay, clock=robot.getTime))
            if gesture_replay
            else None
        )
        input_options: dict[str, Any] = {}
        if voice_factory is not None:
            input_options["voice_factory"] = voice_factory
        if gesture_factory is not None:
            input_options["gesture_factory"] = gesture_factory
        live_input = LocalMultimodalInput(
            os.environ.get("VOSK_MODEL_PATH", str(PROJECT / "models" / "vosk-model-small-en-us-0.15")),
            os.environ.get("WEBCAM_INDEX", "auto"),
            microphone_device=microphone_device,
            retry_interval=float(os.environ.get("INPUT_RETRY_SECONDS", "3")),
            strict=False,
            **input_options,
        )
        logger.event(
            "live_input_supervisor_started",
            status=live_input.status(),
            voice_source="transcript_replay" if transcript_replay else "local_vosk_microphone",
            gesture_source="classified_gesture_video_replay" if gesture_replay else "local_mediapipe_camera",
        )
    dashboard: Any | None = None
    if not scenario_path and os.environ.get("EPUCK_DISABLE_DASHBOARD") != "1":
        try:
            from live_dashboard import LiveTraceDashboard

            dashboard = LiveTraceDashboard(fps=float(os.environ.get("EPUCK_DASHBOARD_FPS", "8")))
            logger.add_listener(dashboard.record_event)
            logger.event("dashboard_started", display="automatic_local_window", recording=False)
        except Exception as error:
            logger.event("dashboard_unavailable", reason=str(error))
    machine = TaskMachine()
    navigator = WaypointNavigator(left, right, gps, compass, sensors)
    navigator.obstacle_threshold = float(os.environ.get("EPUCK_OBSTACLE_THRESHOLD", str(navigator.obstacle_threshold)))
    logger.event("controller_started", state=machine.state.value, scenario=str(scenario_path or "live"))
    action_armed = False
    active_route_name: str | None = None
    active_route_request: RouteRequest | None = None
    completed = False
    loop_count = 0
    timeout_default = "120" if scenario_path else "0"
    timeout_seconds = float(os.environ.get("EPUCK_TIMEOUT_SECONDS", timeout_default))
    replay_complete_seconds = float(os.environ.get("EPUCK_REPLAY_COMPLETE_AFTER_SECONDS", "0"))
    replay_expected_state = os.environ.get("EPUCK_REPLAY_EXPECTED_STATE", "").upper().strip()
    start_time = robot.getTime()
    capture_overview = os.environ.get("EPUCK_CAPTURE_OVERVIEW") == "1"
    screenshot_dir = run_dir / "screenshots"
    initial_captured = False
    movie_path_value = os.environ.get("EPUCK_RECORD_MOVIE")
    movie_path = Path(movie_path_value) if movie_path_value else None
    movie_stop_requested = False
    last_live_status: dict[str, object] | None = None
    last_voice_final_decision: tuple[object, object] | None = None
    last_gesture_detection_status: dict[str, Any] | None = None
    last_gesture_detection_logged_at = -math.inf
    last_status_message: str | None = None
    last_route_selection: str | None = None
    route_selection_error: str | None = None
    last_route_status: tuple[str, str] | None = None
    last_navigation_details: dict[str, Any] = {}
    last_safety_stop: str | None = None
    control_mode = "MICROPHONE"

    def set_control_mode(mode: str, reason: str) -> None:
        nonlocal control_mode
        mode = mode.upper()
        if mode not in {"MICROPHONE", "CAMERA"}:
            raise ValueError(f"unsupported control mode: {mode}")
        if mode != control_mode:
            previous = control_mode
            control_mode = mode
            logger.event("input_mode_changed", previous=previous, mode=mode, reason=reason, state=machine.state.value)

    def track_safety_event(entry: dict[str, Any]) -> None:
        nonlocal last_safety_stop
        if entry.get("event") == "safety_stop":
            last_safety_stop = str(entry.get("source") or "safety_stop")

    logger.add_listener(track_safety_event)
    destination_verification_logged = False

    waypoint_defaults = {
        "S": ([0.10, 0.70, 0.25], [0.03, 0.15, 0.04]),
        "A": ([0.85, 0.08, 0.08], [0.16, 0.01, 0.01]),
        "B": ([0.08, 0.35, 0.90], [0.01, 0.04, 0.16]),
        "C": ([0.55, 0.14, 0.78], [0.10, 0.02, 0.15]),
    }
    visual_updates_enabled = capture_overview or not scenario_path
    locator = robot.getFromDef("ROBOT_LOCATOR") if visual_updates_enabled else None

    def set_status(event: str, detail: str = "", *, force: bool = False) -> None:
        nonlocal last_status_message
        if not visual_updates_enabled:
            return
        message = f"STATE: {machine.state.value} | {event}"
        if detail:
            message += f" | {detail}"
        if force or message != last_status_message:
            print(f"[status] {message}", flush=True)
            last_status_message = message
        publish_route_status()

    def pending_destination() -> str | None:
        command = machine.pending_command or ""
        if command.startswith(("go to ", "start ")):
            return command[-1]
        return {"drop off": "C", "return": "S", "pickup": machine.current_location}.get(command)

    def canonical_choice(choice: str | None) -> str | None:
        return {"short": "shortest", "long": "alternative"}.get(choice, choice)

    def route_feedback() -> dict[str, Any]:
        return {
            "state": machine.state.value,
            "pending_command": machine.pending_command,
            "pending_destination": pending_destination(),
            "pending_route_choice": canonical_choice(machine.route_choice),
            "active_destination": machine.active_destination,
            "active_route_choice": ("alternative" if active_route_request.alternative else "shortest") if active_route_request else None,
            "current_location": machine.current_location,
            "route_selection_error": route_selection_error,
        }

    def publish_route_status() -> None:
        nonlocal last_route_status
        if not visual_updates_enabled:
            return
        status = route_status_text(route_feedback())
        status_key = (machine.state.value, status)
        if status_key != last_route_status:
            print(f"[route] {status}", flush=True)
            robot.setLabel(0, f"STATE: {machine.state.value} | {status}", 0.14, 0.025, 0.045, 0xFFFFFF, 0.05, "Arial")
            last_route_status = status_key

    def pending_route_text() -> str:
        destination = pending_destination() or machine.destination or machine.active_destination or "?"
        if not str(machine.pending_command or "").startswith(("go to ", "start ")):
            return f"{machine.pending_command}: {destination}; awaiting NOD"
        choice = canonical_choice(machine.route_choice)
        if choice is None:
            return f"TO {destination}: choose SHORTEST (LEFT) or ALTERNATIVE (RIGHT); then NOD"
        return f"TO {destination}: {choice.upper()} selected; awaiting NOD"

    def report_tilt(gesture: str, outcome: str, *, superseding_command: str | None = None) -> None:
        nonlocal last_route_selection, route_selection_error
        if gesture not in {"TILT_LEFT", "TILT_RIGHT"}:
            return
        destination = pending_destination() or machine.active_destination
        selected = outcome in {"route_short_selected", "route_long_selected", "route_alternative_selected"}
        choice = canonical_choice(machine.route_choice) if selected else None
        if superseding_command:
            detail = f"{gesture.replace('_', ' ')} ignored: voice {superseding_command.upper()} has priority"
        elif selected:
            route_selection_error = None
            detail = f"{gesture.replace('_', ' ')} -> {pending_route_text()}"
        else:
            context = f"TO {destination}" if destination else "no destination selected"
            detail = f"{gesture.replace('_', ' ')} ignored ({context}); {machine.state.value}"
        # History describes what the tilt did; current confirmation guidance
        # comes from route_feedback and expires when the route starts.
        last_route_selection = (f"{gesture.replace('_', ' ')} -> TO {destination}: {choice.upper()} selected"
                                if selected else detail)
        logger.event("route_selection", gesture=gesture, destination=destination, route_choice=choice,
                     selected=selected, outcome=outcome, pending_command=machine.pending_command,
                     superseding_command=superseding_command, state=machine.state.value, message=last_route_selection)
        set_status("route selection", detail, force=True)

    def trace_tilt(entry: dict[str, Any]) -> None:
        if entry.get("event") == "gesture_recognised":
            report_tilt(str(entry.get("gesture", "")), str(entry.get("outcome", "ignored_gesture")))

    logger.add_listener(trace_tilt)

    def update_locator() -> None:
        if locator is None:
            return
        x, y = navigator.position()
        locator.getField("translation").setSFVec3f([x, y, 0.13])

    def update_route_display(request: RouteRequest | None = None) -> None:
        if not visual_updates_enabled:
            return
        # Route geometry is deliberately invisible. Only the requested
        # destination marker changes, while navigation continues to use the
        # same internal graph and GPS/compass waypoint sequence.
        destination = request.destination if request else None
        for name, (base_color, emissive_color) in waypoint_defaults.items():
            node = robot.getFromDef(f"WAYPOINT_{name}_STYLE")
            if node is None:
                continue
            node.getField("baseColor").setSFColor(base_color)
            node.getField("emissiveColor").setSFColor([0.75, 0.65, 0.20] if name == destination else emissive_color)

    update_route_display()
    set_status("START REQUIRED", "motors locked; say START")

    def update_live_status() -> bool:
        """Log device transitions and fail closed once if a ready pair is lost."""
        nonlocal last_live_status, last_voice_final_decision, action_armed
        nonlocal last_gesture_detection_status, last_gesture_detection_logged_at
        if scenario_path or live_input is None:
            return False
        status = live_input.status()
        trace_status = getattr(live_input, "trace_status", None)
        trace = trace_status() if callable(trace_status) else {}
        decision = trace.get("voice_final_decision")
        if isinstance(decision, dict) and decision.get("transcript") and decision.get("decision_id") is not None:
            decision_key = (status.get("voice_reconnects", 0), decision["decision_id"])
            if decision_key != last_voice_final_decision:
                # Persist only final speech decisions. Camera frames, poses,
                # audio and changing partial transcripts remain transient.
                details = {
                    key: decision[key]
                    for key in ("decision_id", "source", "transcript", "command", "confidence", "threshold", "accepted", "reason")
                    if key in decision
                }
                details["word_confidences"] = [
                    {key: word[key] for key in ("word", "confidence") if key in word}
                    for word in decision.get("word_confidences", [])
                    if isinstance(word, dict)
                ]
                logger.event("voice_final_decision", voice_reconnects=decision_key[0], state=machine.state.value, **details)
                last_voice_final_decision = decision_key
        gesture_trace = trace.get("gesture_trace")
        if isinstance(gesture_trace, dict) and "tilt_gate" in gesture_trace:
            # Categorical diagnostics explain missed gestures without saving
            # poses, landmarks, frames, or the detector's numeric evidence.
            detection_status = {
                key: gesture_trace[key]
                for key in ("tilt_gate", "tilt_direction", "armed", "candidate", "tilt_blocked_axes", "neutral_axes_outside")
                if key in gesture_trace
            }
            detection_status.update(
                state=machine.state.value,
                pending_confirmation=action_armed,
                pending_command=machine.pending_command,
                active_destination=machine.active_destination,
            )
            now = monotonic()
            elapsed = now - last_gesture_detection_logged_at
            changed = detection_status != last_gesture_detection_status
            if elapsed >= 0.5 and (changed or elapsed >= 5.0):
                logger.event("gesture_detection_status", sample_reason="changed" if changed else "periodic", **detection_status)
                last_gesture_detection_status = detection_status
                last_gesture_detection_logged_at = now
        tracked = {
            key: status[key]
            for key in ("ready", "voice_ready", "camera_ready", "face_present", "gesture_calibrated")
        }
        previous = last_live_status
        if previous != tracked:
            logger.event("live_input_status", **status)
            print(
                "[live input] "
                f"microphone={'ready' if status['voice_ready'] else 'waiting'}; "
                f"camera={'ready' if status['camera_ready'] else 'waiting'}; "
                f"face={'present' if status['face_present'] else 'absent'}; "
                f"calibration={'ready' if status['gesture_calibrated'] else 'waiting'}",
                flush=True,
            )
            last_live_status = tracked
        lost_ready_pair = bool(previous and previous.get("ready") and not tracked["ready"])
        if lost_ready_pair:
            machine.reset(activated=False, stopped=True)
            navigator.stop()
            action_armed = False
            set_control_mode("MICROPHONE", "device recovery requires START")
            logger.event("safety_stop", source="input_device_disconnected", state=machine.state.value, status=status)
            update_route_display()
            set_status("safety stop", "input device disconnected")
        return lost_ready_pair

    if capture_overview:
        viewpoint = robot.getFromDef("MAIN_VIEW")
        if viewpoint:
            viewpoint.getField("position").setSFVec3f([0.0, 0.0, 7.2])
            viewpoint.getField("orientation").setSFRotation([0.0, 1.0, 0.0, 1.570796])
            logger.event(
                "viewpoint_configured",
                position=viewpoint.getField("position").getSFVec3f(),
                orientation=viewpoint.getField("orientation").getSFRotation(),
            )
        else:
            logger.event("viewpoint_configuration_failed", reason="MAIN_VIEW_not_found")
    if movie_path:
        movie_path.parent.mkdir(parents=True, exist_ok=True)
        movie_acceleration = int(os.environ.get("EPUCK_MOVIE_ACCELERATION", "4"))
        robot.movieStartRecording(
            str(movie_path),
            int(os.environ.get("EPUCK_MOVIE_WIDTH", "1280")),
            int(os.environ.get("EPUCK_MOVIE_HEIGHT", "720")),
            0,
            int(os.environ.get("EPUCK_MOVIE_QUALITY", "85")),
            movie_acceleration,
            False,
        )
        logger.event("movie_recording_started", path=str(movie_path), acceleration=movie_acceleration)
    if os.environ.get("EPUCK_BLOCK_SHORT_CORRIDOR") == "1":
        blocker = robot.getFromDef("TEST_BLOCKER")
        if blocker:
            blocker.getField("translation").setSFVec3f([0.0, 2.02, 0.20])
            logger.event("validation_fault_injected", fault="blocked_short_corridor")

    deferred_captures: list[tuple[int, str]] = []

    def export_capture(name: str) -> None:
        if not capture_overview:
            return
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        robot.exportImage(str(screenshot_dir / f"{name}.jpg"), 95)

    def capture(name: str, defer_frames: int = 0) -> None:
        if not capture_overview:
            return
        if defer_frames > 0:
            deferred_captures.append((defer_frames, name))
            return
        export_capture(name)

    pending_action: dict[str, str] | None = None

    def gesture_event_details(action: dict[str, str] | None) -> dict[str, Any]:
        if not action:
            return {}
        details: dict[str, Any] = {}
        for key in (
            "gesture_source",
            "gesture_section",
            "gesture_scheduled_seconds",
            "gesture_source_time_seconds",
        ):
            value = action.get(key)
            if value not in {None, ""}:
                details[key] = value
        return details

    def dashboard_snapshot() -> dict[str, Any]:
        position: tuple[float, float]
        try:
            position = navigator.position()
        except Exception:
            position = (float("nan"), float("nan"))
        next_waypoint = navigator.points[navigator.index] if navigator.index < len(navigator.points) else None
        distance = last_navigation_details.get("distance")
        if distance is None and next_waypoint and all(math.isfinite(value) for value in (*position, *next_waypoint)):
            distance = math.dist(position, next_waypoint)
        input_trace = live_input.trace_status() if live_input is not None else {}
        requested_destination = pending_destination()
        active_choice = ("alternative" if active_route_request.alternative else "shortest") if active_route_request else None
        active_input_source = control_mode
        if control_mode == "CAMERA" and action_armed:
            active_input_detail = "CAMERA MODE: tilt selects route; NOD confirms"
        elif control_mode == "CAMERA" and machine.state in machine.MOVING_STATES:
            active_input_detail = "CAMERA MODE: tilt selects a route; SHAKE stops"
        elif control_mode == "CAMERA":
            active_input_detail = "CAMERA MODE: gesture input active; voice switches mode"
        elif action_armed:
            active_input_detail = "VOICE MODE: make a gesture to switch back to camera confirmation"
        elif machine.state in machine.MOVING_STATES:
            active_input_detail = "VOICE MODE: listening for destination override or STOP"
        elif machine.state in {TaskState.IDLE, TaskState.STOPPED}:
            active_input_detail = "VOICE MODE: START REQUIRED; robot locked stationary"
        else:
            active_input_detail = "VOICE MODE: waiting for a destination command"
        return {
            **input_trace,
            "active_input_source": active_input_source,
            "active_input_detail": active_input_detail,
            "control_mode": control_mode,
            "session_id": logger.session_id,
            "state": machine.state.value,
            "current_location": machine.current_location,
            "route_status": route_status_text(route_feedback()),
            "pending_command": machine.pending_command,
            "confirmation_required": action_armed,
            "route_choice": machine.route_choice,
            "pending_destination": requested_destination,
            "pending_route_choice": canonical_choice(machine.route_choice) if requested_destination else None,
            "route": None if machine.pending_command else active_route_name,
            "active_route_name": active_route_name,
            "active_route_choice": active_choice,
            "active_destination": machine.active_destination,
            "last_route_selection": last_route_selection,
            "route_selection_error": route_selection_error,
            "origin": machine.active_origin,
            "destination": requested_destination or machine.active_destination or machine.destination,
            "position": list(position),
            "next_waypoint": None if machine.pending_command or next_waypoint is None else list(next_waypoint),
            "distance": None if machine.pending_command else distance,
            "sensor_peak": navigator.maximum_sensor_peak,
            "last_safety_stop": last_safety_stop or "clear",
        }

    def stop_from_dashboard(source: str = "dashboard_stop") -> None:
        nonlocal action_armed, pending_action, active_route_name, active_route_request, last_safety_stop
        machine.reset(activated=False, stopped=True)
        navigator.stop()
        action_armed = False
        pending_action = None
        active_route_name = None
        active_route_request = None
        last_safety_stop = source
        set_control_mode("MICROPHONE", "dashboard stop requires START")
        update_route_display()
        set_status("safety stop", source.replace("_", " "))
        logger.event("safety_stop", source=source, state=machine.state.value, position=navigator.position())

    def update_dashboard() -> str | None:
        """Render transient live evidence and return one UI safety action."""
        nonlocal dashboard, last_safety_stop
        if dashboard is None or live_input is None:
            return None
        try:
            dashboard.update(dashboard_snapshot(), live_input.consume_preview_frame())
            return dashboard.poll_action()
        except Exception as error:
            try:
                dashboard.close()
            except Exception:
                pass
            dashboard = None
            last_safety_stop = "dashboard_failure"
            logger.event("dashboard_failure", reason=str(error), state=machine.state.value)
            return "STOP"

    def finish_success(reason: str) -> int | None:
        if movie_path and movie_stop_requested:
            if robot.movieFailed():
                logger.event("movie_recording_failed", path=str(movie_path))
                logger.result(pass_result=False, final_state=machine.state.value, reason="movie_recording_failed")
                return 8
            if not robot.movieIsReady():
                return None
            logger.event("movie_recording_ready", path=str(movie_path))
        logger.result(
            pass_result=True,
            final_state=machine.state.value,
            reason=reason,
            final_position=navigator.position(),
            maximum_sensor_peak=navigator.maximum_sensor_peak,
            actual_path_length=round(navigator.actual_path_length, 3),
            simulation_duration_seconds=round(robot.getTime() - start_time, 3),
        )
        return 0

    while robot.step(TIME_STEP) != -1:
        loop_count += 1
        publish_route_status()
        dashboard_action = update_dashboard()
        if dashboard_action == "STOP":
            stop_from_dashboard("dashboard_stop")
            continue
        if dashboard_action == "RESET":
            stop_from_dashboard("dashboard_reset")
            logger.event("dashboard_reset_requested", state=machine.state.value, position=navigator.position())
            if dashboard is not None:
                dashboard.update(dashboard_snapshot(), force=True)
            if live_input is not None:
                live_input.close()
            if dashboard is not None:
                dashboard.close()
            robot.simulationResetPhysics()
            robot.simulationReset()
            robot.step(TIME_STEP)
            return 0
        if deferred_captures:
            remaining: list[tuple[int, str]] = []
            for frames, capture_name in deferred_captures:
                if frames <= 1:
                    export_capture(capture_name)
                else:
                    remaining.append((frames - 1, capture_name))
            deferred_captures[:] = remaining
        # Scene-tree writes are unnecessary in headless deterministic runs and
        # expensive in software rendering. Ten updates per simulated second
        # remain smooth for live/visible demonstrations.
        if (capture_overview or not scenario_path) and loop_count % max(1, 1000 // TIME_STEP // 10) == 0:
            update_locator()
        if not initial_captured:
            if visual_updates_enabled:
                update_locator()
            capture("00_initial_overview")
            initial_captured = True
        if os.environ.get("EPUCK_FORCE_CONTROLLER_FAILURE") == "1":
            navigator.stop()
            machine.reset(activated=False, stopped=True)
            update_route_display()
            set_status("safety stop", "controller failure")
            logger.event("controller_failure", reason="injected_validation_failure", state=machine.state.value)
            capture("safety_stop_controller_failure")
            expected = scenario.expected_terminal == "safe_controller_failure"
            logger.result(pass_result=expected, final_state=machine.state.value, reason="controller_failure")
            return 0 if expected else 7
        if timeout_seconds > 0 and robot.getTime() - start_time > timeout_seconds:
            navigator.stop()
            logger.event("route_failed", reason="timeout", state=machine.state.value, position=navigator.position())
            logger.result(pass_result=False, final_state=machine.state.value, reason="timeout", final_position=navigator.position())
            return 2
        if replay_complete_seconds > 0 and robot.getTime() - start_time >= replay_complete_seconds:
            navigator.stop()
            expected = not replay_expected_state or machine.state.value == replay_expected_state
            if movie_path and not movie_stop_requested:
                robot.movieStopRecording()
                movie_stop_requested = True
                logger.event("movie_recording_stop_requested", path=str(movie_path))
                continue
            logger.event(
                "gesture_video_replay_completed",
                expected_state=replay_expected_state or None,
                final_state=machine.state.value,
                matched=expected,
            )
            result = finish_success("gesture_video_replay_completed") if expected else None
            if expected and result is None:
                continue
            if expected:
                return result
            logger.result(
                pass_result=False,
                final_state=machine.state.value,
                reason="unexpected_gesture_video_replay_state",
                expected_state=replay_expected_state,
                final_position=navigator.position(),
            )
            return 10

        key = keyboard.getKey()
        injected_keyboard = os.environ.get("EPUCK_INJECT_KEYBOARD_STOP") == "1" and machine.state in machine.MOVING_STATES
        if is_emergency_key(key, Keyboard.END) or injected_keyboard:
            machine.reset(activated=False, stopped=True)
            navigator.stop()
            action_armed = False
            pending_action = None
            set_control_mode("MICROPHONE", "keyboard stop requires START")
            update_route_display()
            set_status("safety stop", "keyboard")
            logger.event("safety_stop", source="keyboard", state=machine.state.value)
            capture("safety_stop_keyboard")
            if scenario.expected_terminal == "safe_stop":
                logger.event("safety_stop_verified", source="keyboard", state=machine.state.value)
                result = finish_success("expected_keyboard_stop")
                return 0 if result is None else result
            continue

        # Active navigation accepts emergency commands, bounded intervention,
        # and destination changes without waiting for a waypoint.
        if machine.state in machine.MOVING_STATES:
            action = scenario.peek_action() if scenario_path else live_input.poll()
            ready_pair_lost = update_live_status()
            if ready_pair_lost or (not scenario_path and not live_input.ready):
                machine.reset(activated=False, stopped=True)
                navigator.stop()
                set_control_mode("MICROPHONE", "input unavailable requires START")
                action_armed = False
                update_route_display()
                set_status("safety stop", "input unavailable")
                if not ready_pair_lost:
                    logger.event("safety_stop", source="input_device_unavailable", state=machine.state.value, status=live_input.status())
                continue
            if scenario_path and action:
                required_route = action.get("wait_for_route")
                minimum_index = int(action.get("minimum_waypoint_index", "0"))
                emergency_action = (
                    normalise_command(action.get("command", "")) == "stop"
                    or action.get("gesture", "").upper() == "SHAKE"
                )
                route_ready = not required_route or (active_route_name and active_route_name.startswith(required_route))
                # Ordinary task commands in deterministic scenarios are meant
                # for the next arrival state. Only explicitly route-gated
                # interventions and global emergency actions run in motion.
                if (not emergency_action and not required_route) or not route_ready or navigator.index < minimum_index:
                    action = None
            forced_face_absent = os.environ.get("EPUCK_FORCE_FACE_ABSENT") == "1"
            if forced_face_absent or (not scenario_path and not live_input.face_present):
                machine.reset(activated=False, stopped=True)
                navigator.stop()
                set_control_mode("MICROPHONE", "face safety stop requires START")
                update_route_display()
                set_status("safety stop", "face absent")
                logger.event("safety_stop", source="face_absent", state=machine.state.value, position=navigator.position())
                capture("safety_stop_face_absent")
                if scenario.expected_terminal == "safe_face_stop":
                    logger.result(pass_result=True, final_state=machine.state.value, reason="expected_face_absent_stop", final_position=navigator.position())
                    return 0
                continue
            if action:
                if scenario_path:
                    action = scenario.next_action()
                command = normalise_command(action.get("command", ""))
                gesture = action.get("gesture", "").upper()
                if command == "stop" or gesture == "SHAKE":
                    report_tilt(gesture, "ignored_voice_priority", superseding_command=command)
                    source = "voice" if command == "stop" else "head_shake"
                    machine.accept_command("stop") if source == "voice" else machine.accept_gesture("SHAKE")
                    if source == "head_shake":
                        set_control_mode("CAMERA", "head shake safety input")
                        logger.event(
                            "gesture_recognised",
                            gesture="SHAKE",
                            outcome="emergency_stop",
                            state=machine.state.value,
                            input_source="CAMERA",
                            **gesture_event_details(action),
                        )
                    navigator.stop()
                    set_control_mode("MICROPHONE", "safety stop requires START")
                    action_armed = False
                    pending_action = None
                    update_route_display()
                    set_status("safety stop", source)
                    logger.event("safety_stop", source=source, state=machine.state.value, position=navigator.position())
                    capture(f"safety_stop_{source}")
                    if scenario.expected_terminal == "safe_stop":
                        logger.event("safety_stop_verified", source=source, state=machine.state.value)
                        logger.result(pass_result=True, final_state=machine.state.value, reason=f"expected_{source}_stop", final_position=navigator.position(), actual_path_length=round(navigator.actual_path_length, 3))
                        return 0
                    continue
                if command:
                    report_tilt(gesture, "ignored_voice_priority", superseding_command=command)
                    set_control_mode("MICROPHONE", f"voice command: {command}")
                    previous_route = active_route_name
                    previous_destination = machine.active_destination
                    accepted, status = machine.accept_command(command)
                    logger.event("command_recognised", command=command, accepted=accepted, status=status, state=machine.state.value, in_motion=True, input_source="MICROPHONE")
                    set_status("command accepted" if accepted else "command rejected", f"{command}: {status}")
                    if not accepted:
                        navigator.stop()
                        machine.reset(activated=False, stopped=True)
                        update_route_display()
                        logger.event("safety_stop", source="invalid_in_motion_command", command=command, state=machine.state.value, position=navigator.position())
                        if scenario.expected_terminal == "safe_rejection":
                            logger.result(pass_result=True, final_state=machine.state.value, reason=status)
                            return 0
                        continue
                    if status == "clarification_required":
                        navigator.stop()
                        logger.event("navigation_paused", command=command, state=machine.state.value, choices=["continue", "alternative route", "go to A/B/S", "reverse", "stop"])
                        set_status("paused for clarification", "say CONTINUE, ALTERNATIVE ROUTE, GO TO A/B/S, REVERSE, or STOP")
                        capture("navigation_paused")
                        continue
                    if status in {"continue_navigation", "resume_navigation"}:
                        logger.event("navigation_resumed", command=command, state=machine.state.value)
                        set_status("navigation resumed", active_route_name or "route")
                    elif status == "pending_confirmation":
                        route_selection_error = None
                        navigator.stop()
                        # A gesture sampled alongside speech is not a response
                        # to the new prompt. Require a later live gesture.
                        action["_gesture"] = action.get("gesture") if scenario_path else None
                        action["_confirm_after"] = robot.getTime() + float(action.get("confirmation_delay_seconds", 0))
                        action["_pending_since"] = robot.getTime()
                        pending_action = action
                        action_armed = True
                        if command.startswith("go to "):
                            logger.event(
                                "voice_destination_override_pending",
                                simulation_seconds=robot.getTime(),
                                position=navigator.position(),
                                command=command,
                                previous_route=previous_route,
                                previous_destination=previous_destination,
                                requested_destination=machine.destination,
                                state=machine.state.value,
                                input_source="MICROPHONE",
                                confirmation="NOD",
                            )
                            set_status("voice destination override", pending_route_text())
                        continue
                elif gesture in {"TILT_LEFT", "TILT_RIGHT"}:
                    outcome, _ = machine.accept_gesture(gesture, navigator.position())
                    set_control_mode("CAMERA", f"camera route gesture: {gesture}")
                    logger.event(
                        "gesture_recognised", gesture=gesture, outcome=outcome,
                        state=machine.state.value, in_motion=True, input_source="CAMERA",
                        **gesture_event_details(action),
                    )
                    if machine.pending_command:
                        navigator.stop()
                        pending_action = {**action, "command": machine.pending_command, "_gesture": None}
                        pending_action["_pending_since"] = robot.getTime()
                        pending_action["_confirm_after"] = robot.getTime() + float(action.get("confirmation_delay_seconds", 0))
                        action_armed = True
                        update_route_display()
                        logger.event(
                            "gesture_route_override_pending", gesture=gesture,
                            command=machine.pending_command, route_choice=machine.route_choice,
                            previous_route=active_route_name, state=machine.state.value,
                            position=navigator.position(), simulation_seconds=robot.getTime(),
                            input_source="CAMERA", confirmation="NOD",
                        )
                        set_status("route change pending", pending_route_text())
                        # Do not consume a confirmation in the same iteration.
                        continue

        stationary_states = {
            TaskState.IDLE,
            TaskState.READY,
            TaskState.ARRIVED,
            TaskState.AT_PICKUP,
            TaskState.AT_DROPOFF,
            TaskState.PAUSED,
            TaskState.STOPPED,
        }
        if not action_armed and machine.state in stationary_states:
            action = scenario.next_action() if scenario_path else live_input.poll()
            if update_live_status():
                continue
            if action:
                if action.get("gesture", "").upper() == "SHAKE":
                    action = {**action, "command": "stop"}
                command = action.get("command", "")
                if not command:
                    gesture = action.get("gesture", "")
                    if machine.state not in {TaskState.IDLE, TaskState.STOPPED}:
                        set_control_mode("CAMERA", f"camera gesture: {gesture}")
                    outcome, _ = machine.accept_gesture(gesture, navigator.position())
                    logger.event(
                        "gesture_recognised",
                        gesture=gesture,
                        outcome=outcome,
                        state=machine.state.value,
                        input_source="CAMERA",
                        **gesture_event_details(action),
                    )
                    if outcome == "emergency_stop":
                        navigator.stop()
                        update_route_display()
                        set_status("safety stop", "head shake")
                    elif machine.pending_command:
                        navigator.stop()
                        pending_action = {**action, "command": machine.pending_command, "_gesture": None}
                        action_armed = True
                        update_route_display()
                        set_status("route change pending", pending_route_text())
                    else:
                        logger.event("gesture_ignored", gesture=gesture, state=machine.state.value)
                    continue
                original_command = command
                if not scenario_path:
                    report_tilt(action.get("gesture", "").upper(), "ignored_voice_priority", superseding_command=command)
                effective_command = (
                    live_startup_gate(command, machine.state)
                    if not scenario_path and not transcript_replay
                    else normalise_command(command)
                )
                accepted, status = machine.accept_command(effective_command or "")
                display_command = effective_command or original_command
                set_control_mode("MICROPHONE", f"voice command: {display_command}")
                logger.event(
                    "command_recognised",
                    command=display_command,
                    recognised_as=original_command if display_command != normalise_command(original_command) else None,
                    accepted=accepted,
                    status=status,
                    state=machine.state.value,
                    input_source="MICROPHONE",
                )
                set_status("command accepted" if accepted else "command rejected", f"{display_command}: {status}")
                if not accepted:
                    logger.event("route_failed", reason=status, state=machine.state.value)
                    expected = scenario.expected_terminal == "safe_rejection"
                    if scenario_path:
                        logger.result(pass_result=expected, final_state=machine.state.value, reason=status)
                        return 0 if expected else 3
                    continue
                if status == "emergency_stop":
                    navigator.stop()
                    update_route_display()
                    logger.event("safety_stop", source="voice", state=machine.state.value)
                    continue
                if status in {"activated", "already_active"}:
                    route_selection_error = None
                    navigator.stop()
                    last_safety_stop = None
                    active_route_name = None
                    active_route_request = None
                    update_route_display()
                    logger.event("system_activated", state=machine.state.value, movement_started=False, waiting_for_destination=True, input_source="MICROPHONE")
                    set_status("controls active; robot waiting", "say GO TO A, B, C, or S")
                    continue
                if status == "resume_navigation":
                    logger.event("navigation_resumed", command=command, state=machine.state.value)
                    set_status("navigation resumed", active_route_name or "route")
                    continue
                if status == "clarification_required":
                    navigator.stop()
                    logger.event("navigation_paused", command=command, state=machine.state.value)
                    set_status("paused for clarification", "say CONTINUE, ALTERNATIVE ROUTE, GO TO A/B/S, REVERSE, or STOP")
                    continue
                route_gesture = action.get("route_gesture")
                if route_gesture:
                    set_control_mode("CAMERA", f"camera route gesture: {route_gesture}")
                    gesture_outcome, _ = machine.accept_gesture(route_gesture, navigator.position())
                    logger.event("gesture_recognised", gesture=route_gesture, outcome=gesture_outcome, state=machine.state.value, input_source="CAMERA")
                action["_gesture"] = action.get("gesture") if scenario_path else None
                pending_action = action
                action_armed = status == "pending_confirmation"
                if action_armed and pending_destination():
                    route_selection_error = None
                    set_status("destination pending", pending_route_text())

            if not action and machine.state == TaskState.READY and completed:
                result = finish_success("execution_completed")
                if result is not None:
                    return result
            if not action and scenario_path and machine.state == TaskState.ARRIVED and scenario.expected_terminal == "destination_reached":
                expected_name = scenario.expected_final_position
                expected_position = WAYPOINTS.get(expected_name)
                position = navigator.position()
                within_tolerance = bool(expected_position and ((position[0] - expected_position[0]) ** 2 + (position[1] - expected_position[1]) ** 2) ** 0.5 <= 0.12)
                if not destination_verification_logged:
                    logger.event("destination_verified", destination=expected_name, position=position, within_tolerance=within_tolerance)
                    destination_verification_logged = True
                if within_tolerance and movie_path:
                    if not movie_stop_requested:
                        robot.movieStopRecording()
                        movie_stop_requested = True
                        logger.event("movie_recording_stop_requested", path=str(movie_path))
                        continue
                    result = finish_success("destination_reached")
                    if result is None:
                        continue
                    return result
                logger.result(pass_result=within_tolerance, final_state=machine.state.value, reason="destination_reached", final_position=position, actual_path_length=round(navigator.actual_path_length, 3))
                return 0 if within_tolerance else 9

        if action_armed and pending_action is not None:
            if robot.getTime() < float(pending_action.get("_confirm_after", 0)):
                navigator.stop()
                if scenario_path and robot.getTime() - pending_action["_pending_since"] >= .5 and not pending_action.get("_settled_logged"):
                    logger.event("pending_stop_sample", position=navigator.position(), simulation_seconds=robot.getTime(), motor_targets=[left.getVelocity(), right.getVelocity()])
                    pending_action["_settled_logged"] = True
                continue
            gesture = pending_action.get("_gesture")
            gesture_action = pending_action
            if not gesture:
                # Scenarios may supply a route tilt and its confirmation as
                # separate actions, just as physical live input does.
                live_action = scenario.next_action() if scenario_path else live_input.poll()
                if update_live_status():
                    action_armed = False
                    continue
                if live_action and live_action.get("gesture", "").upper() == "SHAKE":
                    stop_from_dashboard("head_shake")
                    if scenario_path and scenario.expected_terminal == "safe_stop":
                        logger.result(pass_result=True, final_state=machine.state.value, reason="expected_head_shake_stop")
                        return 0
                    continue
                if live_action and live_action.get("command"):
                    replacement_command = normalise_command(live_action["command"])
                    report_tilt(live_action.get("gesture", "").upper(), "ignored_voice_priority",
                                superseding_command=replacement_command or live_action["command"])
                    set_control_mode("MICROPHONE", f"voice command: {replacement_command or live_action['command']}")
                    if replacement_command == "stop":
                        machine.accept_command("stop")
                        navigator.stop()
                        update_route_display()
                        logger.event("safety_stop", source="voice", state=machine.state.value, input_source="MICROPHONE")
                        set_status("safety stop", "voice")
                        action_armed = False
                        pending_action = None
                        if scenario_path and scenario.expected_terminal == "safe_stop":
                            logger.result(pass_result=True, final_state=machine.state.value, reason="expected_voice_stop")
                            return 0
                    elif replacement_command and replacement_command.startswith("go to "):
                        previous_pending = machine.pending_command
                        previous_route_choice = machine.route_choice
                        accepted, status = machine.accept_command(replacement_command)
                        logger.event(
                            "command_recognised",
                            command=replacement_command,
                            accepted=accepted,
                            status=status,
                            state=machine.state.value,
                            input_source="MICROPHONE",
                            replaces_pending_command=previous_pending,
                        )
                        if accepted and status == "pending_confirmation":
                            route_selection_error = None
                            live_action["_gesture"] = None
                            pending_action = live_action
                            action_armed = True
                            logger.event(
                                "voice_destination_override_replaced",
                                previous_command=previous_pending,
                                command=replacement_command,
                                requested_destination=machine.destination,
                                previous_route_choice=previous_route_choice,
                                route_choice=machine.route_choice,
                                state=machine.state.value,
                                confirmation="NOD",
                                input_source="MICROPHONE",
                            )
                            set_status("voice destination updated", pending_route_text())
                        else:
                            machine.reset(activated=False, stopped=True)
                            navigator.stop()
                            update_route_display()
                            logger.event("safety_stop", source="invalid_replacement_command", command=replacement_command, state=machine.state.value)
                            set_status("safety stop", "invalid replacement command")
                            action_armed = False
                            pending_action = None
                    else:
                        machine.reset(activated=False, stopped=True)
                        navigator.stop()
                        update_route_display()
                        logger.event("safety_stop", source="conflicting_pending_command", command=live_action["command"], state=machine.state.value)
                        set_status("safety stop", "conflicting command")
                        action_armed = False
                        pending_action = None
                        set_control_mode("MICROPHONE", "command conflict requires START")
                    continue
                if not live_action or not live_action.get("gesture"):
                    continue
                gesture = live_action["gesture"]
                gesture_action = live_action
            outcome, request = machine.accept_gesture(gesture, navigator.position())
            set_control_mode("CAMERA", f"camera gesture: {gesture}")
            logger.event(
                "gesture_recognised",
                gesture=gesture,
                outcome=outcome,
                state=machine.state.value,
                input_source="CAMERA",
                **gesture_event_details(gesture_action),
            )
            if gesture not in {"TILT_LEFT", "TILT_RIGHT"} and request is None:
                set_status("gesture", f"{gesture}: {outcome}")
            if outcome == "emergency_stop":
                navigator.stop()
                update_route_display()
                action_armed = False
                pending_action = None
                logger.event("safety_stop", source="head_shake", state=machine.state.value)
                set_control_mode("MICROPHONE", "head shake stop requires START")
                capture("safety_stop_head_shake")
                if scenario.expected_terminal == "safe_stop":
                    logger.result(pass_result=True, final_state=machine.state.value, reason="expected_head_shake_stop")
                    return 0
            elif request:
                route_selection_error = None
                navigator.start(request.points)
                active_route_request = request
                active_route_name = request.name
                update_route_display(request)
                logger.event("command_confirmed", simulation_seconds=robot.getTime(), position=navigator.position(), command=pending_action["command"], route=request.name, route_length=round(route_length(request.points), 3), route_segments=request.segment_ids, origin=request.origin, destination=request.destination, alternative=request.alternative, state=machine.state.value, confirmation_source="CAMERA")
                logger.event("route_started", route=request.name, state=machine.state.value, trigger_source="camera_nod_confirmation")
                confirmed_choice = "ALTERNATIVE" if request.alternative else "SHORTEST"
                set_status("route started", f"TO {request.destination}: {confirmed_choice}; {request.name}")
                # Supervisor appearance writes become visible on the following
                # rendered frame, so defer evidence capture by one step.
                capture(f"route_selected_{request.name.lower()}", defer_frames=1)
                action_armed = False
                pending_action = None
            elif outcome in {"route_short_selected", "route_long_selected", "route_alternative_selected", "route_selection_required"}:
                pending_action["_gesture"] = None
            elif outcome in {"current_position_outside_route_network", "no_route_available", "unknown_destination", "alternative_route_unavailable", "already_at_destination"}:
                navigator.stop()
                logger.event("route_failed", reason=outcome, state=machine.state.value, position=navigator.position())
                message = f"TO {machine.destination}: {outcome.replace('_', ' ')}; robot remains stopped"
                route_selection_error = (f"Already at {machine.destination}; no new route" if outcome == "already_at_destination"
                                         else f"TO {machine.destination}: {(canonical_choice(machine.route_choice) or 'route').upper()} unavailable")
                logger.event("route_selection_unavailable", destination=machine.destination,
                             route_choice=canonical_choice(machine.route_choice), message=message, state=machine.state.value)
                set_status("route rejected", message)
                action_armed = False
                pending_action = None
            elif outcome == "pickup_completed":
                logger.event("command_confirmed", command=pending_action["command"], state=machine.state.value)
                action_armed = False
                pending_action = None
            elif outcome != "ignored_gesture":
                action_armed = False
                pending_action = None

        if machine.state in machine.MOVING_STATES:
            if os.environ.get("EPUCK_FORCE_LOCALISATION_LOSS") == "1":
                navigator.force_localisation_loss = True
            outcome, details = navigator.step()
            last_navigation_details = dict(details)
            if outcome == "obstacle":
                last_safety_stop = "proximity"
                machine.reset(activated=False, stopped=True)
                update_route_display()
                set_control_mode("MICROPHONE", "obstacle safety stop requires START")
                set_status("safety stop", "obstacle detected")
                logger.event("safety_stop", source="proximity", details=details, state=machine.state.value)
                capture("safety_stop_obstacle")
                expected = scenario.expected_terminal == "safe_obstacle_stop"
                logger.result(pass_result=expected, final_state=machine.state.value, reason="obstacle", final_position=navigator.position(), maximum_sensor_peak=navigator.maximum_sensor_peak, actual_path_length=round(navigator.actual_path_length, 3))
                return 0 if expected else 4
            if outcome == "localisation_lost":
                last_safety_stop = "localisation"
                machine.reset(activated=False, stopped=True)
                update_route_display()
                set_control_mode("MICROPHONE", "localisation safety stop requires START")
                set_status("safety stop", "localisation lost")
                logger.event("safety_stop", source="localisation", details=details, state=machine.state.value)
                capture("safety_stop_localisation")
                expected = scenario.expected_terminal == "safe_localisation_stop"
                logger.result(pass_result=expected, final_state=machine.state.value, reason="localisation_lost", actual_path_length=round(navigator.actual_path_length, 3))
                return 0 if expected else 6
            if outcome == "complete":
                transition = machine.route_finished()
                update_route_display()
                set_status("arrived", transition)
                logger.event("waypoint_reached", transition=transition, position=navigator.position(), state=machine.state.value)
                capture(f"waypoint_{transition}", defer_frames=1)
                if transition == "destination_reached":
                    logger.event("destination_reached", position=navigator.position(), state=machine.state.value)
                    capture("destination_reached", defer_frames=1)
                if transition == "execution_completed":
                    completed = True
                    logger.event("execution_completed", position=navigator.position(), state=machine.state.value)
                    if camera_enabled:
                        screenshot_dir.mkdir(parents=True, exist_ok=True)
                        camera.saveImage(str(screenshot_dir / "final.png"), 100)
                    capture("99_final_overview")
                    if movie_path:
                        robot.movieStopRecording()
                        movie_stop_requested = True
                        logger.event("movie_recording_stop_requested", path=str(movie_path))
            elif outcome == "waypoint":
                logger.event("waypoint_reached", position=navigator.position(), state=machine.state.value, details=details)
            elif outcome == "moving" and loop_count % 100 == 0:
                logger.event("navigation_progress", state=machine.state.value, route=active_route_name, details=details)
                set_status("navigating", f"{active_route_name} → {machine.active_destination}")
    if live_input is not None:
        live_input.close()
    if dashboard is not None:
        dashboard.close()
    logger.result(pass_result=False, final_state=machine.state.value, reason="webots_ended")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Controller failure: {error}", file=sys.stderr)
        raise
