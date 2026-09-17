# Multimodal e-puck waypoint-navigation prototype

## Project goal

Develop and evaluate a simulation-only Webots e-puck prototype that combines local voice recognition with head gestures for safe, hands-free waypoint navigation. The project evaluates technical reliability through repeatable simulator runs; usability studies with participants are future work.

The world design follows the point-to-point reference map supplied during project design. Recreate its functional layout, waypoint topology, walls, and obstacle placement with original Webots-native geometry and labels. Do not copy the reference artwork or assets.

## Implementation checklist and current status

Status key: `[x]` complete and verified, `[~]` implemented but still needs the stated verification, `[ ]` pending.

### Build

- [x] Keep the Toyota world and direct-steering controller untouched in the development workspace only; exclude them from the final submission because the e-puck world is the sole required runnable world.
- [x] Create the separate `epuck_waypoint_navigation.wbt` e-puck world with 32 ms stepping, differential-drive motors, `ps0`-`ps7`, GPS, compass, coloured S/A/B/C markers, enclosure, interior walls, and non-blocking map decoration.
- [x] Encode the short/long S<->A corridors and A<->C, A<->B, and B<->C waypoint routes.
- [x] Implement the `READY`, pickup, drop-off, return, and `READY`-on-completion task-state workflow.
- [x] Implement bounded command normalisation and invalid-state rejection.
- [x] Add standalone `START`, `GO TO A/B/C/S`, `FORWARD`, `REVERSE`, `LEFT`, `RIGHT`, `CONTINUE`, and `ALTERNATIVE ROUTE` commands while preserving the assessed pickup/drop-off commands.
- [x] Replace fixed route-choice logic for general navigation with a weighted graph that calculates shortest and distinct alternative paths in both directions.
- [x] Replan destination, alternative, and reverse requests from the GPS-measured current position by projecting it onto the nearest safe corridor segment.
- [x] Add `IDLE`, `NAVIGATING`, `PAUSED`, `ARRIVED`, and `STOPPED` states plus bounded mid-route clarification and deterministic command-priority rules.
- [x] Remove all visible route-guide geometry while retaining the internal route graph; show only the active destination, a non-colliding robot locator, a 0.28 m attached e-puck visual body, and the Webots command/state/route-name overlay.
- [x] Implement deterministic scenario input, waypoint navigation, proximity-stop logic, keyboard stop handling, runtime events, and JSON validation results.
- [x] Implement local-only Vosk and MediaPipe adapters, including Vosk grammar/confidence filtering and MediaPipe neutral calibration, stateful one-shot tilt/nod/shake classification, cooldown, neutral re-arming, face-loss motion reset, and no media-file retention.
- [x] Create an isolated `.venv`, pin compatible recognition dependencies in `requirements.txt`, and install the offline `vosk-model-small-en-us-0.15` model under `models/`.
- [x] Add `tools/check_live_inputs.py` and `tools/run_live.py` for non-recording device preflight and real-time Webots launch through the isolated environment.
- [x] Harden client device startup: require actual microphone callbacks and stable camera frames, scan camera indices/backends, list and explicitly select Windows microphones, auto-discover Webots, support explicit microphone/camera selection, retry devices independently, remove the live idle timeout, log readiness transitions, fail closed on disconnect, and recalibrate after camera recovery.
- [x] Add the official Webots R2025a Docker/Xvfb validation environment (`compose.webots.yaml`) and the reusable `tools/run_docker_validation.ps1` entry point.
- [x] Open and close the available microphone stream with the installed Vosk model and bounded grammar.
- [~] Exercise MediaPipe with a real webcam; the software stack imports correctly, but Windows reports no camera device on this machine.
- [x] Replay the 70.06-second `tilt_gesture.mp4` recording through the production MediaPipe path using recorded camera timestamps; verify calibration, both tilt directions, nod, shake, face-loss handling, route selection, nod confirmation, and shake emergency-stop effects.
- [x] Add an automatic 8 FPS Windows-host traceability dashboard with transient webcam preview, face box, head pose, gesture/calibration evidence, Vosk decision evidence, state/route/GPS/sensor status, device recovery, and recent events.
- [x] Add dashboard `STOP`, `RESET AT S`, and close-window safety behavior; append live events across reset sessions without storing camera pixels, audio, or landmarks.
- [x] Add persistent `MODE: VOICE` / `MODE: CAMERA` control, a coloured mode badge, microphone callback/level/partial-transcript evidence, and a state-aware `NEXT STEP` instruction panel covering activation, destination selection, tilt/nod confirmation, neutral re-arming, device recovery, route override, and restart after a stop.
- [x] Enforce stationary standalone `START` behavior, require a destination before any movement gesture, switch to Voice Mode for every valid voice input, give in-motion voice destination replacement priority, and switch back to Camera Mode on the next valid gesture while retaining nod confirmation and higher-priority global stop/shake safety.
- [x] Explicitly enable Vosk per-word results so live confidence filtering receives the data it requires; retain the strict 0.65 threshold for movement-affecting commands and use a safe 0.50 threshold only for stationary standalone `START`.
- [x] Add a text-only transcript replay launcher and consented derived dashboard-video builder; keep the raw `tilt_gesture.mp4` source outside the package.

### Automated verification completed

- [x] Compile all controller and validation Python modules.
- [x] Pass all 66 offline tests covering legacy workflows, the physical-live activation-only startup gate, expanded Vosk commands, live word-confidence configuration, PCM callback/partial-transcript delivery, all directed graph pairs, shortest/alternative selection, current-position replanning, repeated voice destination replacement, same-cycle multimodal priority, event metrics, device recovery, gesture behavior, dashboard rendering/actions/instructions/privacy, transcript replay, safety paths, and world configuration.
- [x] Complete the final 40/40 headless Webots full-workflow reliability suite on the corrected map: ten each for baseline short, baseline long, expanded-B short, and expanded-B long.
- [x] Verify every required directed route within those repeated workflows: S->A (short and long), A->S return, A<->C, A<->B, and B<->C.
- [x] Verify all four complete workflows in rendered mode using the corrected overhead Viewpoint; preserve initial, waypoint-arrival, final-overview, and e-puck camera images.
- [x] Pass all 16 deterministic safety/failure scenarios: voice stop, shake, keyboard, proximity, physical blocked corridor, localisation loss, invalid/conflicting input, absent face, controller failure, and stop/cancel on S->A, A->B, A->C, B->C, C->A, and A->S.
- [x] Confirm all final workflow runs end in `READY` and the maximum final S-position error is 0.0863 m. Docker log audit reports zero actionable error lines; only the expected root-container and Mesa software-rendering warnings remain.
- [x] Record per-run commands, gestures, routes, state transitions, GPS positions, actual path length, simulation/wall-clock time, confirmation response time, sensor peak, failures, screenshots, and pass/fail outcome.
- [x] Save aggregate suite summaries under `validation_runs/suite_summaries/`.
- [x] Verify launched Webots validation processes are terminated after each run and no Webots process remains after the suite.
- [x] Complete a post-change Docker regression of all four canonical workflows (4/4 passed) and all 16 independent safety/fault scenarios (16/16 passed).
- [x] Pass 5/5 no-audio transcription scenarios through the production command normaliser and Webots task controller: complete A/short and B/long journeys, unbounded-text rejection, wrong-state rejection, and whitespace-normalised global stop.
- [x] Complete a rendered Docker/Xvfb baseline workflow after giving software rendering a bounded 360-second host allowance; verify six screenshots, the configured overhead view, final `READY` state, and return to S.
- [x] Record and visually verify the H.264 all-changes showcase (`demo/head_gesture_epuck_all_changes_showcase.mp4`): show the live traceability dashboard beside a cropped full-height Webots robot/world view, then cover consented gesture replay, text-only voice decisions, activation, routing/replanning, voice stop, head shake, obstacle stop, and complete removal of floor route lines. Runtime capture remains disabled and the raw participant clip is excluded.
- [x] Remove actionable world-load warnings by declaring the background PROTOs, assigning unique Solid names, and replacing unsupported `Text` geometry with original box-stroke S/A/B/C labels while retaining full waypoint descriptions in Solid names.
- [x] Rerun the final Docker baseline workflow and normalized transcription-stop scenario after device hardening; both pass with all 34 preflight and postflight tests.
- [x] Pass the revised legacy Docker baseline after the controller expansion, with all 46 then 48 preflight/postflight tests.
- [x] Pass all 12 Docker navigation-change scenarios: A/B shortest and alternative routes, A->S, A->B, B->A, mid-route destination replacement, clarification plus alternative, clarification plus continue, reverse, and forward/continue.
- [x] Pass the complete 16/16 Docker safety regression after adding in-motion commands.
- [x] Pass rendered Docker showcase and safety runs after route-guide removal; visually verify that no floor route lines remain while destination emphasis, current-position locator, route name/state overlay, navigation, and all three safety-stop modes remain correct.
- [x] Disable the e-puck camera only for headless deterministic scenarios, eliminating the reproducible long-run simulator stall while retaining camera capture for live and rendered evidence.
- [x] Defer rendered screenshots by one frame after destination-display changes so captured evidence matches the controller state.
- [x] Complete the final post-fix Docker evidence: baseline 1/1 (`20260820_224341_129620_baseline_short.json`), transcriptions 5/5 (`20260820_225829_866703_transcriptions.json`), expanded navigation 12/12 (`20260820_231254_095929_navigation_changes.json`), safety 16/16 (`20260820_231550_507068_safety.json`), and rendered alternative navigation 1/1 (`20260820_230853_271745_goto_a_alternative.json`), each with 48/48 preflight and postflight tests.
- [x] Complete the final route-guide-free Docker regression: demo showcase 1/1 (`20260821_075133_873491_demo_showcase.json`) with 48/48 preflight and postflight tests; visually inspect full-size title, navigation, voice-stop, head-shake, obstacle-stop, and summary frames from the finished video.
- [x] Add and verify the 0.28 m attached e-puck visual body: rendered S→A 1/1 (`20260821_081648_987706_goto_a_shortest.json`), refreshed rendered/movie showcase 1/1 (`20260821_082452_048195_demo_showcase.json`), voice stop 1/1, head shake 1/1, and blocked corridor 1/1, each with 48/48 preflight and postflight tests.
- [x] Pass the post-dashboard Docker baseline 1/1 (`20260824_002905_892164_baseline_short.json`) after allocating 1 GB container shared memory and disabling Qt MIT-SHM; 52 portable tests pass in Docker and four host-GUI rendering tests are explicitly skipped there.
- [x] Cut the consented gesture clip into a staged sequence and verify the production classifier emits exactly `TILT_LEFT, NOD, TILT_LEFT, NOD, TILT_RIGHT, NOD, SHAKE` without boundary-induced false gestures.
- [x] Replay those exact classified timestamps through the normal Docker Webots controller with text-only `start A`, `go to C`, and `go to B` fixtures; verify the robot finishes `S_A_SHORT`, then finishes `GRAPH_A_C_SHORTEST`, then starts `GRAPH_C_B_ALTERNATIVE` before the video-derived shake stops it.
- [x] Vendor the official R2025a e-puck/appearance resources required by the world after Webots' internal HTTP asset loader blocked rendered startup; confirm network-independent headless startup and a passing rendered recording.
- [x] Build and visually verify the synchronized 33.16-second dashboard/robot professor video (`demo/head_gesture_video_controlled_robot.mp4`), showing two completed commands and interruption of the third.
- [x] Pass the final self-contained-resource Docker baseline 1/1 (`20260824_021650_245838_baseline_short.json`) with all 56 portable Docker tests passing and the host-only OpenCV dashboard module explicitly skipped.
- [x] Pass the post-guidance Docker mid-route destination-change regression 1/1 (`20260824_082011_814930_midroute_destination_change.json`): standalone `START` logs `movement_started=false`, A begins only after destination plus nod, `GO TO B` pauses and replaces the active A route, and nod starts the B route from the measured position.
- [x] Pass the final explicit-mode/Vosk-confidence Docker regression 1/1 (`20260824_084958_555229_midroute_destination_change.json`): event evidence records stationary `START`, Voice-to-Camera on the first nod, Camera-to-Voice on the mid-route `GO TO B` override, Voice-to-Camera on the confirming nod, and arrival at B; all 61 portable tests pass before and after Webots.
- [x] Pass the post-startup-lock Docker regression 1/1 (`20260910_081439_582222_midroute_destination_change.json`): all 62 portable Docker tests pass before and after Webots; the controller starts in `IDLE`, `START` records `movement_started=false` and `waiting_for_destination=true`, and movement begins only after a separate destination plus nod.
- [x] Verify the Windows microphone callback path with the production adapter (`client_device_preflight_20260824.json`): more than 20 callbacks and over 160,000 bytes reached Vosk; the report explicitly marks the selected virtual device as silent, so spoken-command accuracy remains a client-hardware check.

### Verification still pending

- [ ] Connect a physical webcam and run neutral calibration plus live tilt, nod, shake, absent-face, and low-confidence tests.
- [x] Repeat Webots validation after the gesture change in the official Docker image; Docker replaces the unstable host GUI path and passes workflows, transcription integration, safety/fault coverage, and rendered-view verification.
- [ ] Run a human-spoken command dataset through the available microphone to calculate real voice-command accuracy; model loading and microphone streaming are verified, but recognition accuracy requires spoken samples.
- [ ] Label expected gesture intervals in the recorded clip or complete webcam trials before calculating accuracy; recorded-camera coverage and deterministic classifier tests are complete.
- [ ] Press the physical keyboard emergency key during a live Webots session; the keyboard branch is covered by unit and injected Webots tests.
- [ ] Convert proximity sensor peaks to minimum clearance only if a calibrated sensor-to-distance curve is added; current results correctly report raw maximum proximity peaks.
- [ ] Conduct any participant usability evaluation as future work; it is outside the technical simulation scope.

### Readiness decision

- [x] Ready for technical Webots simulation evaluation.
- [~] Live multimodal hardware evaluation is software-ready but blocked by the absence of a webcam and still requires human voice/gesture trials.

## World and routes

- Create an approximately 6 m x 5 m enclosed Webots world with a standard differential-drive e-puck, a 32 ms time step, wheel motors, `ps0`-`ps7` proximity sensors, GPS, and compass.
- Place the waypoints as shown in the reference map:
  - S: start, lower-left;
  - A: pickup, upper-left;
  - B: pickup, lower-right;
  - C: drop-off, upper-right.
- Use coloured waypoint markers without visible floor routes. Add interior walls and non-blocking bench/plant decoration that reproduces the map's navigation constraints. Keep route topology solely in the controller's graph and waypoint data.
- Implement this directed route network:
  - S <-> A: a short green route and a longer orange route;
  - A <-> C;
  - A <-> B;
  - B <-> C.
- The baseline assessed journey is S->A->C->A->S. The B waypoint and its connecting routes provide expanded navigation coverage through S->A->B->C->A->S.

## Interaction model

- Use local Vosk speech recognition with a bounded grammar containing `start`, `go to A/B/C/S`, `forward`, `reverse`, `left`, `right`, `continue`, `alternative route`, `stop`, and the legacy pickup/drop-off commands.
- Begin in `IDLE`; standalone `START` activates the controls without movement. The legacy `start A` and `start B` commands combine activation with the assessed pickup workflow for backward compatibility.
- For general navigation, `GO TO ...` defaults to the graph's shortest route. A left tilt explicitly selects shortest, a right tilt selects a distinct alternative, and a nod confirms the pending route.
- During navigation, `LEFT` or `RIGHT` stops and enters `PAUSED`, where the bounded replies are `CONTINUE`, `ALTERNATIVE ROUTE`, `GO TO A/B/C/S`, `REVERSE`, or `STOP`.
- `FORWARD` means continue the confirmed autonomous route; it never bypasses obstacle supervision by directly writing wheel speeds. `REVERSE` replans to the active route origin from the measured current position.
- Voice and gesture adapters remain active together. Same-cycle events follow the fixed priority: emergency stop, clarification/resume, state-valid destination/task command, route selection, then rejection.
- The task state machine includes `IDLE`, `READY`, `NAVIGATING`, `PAUSED`, `ARRIVED`, `TO_PICKUP`, `AT_PICKUP`, `TO_DROPOFF`, `AT_DROPOFF`, `TO_RETURN`, and `STOPPED`.
- Invalid, unrecognised, low-confidence, ambiguous, and wrong-state commands cannot initiate new movement.

## Safety, data, and controller structure

- `stop`, a head shake, and an independent keyboard emergency-stop override are globally valid. Each immediately clears pending input, stops both wheel motors, and enters `STOPPED`; standalone `START` reactivates the controller.
- Stop the e-puck when gesture confidence is low, a face is absent, speech recognition fails, localisation is lost, an obstacle is detected, a route is blocked, or the controller errors.
- Structure the controller into gesture recognition, Vosk recognition, command fusion/task state, waypoint navigation, safety supervision, and technical-result logging modules.
- Process microphone and webcam data transiently and locally for recognition. Do not store raw audio, video, frames, face landmarks, or other identifiable media.
- Display the newest transient webcam frame in the live dashboard without runtime recording. The separately generated professor demo may contain only the user-approved consented clip; do not package its raw source.
- Store only non-identifying technical results: run ID, command and gesture categories, selected route, state transitions, completion status, response and execution times, path length, safety overrides, error category, and minimum obstacle clearance.

## Testing and evidence-based validation

- Unit-test command handling, gesture calibration/classification, route-selection gestures, state-valid command acceptance, invalid-state rejection, keyboard stop, and every safe-stop path.
- Run at least 10 deterministic headless trials for every directed route: both S->A routes, A->S return, A<->C, A<->B, and B<->C.
- Run complete baseline and expanded scenarios. Inspect at least one successful run of each complete scenario in visible Webots mode without changing the world Viewpoint or initial camera configuration.
- Test stop/cancel during every route leg, keyboard emergency stop, blocked corridors, obstacle-triggered stops, lost localisation, speech-recognition failure, absent/low-confidence face detection, and conflicting commands.
- Measure voice-command accuracy, gesture-recognition accuracy, confirmation response time, route/task completion rate, pickup/drop-off/return completion, path length, execution time, failed-command frequency, obstacle stops, minimum clearance, and reliability across repeated runs.

### Validation procedure

1. Before each run, inspect the target world, controller entry points and names, required DEF nodes, PROTO compatibility, and runtime configuration. Run the complete offline test suite and record exact pass/fail totals.
2. Create `validation_runs/<run-id>/` with:
   - `scenario.json`: command sequence, selected S<->A route, expected state transitions, and expected final position;
   - `controller_events.ndjson`: timestamped runtime events;
   - `result.json`: expected and observed outcomes, durations, metrics, and final pass/fail result;
   - `screenshots/`: initial state, waypoint arrivals, safety stops, and final state;
   - `webots.stdout.log` and `webots.stderr.log`.
3. Pass absolute paths for `scenario.json` and the run directory through run-specific environment variables such as `EPUCK_SCENARIO_FILE` and `EPUCK_VALIDATION_DIR`.
4. Launch Webots R2025a through `tools/run_docker_validation.ps1`, which uses the official image, an ephemeral container, Xvfb, and software rendering. Use headless trials for repeatability and `-Visible` for screenshot verification; rendered runs have a separate bounded host allowance because Mesa rendering is slower.
5. Record the Webots process ID and stop only that process after a completed run, timeout, or failure.
6. Require `controller_started` before assessing any route. Record `command_recognised`, `gesture_recognised`, `command_confirmed`, `route_started`, `waypoint_reached`, `safety_stop`, `route_failed`, and `execution_completed` events when applicable.
7. For every command and route step, record the input, expected and observed state transitions, GPS-observed e-puck position, selected route, route length, minimum sensor-observed clearance, duration, and verification result.
8. Validate navigation from the controller's declared waypoint and sensor inputs, not hidden Supervisor lookups of robot or waypoint state. Supervisor instrumentation may observe outcomes but must not influence controller decisions.
9. Fail closed: stop the remaining actions and record the failure when the controller does not start, an expected event is missing, an observed result differs from expectation, an unapproved safety stop occurs, or the run times out.
10. Inspect Webots output for missing Python packages, controller naming/entry-point errors, missing DEF nodes, PROTO loading errors, rendering errors, and crashes. Diagnose the real cause before rerunning the complete offline and Webots validation sequence.
11. Declare success only when all required commands and state transitions have evidence, the final waypoint is reached within the configured tolerance, the final controller state is `READY`, no unapproved safety stop occurred, and visible inspection confirms the logged behaviour.
12. Rerun the offline test suite after each successful validation run. Preserve validation artefacts and verify that no cache or project-state files were created outside `validation_runs/`.

## Assumptions

Client deployment uses `py -3.12 tools/setup_client.py` after extracting the ZIP.
The root `AGENTS.md` gives Codex machine-local setup, device selection, and live
acceptance steps. `CLIENT_READINESS_AUDIT.md` separates verified software checks
from physical microphone/camera checks that remain required on the client laptop.

- Webots R2025a in the official `cyberbotics/webots:R2025a-ubuntu22.04` Docker image and Python are the supported automated validation environment.
- The isolated `.venv` and local Vosk model are the supported live-input runtime.
- The controller uses original Webots-native assets and the supplied map only as a functional design reference.
- This file tracks the implemented project and its evidence-backed completion status.
