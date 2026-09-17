# Code explanation and technology guide

## 1. Purpose of this document

September 11 override regression: `tests/test_live_override_controller.py`
executes the live controller loop with fake devices. `run_live()` supplies
time-separated speech/gesture events and records motor commands; its tests check
the pending stop, mode handoff, missing nod, and shake cancellation. The Docker
runner also verifies actual travel before override, a two-second stationary
confirmation interval, and arrival at B. See `VOICE_OVERRIDE_FIX.md`.

This document explains the source code of the multimodal e-puck waypoint-navigation project. It is organised by file, class, function, and system action. It does not explain individual lines of code.

The submitted application is centred on:

- `worlds/epuck_waypoint_navigation.wbt`;
- `controllers/epuck_waypoint_controller/`;
- `tools/run_live.py` for live Windows operation;
- `tools/run_docker_validation.ps1` and `tools/run_validation.py` for repeatable Webots testing.

The older Toyota world and `gesture_vehicle_controller` are development references. They are not required by the final e-puck submission.

## 2. System architecture

The project is divided into six main layers:

1. **Input layer:** Vosk converts microphone audio into a small allowed set of commands. MediaPipe and OpenCV convert webcam frames into head-pose measurements and gestures.
2. **Fusion and task layer:** `TaskMachine` checks whether a voice command or gesture is valid in the current state.
3. **Route-planning layer:** `RouteGraph` calculates a shortest or alternative path from the robot's measured position.
4. **Navigation and safety layer:** `WaypointNavigator` uses GPS, compass, proximity sensors, and differential wheel speeds to follow the route safely.
5. **Traceability layer:** the dashboard displays the live input mode, camera preview, recognition evidence, state, route, and safety information. `ValidationLogger` records technical events without saving audio or camera frames.
6. **Verification layer:** unit tests and Docker Webots scenarios reproduce normal journeys, destination changes, failures, and safety stops.

### Main live data flow

```text
Microphone -> sounddevice -> Vosk -> bounded command
                                         |
Webcam -> OpenCV -> MediaPipe -> gesture  |
                    |                    v
                    +------------> LocalMultimodalInput
                                         |
                                         v
                                  TaskMachine
                                         |
                                         v
                                    RouteGraph
                                         |
                                         v
                              WaypointNavigator
                                         |
                             Webots motors/sensors

All stages -> dashboard snapshot + technical event log
```

## 3. Technologies used

| Technology | Use in this project |
| --- | --- |
| Python 3 | Main controller, input processing, task logic, tests, replay tools, and validation orchestration. |
| Webots R2025a | e-puck simulation, world physics, motors, GPS, compass, proximity sensors, keyboard input, screenshots, and movies. |
| Webots Python Controller API | Connects Python code to the simulated robot and Supervisor functions. |
| Vosk | Offline, local speech recognition with a bounded grammar. No cloud speech service is used. |
| sounddevice / PortAudio | Captures 16-bit mono microphone samples and delivers them to Vosk through callbacks. |
| MediaPipe Face Mesh | Detects facial landmarks used to estimate relative head roll, pitch, and yaw. |
| OpenCV | Opens webcams/video files, handles frames, draws the dashboard, and encodes intermediate demonstration video. |
| NumPy | Frame arrays, dashboard canvases, and numerical image operations. |
| Docker Compose | Runs the official Webots image in a repeatable Linux environment. |
| Xvfb | Supplies a virtual display for rendered Webots tests inside Docker. |
| Mesa software rendering | Provides graphics rendering when Docker has no physical GPU display. |
| PowerShell | Windows launch wrappers, video assembly, package creation, and ZIP verification. |
| FFmpeg / FFprobe | Measures, crops, scales, blurs, captions, combines, and encodes demonstration videos. |
| JSON and NDJSON | Scenario fixtures, transcript schedules, reports, event logs, and verification evidence. |
| `unittest` | Offline unit and integration testing. |
| SHA-256 | Checks the integrity of packaged submission files. |
| WBT/PROTO/VRML syntax | Defines the Webots world, e-puck model, materials, geometry, sensors, and visual assets. |

`requirements.txt` pins MediaPipe, JAX/JAXLIB, NumPy, OpenCV, sounddevice, and Vosk versions that work together in the Windows virtual environment. JAX is included because it is part of the compatible MediaPipe dependency stack used by this project; the navigation controller does not use JAX directly.

## 4. Runtime action sequences

### 4.1 Startup and activation

1. `tools/run_live.py` finds Webots, the local Python environment, and the Vosk model.
2. It runs `tools/check_live_inputs.py` to prove that microphone callbacks and webcam frames are arriving.
3. Webots loads `epuck_waypoint_navigation.wbt` and starts `epuck_waypoint_controller.py`.
4. The task machine starts in `IDLE`, the control mode starts as `MICROPHONE`, and both motors remain stopped.
5. The dashboard tells the user to say `START`.
6. `START` changes the state to `READY` but does not create a route or move the robot.

### 4.2 Starting a destination journey

1. In `READY`, the user says `GO TO A`, `GO TO B`, `GO TO C`, or `GO TO S`.
2. The command becomes pending and the robot remains stationary.
3. The shortest route is the default. A left tilt explicitly selects the shortest route, while a right tilt selects an alternative route.
4. A nod confirms the pending destination.
5. `RouteGraph.plan()` creates a route from the current GPS position.
6. `WaypointNavigator.start()` loads the route, and the controller changes to `NAVIGATING`.
7. A valid gesture changes the dashboard to Camera Mode.

### 4.3 Voice interruption while moving

1. The robot may be moving in Camera Mode.
2. A valid voice destination command has priority over an ordinary gesture in the same controller cycle.
3. The navigator stops, the old route is paused, the new destination becomes pending, and the dashboard changes to Voice Mode.
4. A newer destination command can replace the pending destination before confirmation.
5. A valid gesture switches back to Camera Mode. A nod confirms the shortest route; a right tilt can select an alternative before the nod.
6. Replanning begins from the robot's measured GPS position rather than teleporting to a predefined route start.

### 4.4 Safety actions

- Voice `STOP` and a head shake are global safety commands.
- The dashboard `STOP` button and closing the dashboard also stop the robot.
- The Webots emergency key, obstacle threshold, lost GPS/compass data, lost live input, absent face during live operation, and controller errors all fail safely.
- A safety stop sets both wheel velocities to zero, clears pending work, changes the state to `STOPPED`, and requires a new `START`.
- `RESET AT S` stops first and requests a full Webots reset to the initial start position.

### 4.5 Privacy and traceability

- Microphone samples and webcam frames are processed locally.
- Only the newest camera preview frame is retained temporarily for display.
- Raw audio, live video, face landmarks, and frames are not written into normal runtime logs.
- Technical logs contain commands, decisions, gesture categories, routes, states, positions, device health, and safety results.

## 5. Production controller package

### `controllers/epuck_waypoint_controller/__init__.py`

This empty package marker allows the controller directory to be treated as a Python package. It contains no runtime logic.

### `controllers/epuck_waypoint_controller/epuck_waypoint_controller.py`

This is the main Webots controller and the integration point for every production module.

#### `main()`

`main()` performs the complete controller lifecycle:

- creates the Webots `Supervisor` object;
- retrieves wheel motors, GPS, compass, proximity sensors, keyboard, world labels, waypoint nodes, and display nodes;
- selects deterministic scenario input, transcript/gesture replay input, or real microphone/webcam input;
- creates `TaskMachine`, `WaypointNavigator`, `ValidationLogger`, and the optional dashboard;
- keeps the robot stationary in `IDLE` until a valid `START`;
- applies safety priority, voice priority, task-state checking, gesture confirmation, route planning, navigation, arrival handling, screenshots, movie handling, and result generation;
- exits cleanly when a deterministic scenario succeeds or fails, while live mode continues until Webots ends or reset is requested.

The following functions are local to `main()` because they share the live controller objects.

#### `set_control_mode(mode, reason)`

Changes the persistent dashboard mode between `MICROPHONE` and `CAMERA`. It records an `input_mode_changed` event only when the mode actually changes.

#### `track_safety_event(entry)`

Listens to technical events and remembers the latest safety-stop source for dashboard display.

#### `set_status(event, detail)`

Updates the Webots on-screen status label and avoids repeatedly drawing the same message.

#### `update_locator()`

Moves the non-colliding visual locator so the enlarged robot remains easy to see from the overhead camera.

#### `update_route_display(request=None)`

Updates the displayed route name and active destination marker. It changes only visual indicators; the floor does not contain route lines.

#### `update_live_status()`

Supervises microphone and camera readiness. It logs disconnect/reconnect transitions, stops safely when required devices are lost, and requires camera recalibration after recovery.

#### `export_capture(name)`

Asks Webots to save a configured screenshot for deterministic evidence runs.

#### `capture(name, defer_frames=0)`

Schedules a screenshot immediately or after a small frame delay. The delay allows Webots visual fields to update before evidence is captured.

#### `gesture_event_details(action)`

Extracts non-identifying replay metadata, such as gesture source and scheduled time, for event logs.

#### `dashboard_snapshot()`

Builds the JSON-safe status dictionary consumed by `LiveTraceDashboard`. It includes device health, microphone callbacks and level, partial/final voice decisions, gesture evidence, control mode, task state, pending command, route, GPS position, next waypoint, distance, sensor peak, and safety source. Camera pixels are passed separately and never placed in this dictionary.

#### `stop_from_dashboard(source="dashboard_stop")`

Implements dashboard and window-close stopping. It stops both motors, clears the route and pending command, changes to `STOPPED`, returns to Voice Mode, and logs the source.

#### `update_dashboard()`

Consumes the newest transient camera frame, renders the latest snapshot, and checks for `STOP`, `RESET`, or window-close actions.

#### `finish_success(reason)`

Finalises deterministic runs by verifying the expected destination/state, writing metrics and results, stopping recording, and returning the correct process status.

### `controllers/epuck_waypoint_controller/model.py`

This file contains pure task and route logic. It does not import Webots, OpenCV, Vosk, or MediaPipe, so it can be tested quickly without hardware or a simulator.

#### Data definitions

- `Point`: an `(x, y)` world coordinate.
- `WAYPOINTS`: coordinates for S, A, B, and C.
- `ROUTES`: physical corridor points for S-A short/long, A-C, A-B, and B-C, plus reverse paths.
- `TaskState`: all general navigation, legacy workflow, paused, arrived, and stopped states.
- `RouteRequest`: immutable route output containing name, points, corridor identities, origin, destination, and alternative flag.
- `_GraphEdge`: internal physical edge, length, and corridor membership.

#### `route_length(points)`

Adds the Euclidean distance between consecutive route points.

#### `_segment_key(start, end)`

Creates a direction-independent key so the same corridor is not duplicated when traversed in reverse.

#### `RouteGraph.__init__()`

Converts the canonical physical routes into an undirected graph of unique corridor edges.

#### `RouteGraph._node_id(point)`

Creates a stable string identifier for a graph coordinate.

#### `RouteGraph._project(point, start, end)`

Projects the robot's measured position onto a corridor segment and returns both the projected point and its position along the segment.

#### `RouteGraph._adjacency(current)`

Builds graph adjacency in both directions. If the robot is between waypoints, it inserts a temporary current-position node connected to the nearest valid corridor. A position farther than the safe graph tolerance is rejected.

The nearest edge is split at the projected position, or its existing endpoint
is reused. An off-corridor current position connects only to that projection.
The unsplit edge is removed from this temporary graph, preventing a candidate
alternative from retracing the current position and then following shortest.
The map and physical corridors remain unchanged.

#### `RouteGraph._enumerate_paths(adjacency, source, target, limit=8)`

Uses a cost-ordered queue to find several unique, loop-free candidate paths. Producing multiple candidates makes a real alternative route possible.

#### `RouteGraph._display_route_ids(points)`

Determines which canonical corridors a calculated path actually uses for status and logging. It avoids claiming unrelated corridor names when physical segments are shared.

#### `RouteGraph.plan(current, destination, alternative=False)`

Validates the destination, handles already-arrived cases, inserts the live position, chooses the shortest or second distinct path, and returns a complete `RouteRequest`.

An unavailable alternative raises `alternative_route_unavailable`; requesting
one after arrival raises `already_at_destination`. Neither silently substitutes
shortest. Legacy long-route requests also carry an accurate alternative flag.

#### `normalise_command(text)`

Converts case, spacing, and approved aliases into the bounded grammar. Unlisted natural-language text returns `None` and cannot move the robot.

#### `live_startup_gate(command, state)`

Applies only to physical live startup. In `IDLE` or `STOPPED`, it safely reduces `start`, `start A`, and `start B` recognition results to standalone `start`. This prevents Vosk from accidentally selecting a destination when a short spoken `start` receives an A/B suffix. Once the controller is active, the legacy `start A` and `start B` meanings remain available.

#### `TaskMachine.__init__()`

Starts the workflow in `IDLE` at S and initialises all pending, active-route, pickup, pause, and destination fields.

#### `TaskMachine.reset(activated=True, stopped=False)`

Clears pending and active task data. It returns to `READY`, `IDLE`, or `STOPPED` according to the supplied flags.

#### `TaskMachine._pause(direction=None)`

Remembers the previous moving state and enters `PAUSED`, optionally recording the clarification direction.

#### `TaskMachine._command_destination(command)`

Extracts A, B, C, or S from a normalised `go to` command.

#### `TaskMachine.accept_command(command)`

Applies the state rules for every voice command. It handles activation, global stop, destination requests, mid-route replacement, continue/forward, reverse, alternative route, legacy pickup/drop-off/return, invalid-state rejection, and newest-pending-command replacement. Movement-bearing commands become pending rather than starting immediately.

#### `TaskMachine.accept_gesture(gesture, current_position=None)`

Applies gesture meaning to the current pending command. Shake stops globally, tilts select route type, and nod confirms. During travel, or a route pause without a pending command, a tilt creates a pending `go to` request for the active destination and selects shortest/alternative. The live controller stops the motors and waits for a later nod, then replans from the measured position, as for a voice route override. On confirmation it calls the general graph planner or creates the correct legacy route.

A gesture-only route change preserves the interrupted legacy pickup, drop-off, or return phase through `pending_route_state`, so arrival still enables the next task command. Repeating the same pending destination preserves both this marker and the selected route. A different spoken destination clears the marker and uses general navigation. Deterministic scenarios can also supply a tilt and its nod or stop as separate actions.

Each detected route tilt generates a `route_selection` event and a forced
terminal status line naming destination, shortest/alternative choice, and nod
requirement. Ignored tilts explain voice priority or missing task context.
Dashboard snapshots distinguish pending destination/choice from the previous
active route and suppress old next-waypoint details during confirmation.
The shared `route_feedback.route_status_text()` formatter drives the console's
`[route]` transition lines, Webots status label, and dashboard `Route status`
row/current-event heading. It distinguishes awaiting confirmation, navigating,
paused, arrived, and START-required states. Historical tilt events remain
timestamped descriptions without stale confirmation instructions. The events
panel uses the snapshot supplied to the current render, not a cached snapshot.
The persistent status remains visible during detector re-arming; moving
re-arm guidance says that travel continues and prepares the next gesture.
Frequent posture diagnostics do not displace route selections in the timeline.
The live launcher forwards Webots controller stdout/stderr to the terminal.

#### `TaskMachine.route_finished()`

Updates the task state and current location after the navigator completes a route. It distinguishes a general arrival, pickup arrival, drop-off arrival, and full return-to-S completion.

#### `TaskMachine._pickup_route()`

Creates S-to-A short/long or S-to-A-to-B legacy pickup routes.

#### `TaskMachine._dropoff_route()`

Creates A-to-C or B-to-C based on the current pickup location.

#### `TaskMachine._return_route()`

Creates C-to-A-to-S and reverses the selected S-A corridor for the final return leg.

#### `is_emergency_key(key, end_key)`

Keeps keyboard emergency-key matching independently testable.

### `controllers/epuck_waypoint_controller/navigation.py`

This file translates route points into differential wheel speeds.

#### `wrap_angle(angle)`

Normalises an angle to the range from `-pi` to `+pi`, preventing incorrect long turns across the angle boundary.

#### `WaypointNavigator.__init__(...)`

Stores Webots devices and navigation limits, including maximum speed, waypoint tolerance, obstacle threshold, path-length counters, and optional forced localisation loss for tests.

#### `WaypointNavigator.start(points)`

Loads a route and removes its first point because that point represents the robot's current position.

#### `WaypointNavigator.stop()`

Sets both motor velocities to zero.

#### `WaypointNavigator.position()`

Returns the current two-dimensional GPS position.

#### `WaypointNavigator.step()`

Performs one navigation cycle. It reads proximity sensors, GPS, and compass; checks finite localisation and obstacles; updates path length; detects waypoint/route completion; calculates heading error; and applies bounded differential wheel speeds. It returns a status such as `moving`, `waypoint`, `complete`, `obstacle`, or `localisation_lost` together with technical details.

### `controllers/epuck_waypoint_controller/input_adapters.py`

This file contains live input, deterministic replay, gesture state, device recovery, and traceability adapters.

#### `parse_vosk_result(payload, confidence_threshold=0.65)`

Compatibility helper that returns only an accepted normalised command or `None`.

#### `parse_vosk_decision(payload, confidence_threshold=0.65)`

Parses final Vosk JSON, calculates the minimum word confidence, normalises the text, and returns transcript, command, confidence, acceptance, threshold, and reason. Standalone `START` uses a safe 0.50 threshold because it cannot move the robot; movement-related commands retain 0.65.

#### `classify_pose_history(history)`

Simple history-based classifier used by offline logic tests for smoothed tilt, nod, and shake evidence.

#### `GestureStateDetector`

This stateful detector converts a stream of relative roll, pitch, and yaw values into one-shot gestures.

- `__init__()` creates smoothing histories, thresholds, hold timers, nod/shake phases, cooldown, and re-arming state.
- `face_lost()` clears incomplete motion so a disappearing face cannot complete an old gesture later.
- `update(pose, now)` smooths pose, requires sustained evidence, recognises tilts/nods/shakes, enforces cooldown, and requires neutral re-arming.
- Shake evidence must reach both sides of calibrated neutral yaw as well as meeting the existing span threshold. A large one-sided face turn cannot meet this condition. Roll tilts retain their existing route-selection meaning.
- `_emit(gesture, now, evidence)` records the confirmed gesture and detector evidence.
- `_clear_motion()` clears tilt/nod candidate state.
- `_clear_yaw()` clears shake direction history.
- `_cooldown_ready(now)` reports whether another gesture may be emitted.
- `trace_status(now)` returns calibration-independent pose, candidate, confirmed gesture, evidence, armed state, and cooldown for the dashboard.
- Neutral-frame progress and axes still outside the neutral range let the dashboard explain re-arming without changing recognition thresholds.
- `tilt_gate`, direction, hold progress, and blocked axes explain an armed but unaccepted tilt. The controller logs categorical detection status on changes at most twice per second, with a five-second refresh, so physical missed-input reports can be investigated without retaining poses or media.
- `_is_neutral(pose)` checks whether the head has returned close enough to neutral to re-arm.

#### `ScenarioInput`

Reads deterministic action lists from scenario JSON.

- `__init__()` loads actions and expected terminal conditions.
- `peek_action()` views the next action without consuming it.
- `next_action()` consumes and returns the next action.

#### `TranscriptReplayRecognizer`

Replays timed, already-transcribed text without opening a microphone.

- `__init__()` loads the fixture and timing source.
- `poll()` releases due transcripts through the production command decision logic.
- `close()` marks the adapter inactive.

#### `GestureEventReplayRecognizer`

Replays only a previously verified production-classifier gesture manifest.

- `__init__()` validates the manifest, source claim, timing, and expected gesture sequence.
- `poll()` emits gestures at their recorded schedule.
- `trace_status()` exposes replay evidence without frames.
- `consume_preview_frame()` returns no frame because this event replay contains categories only.
- `close()` ends replay.

#### `VoskCommandRecognizer`

Implements real offline microphone recognition.

- `__init__()` loads the local Vosk model, queries the selected input device, tries supported sample rates, creates the bounded grammar recognizer, explicitly enables word-confidence output, opens a mono `int16` stream, and proves callbacks are arriving before declaring readiness.
- `_capture(...)` receives microphone bytes, counts callbacks/bytes, estimates live signal peak, records driver status, and places only bounded recent samples in a queue.
- `poll()` detects dead streams, sends queued samples to Vosk, publishes partial text, applies final bounded-command confidence filtering, and returns an accepted command.
- `close()` stops and closes the PortAudio stream.
- `ready` reports whether the stream exists and is active.

#### `MediaPipeGestureRecognizer`

Implements real webcam or video-file gesture recognition.

Head-pose geometry uses the image aspect ratio and measures nose displacement
in coordinates aligned with the eye line. This prevents a pure roll tilt from
creating false yaw and failing the tilt gate. Roll is measured in image-space
radians; upright pitch/yaw retain their existing scales and all detector
thresholds remain unchanged. Synthetic geometry tests cover repeated tilts,
nods, shakes, aspect ratios, and an offset neutral posture; they do not replace
physical camera acceptance.

- `__init__()` loads OpenCV and MediaPipe, opens a source, creates Face Mesh, creates `GestureStateDetector`, and prepares neutral calibration and transient preview storage.
- `_open_camera(requested)` tries requested/automatic camera indices and Windows backends, requires stable frames, and reports the actual device/backend/resolution.
- `_pose(landmarks)` derives approximate roll, pitch, and yaw from selected facial landmarks relative to the calibrated neutral pose.
- `poll(now)` reads one frame, detects a face, completes neutral calibration, updates the gesture detector, draws transient trace overlays, and returns a gesture when confirmed.
- `close()` releases the camera/video and MediaPipe resources.
- `consume_preview_frame()` returns the newest frame once and then clears it.
- `trace_status()` returns JSON-safe calibration, pose, face box, detector, camera, and gesture evidence.
- `ready` reports whether frames are still available.
- `calibrated` reports whether a neutral pose has been learned.

#### `LocalMultimodalInput`

Combines voice and camera adapters and manages independent recovery.

- `__init__()` stores device selections/factories, attempts both connections, and optionally fails closed in strict mode.
- `_connect_missing(force=False)` reconnects unavailable voice/camera devices when their retry deadline is reached.
- `_close_adapter(adapter)` safely closes any adapter.
- `_disconnect_voice(error)` closes the failed microphone and schedules retry.
- `_disconnect_gesture(error)` closes the failed camera and schedules retry/recalibration.
- `poll()` polls both inputs in the same cycle. Shake has global safety priority; otherwise a valid voice command becomes the primary action while an accompanying route/nod gesture can still be retained.
- `face_present`, `ready`, `voice_ready`, `gesture_ready`, and `gesture_calibrated` expose health properties.
- `status()` returns only device/task-safe status fields.
- `trace_status()` adds microphone callbacks/level/partial/final decisions and gesture evidence, but never camera pixels.
- `voice_final_decision` retains the latest nonempty final result across partials and silence. It includes per-word confidences and a per-recogniser decision ID. The controller logs these final decisions once per reconnect/ID, including rejections, without recording audio or head-pose traces.
- The bounded phrase `go to alpha` normalises to `go to A`; it uses the same confidence threshold, activation gate, and nod requirement.
- `consume_preview_frame()` keeps camera pixels on the separate transient dashboard path.
- `close()` releases both devices.

### `controllers/epuck_waypoint_controller/live_dashboard.py`

This file implements the Windows-host OpenCV traceability dashboard.

#### `DashboardAction`

Defines the bounded dashboard commands `STOP` and `RESET`.

#### `LiveTraceDashboard`

- `__init__()` configures window size, 8 FPS refresh limiting, colours, event history, action queue, and render timing.
- `_create_window()` creates the OpenCV window and mouse callback only when live display is enabled.
- `_inside(x, y, box)` performs reusable button hit testing.
- `_mouse_callback(...)` converts mouse release events into dashboard actions.
- `handle_click(x, y)` queues `STOP` or `RESET` only when the correct button is clicked.
- `poll_action()` returns one queued dashboard action.
- `record_event(entry)` converts a technical event into a short timestamped rolling message.
- `update(snapshot, frame, force=False)` stores only the newest frame, renders at the allowed rate, shows the window, and detects window closure as a safety stop.
- `render(snapshot, frame)` constructs the full dashboard canvas.
- `_draw_preview(...)` letterboxes the transient camera frame, shows `LIVE - NOT RECORDED`, draws the face box, and draws simple pose indicators.
- `_draw_input_panel(...)` displays Voice/Camera Mode, device readiness, microphone level/callbacks, partial/final speech, calibration, pose, gesture, cooldown, decision, and recovery information.
- `_draw_robot_panel(...)` displays state, pending command, confirmation requirement, route, origin/destination, GPS, next waypoint, remaining distance, proximity peak, and safety source.
- `_draw_next_step(...)` wraps and displays the current operator instruction.
- `next_step_instruction(snapshot)` selects practical instructions for startup, device problems, calibration, face loss, pending confirmation, detector re-arming, movement, Voice/Camera switching, paused navigation, arrival, and safety restart.
- `_draw_events(...)` displays recent technical events.
- `_draw_buttons(...)` draws `STOP` and `RESET AT S`.
- `_draw_rows(...)` aligns and truncates panel rows consistently.
- `_ready_text()`, `_ready_color()`, `_voice_decision_text()`, and `_recovery_text()` convert raw values into readable status text and colours.
- `mean_render_ms` reports average dashboard render cost.
- `close()` destroys the dashboard window and discards the transient frame.

### `controllers/epuck_waypoint_controller/validation.py`

#### `ValidationLogger.__init__(run_dir, append=False)`

Creates or appends an NDJSON event file, starts a new session identifier, and prepares in-memory events/listeners.

#### `add_listener(listener)`

Allows the dashboard to receive technical events without coupling safety logic to rendering.

#### `event(name, **details)`

Adds timestamp and session ID, appends the event to memory and NDJSON, and notifies listeners. Listener errors are deliberately ignored so display failures cannot interfere with robot safety.

#### `result(**details)`

Calculates command acceptance, gesture, route, pause/resume, destination-change, waypoint, safety, failure, response-time, duration, and success metrics, then writes `result.json`.

## 6. Webots world and model files

### `worlds/epuck_waypoint_navigation.wbt`

This is the submitted world. It defines:

- a 32 ms Webots timestep and overhead `MAIN_VIEW`;
- the textured floor and enclosed approximately 6 m by 5 m environment;
- outer and interior collision walls;
- the optional test blocker used by deterministic obstacle scenarios;
- S, A, B, and C marker solids and original box-stroke labels;
- non-blocking benches/plants and presentation textures;
- active destination and robot locator visuals;
- the e-puck robot using the submitted Python controller;
- GPS, compass, wheel motors, and `ps0` through `ps7` from the e-puck PROTO;
- Supervisor access required for reset, screenshots, labels, and evidence.

The world contains no coloured floor-route geometry. Navigation uses the route graph stored in Python.

### `worlds/head_gesture_car.wbt`

This is the older Toyota development world. It uses remote Webots PROTO resources and `gesture_vehicle_controller.py`. It is kept only as a legacy reference and is excluded from the final submission ZIP.

### `protos/vendor/epuck/E-puck.proto`

Vendored Webots R2025a e-puck model. It defines the physical robot, wheels, motors, sensors, camera options, body appearance, physics, and controller-facing device names. Vendoring makes the submitted world independent of Webots' online asset downloader.

### `protos/vendor/epuck/E-puckDistanceSensor.proto`

Defines an individual e-puck infrared proximity sensor, including pose, lookup behaviour, and appearance. The main e-puck PROTO instantiates the eight `ps0`-`ps7` sensors.

### Appearance PROTO files

- `BrushedSteel.proto`: metal-like material used by selected world objects.
- `PorcelainChevronTiles.proto`: textured chevron floor material.
- `RoughConcrete.proto`: wall/concrete appearance.
- `VarnishedPine.proto`: wood appearance used by benches/decorative objects.

The corresponding `textures/` images provide base colour, normal, roughness, occlusion, and metalness maps. They affect presentation only and do not control the robot.

## 7. Live and validation tools

### `tools/setup_client.py`

`verify_manifest(root)` verifies each packaged SHA-256 hash and rejects paths
outside the extracted project. `main()` requires Windows/Python 3.12 64-bit,
creates a machine-local .venv, installs requirements unless --check-only was
requested, checks dependencies/imports/tests, discovers Webots, and writes a
technical readiness report. It never marks physical devices verified without
the client checks described in AGENTS.md.

`run_live.live_environment(base)` strips inherited EPUCK_* replay/fault flags,
stale microphone selection, and conflicting Python environment paths before
launch. The Windows controller bootstrap selects the project's local .venv,
and default model/log paths are resolved from the source file's project root.

### `tools/run_live.py`

#### `resolve_webots(explicit=None)`

Searches an explicit path, `WEBOTS_EXECUTABLE`, system `PATH`, Program Files, Local AppData, and the development fallback. It returns the first real Webots executable.

#### `main()`

Parses camera/microphone options, lists microphones when requested, checks the virtual environment/model/Webots, creates a live evidence directory, runs device preflight, optionally requires complete readiness, sets environment variables, and launches the submitted world in real-time mode.

### `tools/check_live_inputs.py`

#### `main()`

Creates `LocalMultimodalInput` without recording media, retries until timeout, and reports:

- selected device names and formats;
- microphone callback count, byte count, peak level, partial text, final decision, and whether the callback pipeline is proven;
- camera index, backend, resolution, face presence, and calibration state;
- reconnect/error state and privacy confirmation.

It closes both devices before exiting and optionally writes only the technical JSON report.

### `tools/run_validation.py`

This is the main deterministic Webots test runner. Its scenario dictionaries describe canonical workflows, general point-to-point journeys, destination changes, alternative routes, reverse/continue actions, transcription inputs, safety stops, blocked corridors, lost localisation, absent face, and controller failure.

#### `preflight()`

Checks that Webots, the world, controller, and required project files exist before starting a scenario.

#### `run_tests()`

Runs the portable Python unit suite before and after Webots to detect regressions in the exact mounted project.

#### `run_scenario(name, index, visible, record_demo=False)`

Creates an isolated run directory and scenario JSON, configures environment-based fault injection/evidence options, starts Webots in batch mode, waits for a result with a bounded timeout, terminates remaining processes, and returns the pass result and evidence directory.

#### `main()`

Expands suite names such as workflows, navigation changes, transcriptions, and safety into scenarios; repeats them; collects results; runs postflight tests; writes an aggregate summary; and returns a non-zero status if anything fails.

### `tools/run_docker_validation.ps1`

This PowerShell wrapper validates arguments, confirms Docker exists, constructs `docker compose run --rm`, forwards scenario/repeat/render/recording options, and returns Docker's real exit code.

### `compose.webots.yaml`

Defines the official `cyberbotics/webots:R2025a-ubuntu22.04` service, 1 GB shared memory, software graphics variables, project mount, Xvfb display, and default validation command.

## 8. Recorded gesture and demonstration tools

### `tools/analyze_gesture_video.py`

#### `analyze(video, output, realtime=True)`

Runs a recorded clip through the production `MediaPipeGestureRecognizer`, preserves video timestamps for hold/cooldown behaviour, counts face-present frames, identifies face-loss segments, records emitted gesture categories/times/evidence, and writes only a technical report.

#### `main()`

Parses the clip, output, and real-time/fast options, calls `analyze()`, and prints JSON.

### `tools/build_gesture_control_sequence.py`

#### `build(source, output, manifest_path)`

Cuts selected consented portions of the source gesture clip into a staged calibration/tilt/nod/shake sequence, adds neutral gaps so the detector can re-arm, runs the production classifier over the result, verifies the exact expected order, and writes a technical manifest.

#### `main()`

Parses paths, runs the sequence builder, prints the report, and returns failure when the expected gesture order is not reproduced.

### `tools/run_gesture_control_webots.py`

#### `run(manifest_path, transcripts_path, no_rendering=False)`

Rejects unverified gesture manifests, copies approved event/transcript fixtures into a new evidence directory, launches Webots with replay adapters, optionally records the real robot view, waits safely, and verifies commands, gesture sources, route order, arrivals, final shake interruption, final `STOPPED` state, and staged event order.

#### `main()`

Parses manifest/transcript/render options, calls `run()`, prints the integration verification, and returns a failure code when any proof condition is absent.

### `tools/build_trace_dashboard_demo.py`

#### `build(video, transcripts, output, preview, report_path)`

Processes the consented staged video through the production recognizer, replays timed text commands, applies task-state transitions, maintains Voice/Camera Mode, renders every dashboard frame, writes an intermediate video, encodes H.264 with FFmpeg, saves a preview, and writes a privacy-safe technical report.

#### `main()`

Parses file paths, calls `build()`, and prints the report.

### `tools/run_trace_demo.py`

#### `main()`

Validates the consented clip, transcript fixture, world, and Webots executable; creates an evidence directory; configures the clip as the camera source and JSON as text-only speech input; then launches Webots in real time with the dashboard.

### `tools/build_gesture_control_demo.ps1`

#### `Get-VideoDuration(path)`

Uses FFprobe to measure input duration and fails when duration is unavailable.

#### `Format-AssTime(seconds)`

Converts seconds into ASS subtitle timestamps.

#### Main script action

Selects a passing rendered gesture-control run, verifies route/event order and final safety state, time-aligns dashboard and Webots recordings, creates captions, places them side by side, applies a persistent blur to the subject's face region, encodes the professor-ready H.264 video, and generates a thumbnail/contact sheet/report.

### `tools/build_showcase_video.ps1`

#### `Get-LatestRun(pattern, requiredFile)`

Finds the newest validation run containing required evidence.

#### `Write-Utf8NoBom(path, content)`

Writes FFmpeg subtitle/concat control files using predictable UTF-8.

#### `Convert-ToFilterPath(path)`

Escapes Windows paths for FFmpeg filter syntax.

#### Main script action

Builds an older all-changes showcase from a Webots recording, dashboard video, safety screenshots, captions, title cards, and summary cards. It is a development presentation tool; the final ZIP keeps only the latest blurred gesture-controlled professor video.

### `tools/gesture_control_transcripts.json`

Contains three timed, already-transcribed commands (`start A`, `go to C`, and `go to B`) plus expected A/C arrival times for the gesture-controlled demonstration. It contains no audio.

### `tools/trace_demo_transcripts.json`

Contains timed accepted and low-confidence transcript decisions plus a dashboard reset time for the broader traceability demonstration. It is used to exercise dashboard voice decisions without a microphone.

## 9. Submission packaging

### `tools/build_submission_zip.ps1`

This script creates and audits the self-contained submission ZIP.

#### `Assert-TemporaryPath(path, requiredPrefix)`

Prevents staging or cleanup from targeting an unsafe path outside the approved workspace or without the generated temporary prefix.

#### `Get-RelativePathCompat(basePath, targetPath)`

Creates a safe relative path and rejects files outside their expected source tree.

#### `Copy-PackageFile(source, relativeDestination)`

Checks that a required file exists and copies it into the generated staging tree.

#### `Copy-PackageTree(sourceRoot, relativeDestination)`

Copies a directory recursively while excluding Python caches and bytecode.

#### `Copy-EvidenceRun(runName, destinationName)`

Copies selected technical evidence while excluding intermediate raw movies.

#### `Get-StreamSha256(stream)`

Calculates a SHA-256 hash directly from an archive stream.

#### Main script action

The main body:

1. creates uniquely named, validated staging/QA/archive paths;
2. copies required code, model, world, vendored PROTOs, tests, documentation, selected evidence, and exactly one blurred MP4;
3. excludes the legacy world/controller and raw subject/source videos;
4. creates `SHA256SUMS.txt`;
5. creates the ZIP;
6. checks required entries, exactly one WBT, exactly one MP4, privacy exclusions, and embedded hashes;
7. extracts the archive to QA and reruns the tests from the packaged copy;
8. replaces the previous final ZIP only after every check succeeds;
9. deletes only the validated generated temporary paths.

## 10. Legacy Toyota controller

### `controllers/gesture_vehicle_controller/gesture_vehicle_controller.py`

This is the original Toyota direct-steering experiment and is not used by the final e-puck world.

#### `DebugLogger`

- `__init__()` creates console/file logging suitable for the old controller.
- `debug()`, `info()`, `warning()`, `error()`, and `critical()` forward messages at their corresponding logging levels.

#### `HeadGestureRecognizer`

- `__init__()` opens a camera and configures the older MediaPipe gesture thresholds/history.
- `_calculate_head_rotation(landmarks)` estimates head orientation from landmarks.
- `_classify_from_motion()` converts recent movement into the older gesture labels.
- `get_gesture()` captures a frame, detects the face, classifies the gesture, and displays the old preview.
- `_draw_landmarks(...)` draws landmark/measurement debugging overlays.
- `_display_frame(...)` displays recognition status.
- `get_stats()` returns old recognition counters.
- `release()` closes the camera and display resources.

#### `main()`

Connects the old gestures directly to Toyota steering, throttle, braking, and gear behaviour. This direct vehicle-control design is retained only for comparison; the submitted e-puck uses autonomous waypoint navigation and gesture confirmation instead.

## 11. Test files

The test suite uses Python `unittest`, small fake devices, deterministic clocks, and temporary directories. Tests do not require a real microphone, camera, or Webots GUI unless they explicitly exercise host dashboard rendering.

### `tests/test_input_adapters.py`

Tests bounded Vosk acceptance/rejection, the safer standalone-START threshold, pose smoothing, one-shot tilt behaviour, nod hold behaviour, two-direction shake detection, rejection of a single turn as a shake, and clearing incomplete gesture motion when the face disappears.

The helper `feed()` sends timestamped pose sequences into `GestureStateDetector`.

### `tests/test_device_recovery.py`

The fake classes provide deterministic time, reconnect outcomes, voice events, and gesture events.

The test methods verify:

- same-cycle voice/gesture fusion and priority;
- Camera Mode indication for gestures and shake;
- automatic camera and microphone reconnection;
- camera recalibration after recovery;
- strict preflight cleanup;
- replacement of adapters that become inactive;
- camera frame-failure detection;
- microphone callback-stall detection;
- PCM bytes, peak level, and partial text reaching the Vosk trace;
- explicit enabling of Vosk word-confidence output.

### `tests/test_expanded_navigation.py`

Tests stationary standalone `START`, destination-plus-nod behaviour, shortest/alternative route selection, every directed waypoint pair, measured-position replanning, off-network rejection, pause/continue, mid-route destination replacement, latest-pending replacement, reverse, global stop, bounded expanded vocabulary, and transcription confidence boundaries.

### `tests/test_task_machine.py`

Tests the complete legacy A workflow, invalid-state rejection, shake reset, B/long workflow, voice stop, command normalisation, emergency keys, and required route selection before a legacy start nod.

### `tests/test_navigation.py`

The `Motor`, `Device`, and `Sensor` fakes emulate Webots devices. Tests prove that obstacles and invalid localisation zero both motors and that valid navigation produces forward motion.

### `tests/test_live_dashboard.py`

- `snapshot()` creates representative dashboard telemetry.
- `ClosingCv` emulates a user closing the OpenCV window.
- Tests verify valid-frame and missing-frame rendering, bounded button hitboxes, one-time close-window safety, newest-frame consumption, event display, render cost, and state/mode-specific next-step instructions.

### `tests/test_traceability.py`

Fake voice/gesture classes isolate trace behaviour. Tests prove that Vosk evidence contains decisions but no audio, JSON status contains no pixels, reset sessions append logs, transcript schedules preserve timing, classified gesture manifests replay exact timestamps, and unverified manifests are rejected.

### `tests/test_transcription_workflows.py`

`run_workflow()` passes supplied text through the production normaliser and task machine. Tests cover A/B workflows, case/spacing variations, unbounded and wrong-state rejection, normalised global stop, and Vosk word-confidence boundaries.

### `tests/test_validation_metrics.py`

Checks that technical metrics correctly separate activation, rejected commands, pending commands, confirmation response time, and successful execution.

### `tests/test_world_configuration.py`

Reads the submitted WBT/PROTO files and verifies required robot devices, controller name, overview configuration, waypoint coordinates, supported geometry, local vendored resources, and texture completeness.

## 12. Important environment variables

| Variable | Meaning |
| --- | --- |
| `WEBOTS_EXECUTABLE` | Explicit Webots executable used by live and validation launchers. |
| `VOSK_MODEL_PATH` | Local offline Vosk model directory. |
| `WEBCAM_INDEX` | `auto`, a numeric camera index, or a video-file path. |
| `MICROPHONE_DEVICE` | sounddevice input index or matching name. |
| `INPUT_RETRY_SECONDS` | Independent microphone/camera reconnect delay. |
| `EPUCK_VALIDATION_DIR` | Directory for technical logs and result files. |
| `EPUCK_SCENARIO_FILE` | Deterministic scenario JSON supplied to the controller; removed by the physical live launcher. |
| `EPUCK_TRANSCRIPT_REPLAY` | Timed text-only speech fixture. |
| `EPUCK_GESTURE_REPLAY` | Verified timed gesture-event manifest. |
| `EPUCK_DISABLE_DASHBOARD` | Disables the host OpenCV window for Docker/headless runs. |
| `EPUCK_CAPTURE_OVERVIEW` | Enables Webots overview screenshots for evidence. |
| `EPUCK_RECORD_MOVIE` | Requests a deterministic Webots movie output. |

Additional `EPUCK_*` variables used by validation inject specific faults, select expected terminal conditions, control timeouts, and configure rendering. They are set by the tools rather than by normal live users.

## 13. Files that are data rather than executable code

- `models/vosk-model-small-en-us-0.15/`: trained offline speech-recognition model files.
- `validation_runs/`: generated technical evidence, screenshots, logs, reports, and intermediate validation outputs.
- `demo/`: final presentation media and its documentation.
- `.venv/`: local Python interpreter and installed third-party libraries.
- documentation `.md`, `.docx`, and `.csv` files: project explanation, requirements, change tracking, and submission guidance.

These files support execution or evidence but do not contain the project's control logic.

## 14. Responsibility summary

| Responsibility | Main file |
| --- | --- |
| Webots integration and control loop | `epuck_waypoint_controller.py` |
| Commands, states, graph routes | `model.py` |
| GPS/compass motor navigation | `navigation.py` |
| Vosk, MediaPipe, replay, recovery | `input_adapters.py` |
| Live camera/traceability display | `live_dashboard.py` |
| Runtime events and metrics | `validation.py` |
| Main submitted simulation | `epuck_waypoint_navigation.wbt` |
| Windows live launch | `tools/run_live.py` |
| Client device diagnosis | `tools/check_live_inputs.py` |
| Docker/Webots regression | `tools/run_validation.py` and `run_docker_validation.ps1` |
| Gesture-video verification | `analyze_gesture_video.py`, `build_gesture_control_sequence.py`, and `run_gesture_control_webots.py` |
| Demonstration production | `build_trace_dashboard_demo.py` and `build_gesture_control_demo.ps1` |
| Self-contained submission ZIP | `build_submission_zip.ps1` |
