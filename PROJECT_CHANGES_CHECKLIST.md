# E-puck Project Changes Checklist

## Purpose

This document converts the 24 requirements in `F:\Head gesture thesis\Manikanta_Project_Changes(E-puck Changes).csv` into an implementation and verification checklist for the current Webots e-puck project.

No requirement should be marked complete solely because relevant code exists. Completion requires the implementation, automated tests, a passing Webots run, and visible evidence where applicable.

## Status legend

- `[x]` Implemented and supported by current project evidence.
- `[ ]` Pending only when it depends on unavailable physical hardware or additional human trials.
- **Partial** means useful support exists, but the complete CSV requirement is not satisfied.
- **Scope change** means the request changes the approved bounded pickup/drop-off workflow and should be confirmed before implementation.

## Current alignment summary

| Category | Count | CSV items |
| --- | ---: | --- |
| Implemented | 24 | 1–24 |
| Partially implemented | 0 | — |
| Not implemented | 0 | — |
| Total | 24 | 1–24 |

Implementation alignment is now 100%. Automated verification is complete for the software and Webots behaviors; the physical client webcam and human-spoken accuracy trials remain hardware-dependent checks.

## Decisions required before implementation

- [x] Treat this change list as the approved expanded scope while preserving the pickup/drop-off workflow.
- [x] Use a bounded general point-to-point system alongside the existing task workflow.
- [x] Implement standalone `START`; retain `start A` and `start B` as backward-compatible combined task starts.
- [x] Define `FORWARD`, `REVERSE`, `LEFT`, and `RIGHT` as safe autonomous-route interventions rather than direct wheel control.
- [x] Present clarification through console output and a Webots overlay.
- [x] Calculate shortest and alternative routes for every connected waypoint pair.
- [x] Replan from the measured current position after explicit route/destination/reverse requests; unexpected obstacles still trigger a safe stop.
- [x] Preserve `stop` and head shake as immediate highest-priority safety actions.

> Recommended interpretation: keep the e-puck autonomous and use directional commands to request a route decision rather than directly steering the wheels. Direct manual wheel control would materially change the safety model and thesis evaluation.

---

## Detailed requirement checklist

### 1. Stop automatic movement

**CSV requirement:** The e-puck must remain stationary when the project starts and wait for a user command.

**Current status: Implemented**

- [x] Controller starts stationary in `IDLE` and requires `START` or a backward-compatible destination-bearing task start.
- [x] No navigation route is started at launch.
- [x] Wheel motion begins only after a valid start command, route-selection gesture, and nod confirmation.
- [x] Missing microphone/camera input leaves the robot safely stopped.
- [x] Invalid or low-confidence input does not initiate movement.

**Regression checks**

- [x] Run Webots with no input and confirm the controller remains in `IDLE` with no route or motor command.
- [x] Repeat with unavailable input and absent-face scenarios; all fail closed without initiating movement.
- [x] Record the initial state and zero-motion result in validation evidence.

**Acceptance criterion:** The e-puck remains stationary indefinitely until a valid, confirmed navigation request is accepted.

### 2. Adjust world/e-puck size

**CSV requirement:** Improve robot visibility by reducing the world size or increasing the apparent e-puck size.

**Current status: Implemented**

- [x] Main world is approximately 6 m × 5 m.
- [x] A fixed overhead Webots viewpoint is configured.
- [x] The rendered simulation uses a visible robot locator and enlarged attached e-puck body.
- [x] Add a 0.28 m non-colliding visual body, approximately 3.8× the standard e-puck diameter.
- [x] Preserve the official physical e-puck dimensions, sensors, wheel geometry, collision behavior, and navigation calibration.
- [x] Use the configured overhead camera, locator, and heading-marked robot body to improve visibility without changing physics.
- [x] Verify that S, A, B, C, walls, destination emphasis, and the robot are readable in rendered evidence without floor route lines.

**Acceptance criterion:** A viewer can locate the enlarged, heading-marked e-puck immediately throughout the simulation without altering navigation physics or obscuring the map.

### 3. Modify route highlighting

**CSV requirement:** Routes should look like available paths rather than permanent colour-coded tracks followed rigidly by the robot.

**Current status: Superseded by the approved complete-removal change and implemented**

- [x] Remove saturated tracks and all neutral corridor-guide geometry completely.
- [x] Keep the graph edges and controller waypoints unchanged, so removal is visual only.
- [x] Identify the active route by name in the command/state overlay instead of drawing it on the floor.
- [x] Highlight the active destination and show a non-colliding robot locator.
- [x] Add automated world-structure tests that fail if any `ROUTE_*_GUIDE` or `ROUTE_*_STYLE` node returns.
- [x] Capture rendered navigation, arrival, and safety-stop evidence with no floor route lines.

**Acceptance criterion:** The map communicates route availability, while the active route is clearly distinguishable without looking like a fixed rail.

### 4. Integrate voice and head gesture

**CSV requirement:** Voice and head-gesture recognition must operate in the same main controller/system.

**Current status: Implemented**

- [x] `LocalMultimodalInput` supervises both Vosk and MediaPipe adapters.
- [x] The main task controller receives both command types through one fusion path.
- [x] Voice provides bounded task commands.
- [x] Head tilt selects a route, nod confirms, and shake stops/cancels.
- [x] Device loss stops the robot and clears pending work.
- [x] Missing devices are retried automatically.

**Regression checks**

- [x] Test voice followed by gesture, gesture followed by voice, and same-cycle events.
- [x] Confirm that reconnecting either device clears stale input and requires camera recalibration.

**Acceptance criterion:** Both modalities remain connected to one state machine and cooperate without separate operating modes.

### 5. Add a START command

**CSV requirement:** The robot waits for `START`; after it, voice and gesture controls become active.

**Current status: Implemented**

- [x] The robot already waits for `start A` or `start B` before moving.
- [x] Voice and camera inputs are supervised from launch.
- [x] Implement standalone `START` and retain destination-bearing starts for backward compatibility.
- [x] Add `IDLE` and transition `IDLE → READY` on standalone `START` without movement.
- [x] Keep the recogniser active for `START` while other navigation commands are gated by state.
- [x] Keep head shake and `STOP` globally valid, including in `IDLE`.
- [x] Use `STOPPED` as the explicit stopped state; a later `START` returns to `READY`.
- [x] Update Vosk grammar, normalisation, state tests, README, and validation scenarios.

**Acceptance criterion:** Startup activation has one unambiguous rule, is documented, and cannot accidentally initiate navigation.

### 6. Multiple route combinations

**CSV requirement:** Support S↔A, S↔B, and A↔B, including short and alternative routes.

**Current status: Implemented**

- [x] Static route definitions exist for S↔A, A↔B, A↔C, and B↔C.
- [x] The current workflow can travel S→A, S→A→B, A/B→C, and C→A→S.
- [x] Expose user-requested navigation between all supported waypoints from the current location.
- [x] Calculate S↔B from the connected graph rather than treating it as a hard-coded direct route.
- [x] Calculate a distinct alternative path for connected pairs when requested.
- [x] Represent the route network as a weighted graph derived from canonical route polylines.
- [x] Support reverse traversal using the same graph edges.
- [x] Validate every directed pair in route-planner tests.

**Required route tests**

- [x] S→A shortest and alternative.
- [x] A→S shortest and alternative.
- [x] S→B shortest and alternative.
- [x] B→S shortest and alternative.
- [x] A→B shortest and alternative.
- [x] B→A shortest and alternative.

**Acceptance criterion:** Every approved directed route can be requested from its valid origin and completes collision-free.

### 7. Destination navigation

**CSV requirement:** `Go to A`, `Go to B`, and `Go to S` navigate to the destination using the shortest route from the current location.

**Current status: Implemented**

- [x] Add bounded grammar for `go to A`, `go to B`, `go to C`, and `go to S`.
- [x] Determine the current graph position from GPS with waypoint/corridor tolerance.
- [x] Reject requests safely when the robot cannot be localised to the route graph.
- [x] Compute the shortest valid path using geometric route-segment distances.
- [x] Require a nod to confirm destination and route requests.
- [x] Treat a request for the current location as a successful no-movement action.
- [x] Update destination, selected-route display, status output, and logs.
- [x] Test every supported origin/destination pair and route choice.

**Acceptance criterion:** From any supported location, a valid destination command selects and executes the shortest collision-free graph path.

### 8. Mid-route direction command

**CSV requirement:** During navigation, `Turn Left/Right` should trigger clarification about changing destination, changing route, or continuing.

**Current status: Implemented**

- [x] Define bounded mid-route intervention commands and responses.
- [x] Add a `PAUSED` clarification state.
- [x] Stop the robot before asking for clarification.
- [x] Present available choices in both console output and the Webots overlay.
- [x] Support `go to ...`, `alternative route`, `continue`/`forward`, `reverse`, and `stop`.
- [x] Remain safely paused when no answer is received.
- [x] Keep `STOP` and head shake immediately valid during clarification.
- [x] Reject unrelated responses without movement.
- [x] Log the command, state, selected response, and resulting route.

**Acceptance criterion:** A mid-route direction command pauses safely and cannot change movement until an explicit valid choice is confirmed.

### 9. Recalculate from the current position

**CSV requirement:** Route or destination changes continue from the robot's actual position.

**Current status: Implemented**

- [x] Capture a fresh valid GPS/compass pose before replanning.
- [x] Project the current position onto the nearest safe route segment or graph node.
- [x] Reject replanning if localisation is missing, invalid, or outside the map tolerance.
- [x] Prevent the robot from restarting at the beginning of a predefined route.
- [x] Connect the measured position to the selected graph path through the projected corridor segment.
- [x] Restrict connectors to the validated corridor graph and retain proximity supervision.
- [x] Replace navigator targets while the motors are stopped.
- [x] Test current-position replanning and multiple mid-route interventions in unit and Webots scenarios.

**Acceptance criterion:** After an approved route change, the robot resumes from its measured position without teleporting, reversing unexpectedly, or crossing obstacles.

### 10. STOP command priority

**CSV requirement:** `STOP` has the highest priority and stops movement immediately.

**Current status: Implemented**

- [x] `stop` is globally accepted by the task machine.
- [x] Active-route input polling checks for stop without waiting for waypoint arrival.
- [x] Stop clears pending commands and enters `STOPPED`; standalone `START` returns the controller to `READY`.
- [x] Head shake and the keyboard emergency key provide independent stops.
- [x] Automated safety scenarios cover stop on every route leg.

**Regression checks**

- [x] Verify stop is processed in the first controller cycle in deterministic safety scenarios.
- [x] Confirm stop wins over simultaneous navigation, confirmation, and directional commands.

**Acceptance criterion:** Both wheel velocities are set to zero at the first controller cycle in which an accepted stop is available.

### 11. Robot state management

**CSV requirement:** Use clear states such as IDLE, ACTIVE, NAVIGATING, PAUSED, ARRIVED, and STOPPED.

**Current status: Implemented**

- [x] States include `IDLE`, `READY`, `NAVIGATING`, `PAUSED`, `ARRIVED`, `TO_PICKUP`, `AT_PICKUP`, `TO_DROPOFF`, `AT_DROPOFF`, `TO_RETURN`, and `STOPPED`.
- [x] State-valid command acceptance is enforced.
- [x] Invalid-state commands fail safely.
- [x] State transitions are logged and tested.
- [x] Add `IDLE` and `PAUSED` as approved by the expanded scope.
- [x] Document every state, allowed input, transition, and safety behavior in the README and plan.

**Acceptance criterion:** Every controller state has defined valid commands, gestures, entry conditions, exit conditions, and safe-stop behavior.

### 12. Head-gesture control hardening

**CSV requirement:** Use thresholds, holding time, and cooldown to prevent accidental/repeated commands.

**Current status: Implemented**

- [x] Neutral calibration is required.
- [x] Roll, pitch, and yaw thresholds are defined.
- [x] Tilt and nod require sustained frames.
- [x] Gesture cooldown is applied.
- [x] Neutral re-arming prevents held gestures from repeating.
- [x] Face loss clears incomplete gesture motion.
- [x] Recorded-video and offline gesture tests exist.

**Remaining client verification**

- [ ] Validate neutral calibration, tilt, nod, shake, face loss, and reacquisition on the final physical webcam.
- [ ] Record false-positive and missed-gesture rates under representative lighting.

**Acceptance criterion:** Each intended gesture emits once, held poses do not repeat, and incomplete/low-confidence motion cannot cause navigation.

### 13. Display commands and status

**CSV requirement:** Show recognised commands, gestures, and robot status in the console or UI.

**Current status: Implemented**

- [x] Device readiness and calibration transitions are printed in live mode.
- [x] Commands, gestures, states, routes, progress, and failures are written to technical logs.
- [x] Print or overlay accepted/rejected voice commands.
- [x] Print or overlay detected/ignored gestures.
- [x] Show current state, destination, selected route, and safety reason.
- [x] Avoid displaying partial speech text or face landmarks.
- [x] Throttle scene updates so status is not rewritten every 32 ms.
- [x] Add rendered screenshot evidence for initial, active-navigation, and arrival states.

**Acceptance criterion:** A demonstrator can understand the last input, whether it was accepted, the current state, and what the robot will do next.

### 14. Destination-reached behaviour

**CSV requirement:** Stop at the destination and wait for the next command.

**Current status: Implemented**

- [x] Waypoint navigation stops both motors on route completion.
- [x] The state machine transitions to an arrival state.
- [x] Pickup and drop-off states wait for the next valid voice command and nod.
- [x] Return completion resets to `READY` at S.

**Regression checks**

- [x] Confirm completed navigation scenarios stay stopped in a stable arrival state.
- [x] Confirm the 0.12 m arrival tolerance stops on the safe waypoint area rather than inside collision geometry.

**Acceptance criterion:** Arrival always produces zero wheel velocity and a stable state that waits for valid input.

### 15. Invalid-command handling

**CSV requirement:** Invalid or unclear commands must not cause movement.

**Current status: Implemented**

- [x] Vosk uses a bounded grammar and confidence threshold.
- [x] Text normalisation accepts only documented aliases.
- [x] State-invalid commands are rejected.
- [x] Unbounded and wrong-state transcription tests pass.
- [x] Invalid commands cannot directly set motor speeds.

**Regression checks**

- [x] Extend invalid-state and rejection tests for the expanded commands.
- [x] Reject incomplete or out-of-grammar destination phrases through the bounded normaliser and Vosk grammar.

**Acceptance criterion:** Unrecognised, low-confidence, incomplete, conflicting, and wrong-state commands leave the robot stopped or safely continuing only its previously confirmed route.

### 16. Command-conflict handling

**CSV requirement:** Resolve conflicting voice and head inputs using clear priority rules.

**Current status: Implemented**

- [x] `STOP`, head shake, and keyboard stop override all task actions.
- [x] A second non-stop voice command during pending confirmation causes a safe reset.
- [x] Non-stop voice input during navigation causes a safe stop/reset rather than an uncontrolled route change.
- [x] Conflict and safety scenarios are tested.
- [x] Apply the documented conflict table to pauses, route changes, destination changes, resume, reverse, and emergency stops.

**Required priority order**

1. Emergency stop: voice `STOP`, head shake, keyboard stop, device/localisation/obstacle failure.
2. Confirmed pause or clarification handling.
3. State-valid destination/task command.
4. Route selection.
5. Invalid or ambiguous input: reject without new movement.

**Acceptance criterion:** Every simultaneous-input combination has one deterministic, documented result, with safety actions always winning.

### 17. Map route display

**CSV requirement:** Differentiate available routes, selected route, destination, and current robot position.

**Current status: Implemented with the approved no-floor-route display**

- [x] S/A/B/C markers remain visible; available corridors are intentionally not drawn.
- [x] The physical e-puck position is visible in Webots.
- [x] Recorded demo includes an additional locator.
- [x] Show the selected route name in the state overlay without floor geometry.
- [x] Highlight the active destination marker.
- [x] Add a high-contrast, non-colliding current-position locator for the live view.
- [x] Clear destination highlighting after arrival or cancellation.
- [x] Verify the display states in rendered screenshots.

**Acceptance criterion:** At a glance, a viewer can identify the route by its overlay name, active destination, and robot location while the floor remains free of route lines.

### 18. Shortest and alternative paths

**CSV requirement:** Calculate actual shortest and alternative paths instead of selecting only fixed movement sequences.

**Current status: Implemented**

- [x] Create a graph whose nodes represent S, A, B, C, junctions, and safe route bends.
- [x] Store edge geometry, distance, direction, and route-segment identity.
- [x] Calculate edge weights from route geometry rather than fixed short/long labels.
- [x] Implement deterministic shortest-path selection.
- [x] Implement a distinct alternative-path search.
- [x] Reject cyclic/repeated-node alternatives and use only validated corridor edges.
- [x] Support reversed paths through the same undirected corridor graph.
- [x] Log the selected route, segment identities, and route outcomes.
- [x] Unit-test routing separately from Webots for every directed waypoint pair.

**Acceptance criterion:** The selected shortest path has the minimum computed valid cost, and an alternative is a distinct collision-free path with a documented cost.

### 19. Collision-free routes

**CSV requirement:** Routes must avoid walls, benches, plants, and other obstacles.

**Current status: Implemented**

- [x] Existing routes were designed around the map geometry.
- [x] Bench and plant decoration is non-blocking where intended.
- [x] Complete workflow simulations pass without unapproved collisions.
- [x] A physically blocked-corridor safety scenario exists.
- [x] Derive graph edges only from the previously validated canonical corridor polylines.
- [x] Preserve corridor clearance around the standard-size e-puck and retain a proximity-sensor safety margin.
- [x] Exclude wall-crossing connectors by projecting only to known corridor segments and stopping on obstacles.

**Acceptance criterion:** Every selectable route has sufficient clearance, and blocked/unsafe edges are never executed.

### 20. Obstacle detection

**CSV requirement:** Use e-puck sensors to detect obstacles and stop safely.

**Current status: Implemented**

- [x] `ps0`–`ps7` proximity sensors are enabled.
- [x] Readings are checked on every navigation step.
- [x] Threshold crossing stops both motors.
- [x] Obstacle stops reset the task and are logged.
- [x] Sensor-stop and blocked-corridor scenarios are tested.

**Regression checks**

- [x] Preserve robot scale and speed so the validated threshold remains applicable.
- [x] Test threshold handling, blocked-corridor behavior, and the sensor index responsible for each stop.

**Acceptance criterion:** An obstacle within the configured danger threshold stops the robot before collision and records which sensor triggered.

### 21. Define expanded commands

**CSV requirement:** Define `START`, `STOP`, `FORWARD`, `REVERSE`, `LEFT`, `RIGHT`, `GO TO A`, `GO TO B`, and `GO TO S`.

**Current status: Implemented**

- [x] Existing bounded commands are documented: `start A`, `start B`, `pickup`, `drop off`, `return`, and `stop`.
- [x] Retain the existing bounded pickup/drop-off commands alongside general navigation.
- [x] Define the exact phrases and aliases for every command.
- [x] Define valid states for every command.
- [x] Require nod confirmation for non-emergency route/task requests.
- [x] Define directional words as safe route interventions, never direct wheel control.
- [x] Keep movement bounded by the confirmed autonomous waypoint route and safety supervisor.
- [x] Update Vosk grammar, text normaliser, state machine, README, UI, and tests together.
- [x] Ensure ambiguous or out-of-grammar words cannot bypass confirmation or safety rules.

**Acceptance criterion:** Every supported word has one documented meaning in each valid state, and unsupported interpretations are rejected.

### 22. Manual intervention during autonomous navigation

**CSV requirement:** Accept voice/head commands while destination navigation is active.

**Current status: Implemented**

- [x] Voice `STOP` and head shake remain active during navigation.
- [x] Device, face, localisation, and obstacle supervision remain active during navigation.
- [x] Other in-motion commands currently cause a safe stop/reset.
- [x] Allow only the documented bounded interventions while navigating.
- [x] Pause before processing route or destination changes.
- [x] Require a valid clarification response and nod confirmation before a changed route resumes.
- [x] Centralise motor control in the navigator so commands cannot write conflicting speeds.
- [x] Test continue/forward, reverse, alternative route, and destination replacement in deterministic Webots scenarios.

**Acceptance criterion:** Approved intervention commands are handled predictably while all other inputs preserve or increase safety.

### 23. Simultaneous voice and gesture availability

**CSV requirement:** Keep voice and head recognition active together instead of switching modes.

**Current status: Implemented**

- [x] Both adapters are created and supervised concurrently.
- [x] The same polling path can receive voice or gesture events.
- [x] Gesture remains available while voice confirmation is pending.
- [x] Voice stop and head shake remain available during active navigation.
- [x] One-device failure stops movement and triggers reconnection attempts.
- [x] Test voice and gesture availability in the same polling cycle and verify deterministic priority behavior.

**Acceptance criterion:** Neither modality must be manually selected, and simultaneous events resolve according to the documented priority table.

### 24. Command and event logging

**CSV requirement:** Record recognition accuracy, response time, successful execution, and failed commands.

**Current status: Implemented**

- [x] Commands and acceptance/rejection are logged.
- [x] Gestures and outcomes are logged.
- [x] State, route, waypoint, safety-stop, and failure events are logged.
- [x] Confirmation response time is calculated.
- [x] Route success/failure, path length, duration, sensor peak, and final position are stored.
- [x] Workflow, safety, transcription, gesture-video, and device-readiness evidence exists.
- [x] No raw audio, video frames, or face landmarks are retained by the live pipeline.
- [x] Extend summary metrics with accepted/rejected command totals, acceptance rate, gesture totals, pauses, resumes, destination changes, and successful execution.
- [ ] For real recognition accuracy, create a labelled test script with expected commands/gestures and compare expected versus detected output.

**Acceptance criterion:** Each test run produces enough non-identifying evidence to reconstruct the accepted input, system decision, timing, route, outcome, and failure reason.

### 25. Live camera and traceability dashboard

**Current status: Implemented and locally verified**

- [x] Open an automatic local dashboard during live Windows-host simulation.
- [x] Display the newest external-camera frame with `LIVE - NOT RECORDED`, a face box, and head-pose indicators.
- [x] Display calibration, gesture evidence, final voice transcript/confidence/decision, state, pending confirmation, route, GPS, waypoint distance, proximity peak, device recovery, safety, and recent events.
- [x] Display persistent Voice/Camera control mode, microphone callback/level/partial-transcript evidence, and state-aware next-step instructions for activation, destination entry, route selection, nod confirmation, neutral re-arming, route override, device recovery, and restart.
- [x] Keep standalone `START` stationary; prioritize state-valid in-motion destination voice commands, allow the newest destination to replace a pending one, and retain nod confirmation plus global stop/shake priority.
- [x] Limit display refresh to 8 FPS and retain at most one transient frame.
- [x] Make dashboard `STOP` immediate and global.
- [x] Make `RESET AT S` stop first, reset Webots, return to S, and begin a new appended log session.
- [x] Treat dashboard closure or dashboard failure as a safety-stop condition.
- [x] Disable the GUI for deterministic Docker/headless scenarios.
- [x] Replay the consented 70.06-second gesture clip through the production classifier and dashboard; detect 2 left tilts, 2 right tilts, 4 nods, and 3 shakes.
- [x] Replay six timed transcript decisions without opening a microphone, including a low-confidence rejection.
- [x] Exclude the raw clip from the final ZIP; include only the derived consented demonstration and technical evidence.
- [x] Present the control dashboard and cropped Webots robot/world view side by side in the professor video, with both panes labelled and the e-puck/arena kept visible.
- [x] Replace the illustrative split-screen with a separate synchronized end-to-end video in which production-classified clip events actually drive the Webots controller.
- [x] Verify the exact clip-derived sequence `TILT_LEFT, NOD, TILT_LEFT, NOD, TILT_RIGHT, NOD, SHAKE`, three route starts, both required arrivals before their next commands, and final `STOPPED` in controller evidence.
- [x] Remove Webots runtime asset-download dependence by packaging the official R2025a PROTOs/textures used by the submitted world.

**Acceptance criterion:** Live users can see exactly what the camera, voice recognizer, task controller, navigator, devices, and safety supervisor believe without the display becoming a second navigation interface.

---

## Final automated evidence

- [x] Python compilation completed with no errors.
- [x] Offline unit/integration tests: **66/66 passed**.
- [x] Dashboard/trace replay: **11 gesture events and 6 transcript decisions verified**, with no microphone audio and no packaged raw clip.
- [x] Post-dashboard Docker baseline: **1/1 passed**; summary `validation_runs/suite_summaries/20260824_002905_892164_baseline_short.json`. Docker passed 52 portable tests and explicitly skipped the four host-only OpenCV rendering tests.
- [x] Production-classified staged gesture-video replay: headless **1/1** and rendered **1/1** passed; rendered evidence is `validation_runs/20260824_024532_896682_gesture_video_control`, with completed routes `S_A_SHORT` and `GRAPH_A_C_SHORTEST`, interrupted route `GRAPH_C_B_ALTERNATIVE`, verified arrival-before-next-command ordering, and final state `STOPPED`.
- [x] Post-guidance in-motion voice destination override: **1/1 passed**; summary `validation_runs/suite_summaries/20260824_082011_814930_midroute_destination_change.json`. Evidence records stationary activation, delayed route start until destination plus nod, microphone override from A to B, and successful arrival at B.
- [x] Explicit Voice/Camera-mode and live Vosk-confidence Webots regression: **1/1 passed**; summary `validation_runs/suite_summaries/20260824_084958_555229_midroute_destination_change.json`. All 61 portable tests pass before and after Webots, and events prove Voice→Camera on nod, Camera→Voice on the moving destination override, Voice→Camera on confirmation, and arrival at B.
- [x] Production microphone callback probe: **more than 20 callbacks / over 160,000 bytes reached Vosk**; per-word confidence output is explicitly enabled and covered by a unit test. The report marks the development host's selected virtual input as silent, so the final client's actual microphone must still be selected and spoken into.
- [x] Self-contained-resource Docker baseline: **1/1 passed**; summary `validation_runs/suite_summaries/20260824_021650_245838_baseline_short.json`, with 56 portable tests passing and the host-only OpenCV module skipped.
- [x] Docker baseline workflow: **1/1 passed**; summary `validation_runs/suite_summaries/20260820_224341_129620_baseline_short.json`.
- [x] Already-transcribed voice/control suite: **5/5 passed**; summary `validation_runs/suite_summaries/20260820_225829_866703_transcriptions.json`.
- [x] Expanded destination, route-choice, and intervention suite: **12/12 passed**; summary `validation_runs/suite_summaries/20260820_231254_095929_navigation_changes.json`.
- [x] Safety and injected-fault suite: **16/16 passed**; summary `validation_runs/suite_summaries/20260820_231550_507068_safety.json`.
- [x] Final rendered S→A alternative run: **1/1 passed**; summary `validation_runs/suite_summaries/20260820_230853_271745_goto_a_alternative.json`.
- [x] Visually inspect post-removal rendered navigation and safety evidence: no floor route lines remain, the active route is named in the overlay, the destination is emphasized, and the robot locator is visible.
- [x] Final no-floor-route showcase: **1/1 passed**; summary `validation_runs/suite_summaries/20260821_075133_873491_demo_showcase.json`. The refreshed captioned presentation is 125.96 seconds, 1280×720 H.264, and includes a labelled dashboard/robot split-screen plus all three safety-stop scenes.
- [x] Enlarged-robot rendered checks: S→A **1/1**, full movie showcase **1/1**, voice stop **1/1**, head shake **1/1**, and blocked corridor **1/1** passed; all presentation scenes were refreshed with the 0.28 m visual body.
- [x] Audit the final rendered logs: no actionable controller/world errors; only expected Docker root and Mesa software-rendering warnings.
- [x] Confirm no validation container remains after the Docker suites.
- [ ] Run live gesture trials on the final client webcam and a labelled human-spoken command dataset on the final client microphone.
- [ ] If required for statistical reporting, run 10 repetitions of every newly exposed directed shortest/alternative pair; existing workflow reliability evidence already contains 40/40 complete task trials.

---

## Completed implementation order

### Phase 0 — approve the revised scope

- [x] Resolve all decisions listed under “Decisions required before implementation.”
- [x] Update `plan.md` with the approved command and navigation model.
- [x] Define acceptance criteria before final verification.

### Phase 1 — presentation improvements with low architectural risk

- [x] Complete item 2: robot visibility.
- [x] Complete item 3: remove all floor route geometry and retain route identity in the overlay.
- [x] Complete item 13: command/state display.
- [x] Complete item 17: destination and current-position display.
- [x] Run all 66 offline tests and Docker regression scenarios.

### Phase 2 — graph and routing foundation

- [x] Complete item 6: approved route combinations.
- [x] Complete item 18: shortest and alternative path calculation.
- [x] Revalidate item 19: collision-free graph edges.
- [x] Add route-planner unit tests and deterministic Webots scenarios.

### Phase 3 — expanded commands and mid-route behavior

- [x] Complete item 5: activation behavior.
- [x] Complete item 7: destination commands.
- [x] Complete item 8: mid-route clarification.
- [x] Complete item 9: replanning from current position.
- [x] Complete item 21: expanded command definitions.
- [x] Complete item 22: safe manual intervention.
- [x] Revalidate items 10, 11, 15, 16, and 23 after the state-machine changes.

### Phase 4 — full verification and evidence

- [x] Run all offline tests with zero failures.
- [ ] Run at least 10 Docker Webots trials for every directed route and alternative.
- [x] Test every new command across its valid states and representative invalid states.
- [x] Test `STOP`, shake, keyboard stop, obstacle stop, device loss, face loss, localisation loss, and controller failure across the deterministic safety suite.
- [x] Test simultaneous/conflicting voice and gesture events.
- [x] Test route change, alternative selection, reverse, and resume from measured mid-route positions.
- [x] Verify route-name, destination, locator, and status display visually with no floor lines.
- [ ] Validate microphone and webcam behavior on the final client computer.
- [x] Record result totals, path lengths, response times, failure counts, and screenshots.
- [x] Update README commands and demonstration instructions.
- [x] Mark implementation complete only where code and automated evidence support the requirement.

## Implemented file responsibilities

| File | Expected responsibility |
| --- | --- |
| `controllers/epuck_waypoint_controller/model.py` | Expanded grammar, states, command rules, graph model, and route selection. |
| `controllers/epuck_waypoint_controller/navigation.py` | Current-position replanning, route replacement, pause/resume, and navigation safety. |
| `controllers/epuck_waypoint_controller/input_adapters.py` | Expanded Vosk grammar and simultaneous-event handling. |
| `controllers/epuck_waypoint_controller/live_dashboard.py` | Automatic camera/decision/robot/safety dashboard and bounded STOP/RESET controls. |
| `controllers/epuck_waypoint_controller/epuck_waypoint_controller.py` | Command fusion, clarification workflow, display updates, and route replanning. |
| `controllers/epuck_waypoint_controller/validation.py` | Metrics for new commands, replanning, conflicts, and outcomes. |
| `worlds/epuck_waypoint_navigation.wbt` | Route-guide-free map, named destination display nodes, waypoint markers, and visibility aids. |
| `tests/` | Unit and integration coverage for every new state, command, graph route, conflict, and safe-stop path. |
| `tools/run_validation.py` | New deterministic route, replan, intervention, and display scenarios. |
| `README.md` | Final command vocabulary, gestures, state behavior, and client demonstration steps. |
| `plan.md` | Approved revised scope, implementation checklist, and final evidence status. |

## Final completion gate

### Client portability audit (10 September 2026)

- [x] Add root AGENTS.md with machine-local setup and acceptance instructions for Codex.
- [x] Add setup_client.py and verify installation into a fresh virtual environment.
- [x] Strip inherited replay/fault settings from normal live launches.
- [x] Resolve the controller's model, log directory, and Windows interpreter from this project.
- [x] Correct pending-route instructions and clear the confirmation latch on command conflict.
- [x] Pass 69 Windows offline tests; consult CLIENT_READINESS_AUDIT.md for Docker/package evidence.
- [ ] Perform spoken-command, webcam calibration, hot-plug, and emergency-stop acceptance on the actual client laptop.

### Project completion gates

- [x] All 25 requirements have an evidence-backed implementation status.
- [x] No requirement is marked implemented based only on documentation.
- [x] All approved commands and gestures are documented consistently in code, README, plan, and test scenarios.
- [x] The e-puck never moves automatically or from invalid/ambiguous input.
- [x] Emergency stopping remains immediate after all new features are added.
- [x] Dynamic routes are calculated correctly over the validated collision-free corridor network.
- [x] The simulator visibly communicates current position, destination, selected route name, input, and state without drawing floor routes.
- [ ] Docker Webots validation, offline tests, physical microphone tests, and physical webcam tests all pass.
- [x] Submission evidence contains no raw participant audio, video, frames, or face landmarks; only the separately consented derived professor demo contains selected camera imagery.
