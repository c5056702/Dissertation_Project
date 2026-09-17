# Client setup notes

Date: 2026-09-15

## Environment

- Project: `C:\Users\manik\Downloads\35056702_Dissertation_Final_Project~`
- Windows 11, build 26200; extracted project is writable.
- Python: `C:\Users\manik\AppData\Local\Programs\Python\Python312\python.exe`, version 3.12.10, 64-bit.
- Created a new machine-local `.venv`; no existing environment was copied or replaced.
- Webots: `C:\Program Files\Webots\msys64\mingw64\bin\webots.exe`.
- Webots R2025a confirmed by the installed application registry and `resources/version.txt`.
- Docker CLI and the standard Docker Desktop installation were not found. Docker simulator validation is not run.

## Verification

- `py -3.12 tools/setup_client.py` installed dependencies, verified all 245 packaged checksums, passed dependency compatibility/import checks, and passed all 72 unit tests.
- The first PowerShell logging pipeline reported exit 1 after pip wrote an update notice to stderr, although setup completed successfully. A direct `py -3.12 tools/setup_client.py --check-only` rerun exited 0 and confirmed every check, including all 72 tests. No dependency changes were needed.
- Installation output: `client_setup_install.log`; machine-readable summary: `client_setup.json`.
- Installed recognition versions: MediaPipe 0.10.14, JAX/JAXlib 0.4.33, NumPy 1.26.4, OpenCV contrib 4.6.0.66, sounddevice 0.5.6, Vosk 0.3.45.
- Selected microphone index 1, the default physical Realtek Microphone Array (MME). Bluetooth and loopback devices were not selected.
- `check_live_inputs.py --camera auto --microphone 1 --wait-seconds 15` exited 0. Camera 0 returned valid 640x480 frames through DSHOW. Microphone stream at 16000 Hz returned 8 callbacks / 64000 bytes and peak 729. This proves a stream and signal, not intelligible speech.
- Initial probe showed no face, no completed neutral calibration, and no partial/final transcription. The subsequent live controller detected a face and completed neutral calibration (see below).
- Probe report: `client_devices.json`; no media saved.
- Launched through `run_live.py --microphone 1 --require-ready` with the explicit installed Webots path. Logs: `client_live_stdout.log` and `client_live_stderr.log`.
- Live evidence: `20260915_202917_live/controller_events.ndjson`. Controller started in IDLE, using local Vosk microphone and local MediaPipe camera; dashboard started with recording disabled. Face presence and completed neutral calibration are recorded in the live status events. No speech command or route-start event was recorded at the startup check.
- Process inspection confirms Webots launched this project's `.venv\Scripts\python.exe` controller; its underlying interpreter is the installed Python 3.12.10.
- Only one Webots session was launched. Left running for client acceptance. No project code, dependencies, map, gestures, or safety rules were changed.

## Launch command

From the project root, after closing any existing project Webots session:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"
```

## Physical acceptance still required

- Real speech with changing microphone level and partial/final transcription.
- Visual client confirmation of the dashboard (face presence and neutral calibration are already confirmed by live controller telemetry).
- Startup IDLE / Voice Mode / stationary at S; START enters READY without movement.
- GO TO A waits stationary for a fresh nod; shortest and alternative routes.
- During travel GO TO B stops and awaits a fresh nod; correct mode transitions.
- Voice STOP, head shake, dashboard STOP, and RESET AT S.
- Incompatible PICKUP during pending confirmation safely stops and allows fresh START.
- Head shake during pending confirmation; dashboard next-step instructions.

No microphone audio, webcam frames, or face landmarks are saved during setup.

## Travel-time head gesture correction - 2026-09-16

### Diagnosis

- Client reported left/right head commands being treated as SHAKE during travel, while voice commands worked.
- The moving controller handled voice commands and SHAKE but omitted route-selection tilts. The task model only selected routes when a command was already pending.
- The live shake detector used yaw span alone. An in-memory one-sided yaw sequence from 0 to 0.12 emitted SHAKE without reaching the opposite side of neutral. This reproduced a classifier defect, independent of the client's exact movement.
- The latest pre-fix run, `20260916_181027_live/controller_events.ndjson`, contains accepted speech, calibrated face detection, pending-route TILT_LEFT/TILT_RIGHT selection, and SHAKE stops during navigation. Individual reported false shakes cannot be reconstructed because raw media and face poses were not recorded. The run also contains face-absent stops; that safety behavior remains in place.

### Changes

- During travel, TILT_LEFT/TILT_RIGHT now stops the navigator and selects a shortest/alternative route to the same destination. A later nod is required to replan from the measured position and resume. Route selection also works after a voice-direction pause.
- Legacy pickup/drop-off/return task phases survive gesture-only route changes. Spoken destination replacements retain their existing behavior.
- SHAKE now requires yaw excursions to both sides of calibrated neutral, in addition to the existing span/window/cooldown conditions. One-sided turns and returns do not qualify. Stationary neutral frames no longer appear as a SHAKE candidate.
- Gesture meanings remain ear-to-shoulder roll tilts for routes, nod for confirmation, and side-to-side yaw for stop. Voice priority, activation, stop safeguards, map, and dependency pins remain unchanged.
- Updated dashboard instructions and user documentation. Deterministic scenario input now accepts a separate confirmation or stop after a tilt.

### Verification and package integrity

- Used this project's `.venv\Scripts\python.exe` (Python 3.12.10). Installed Webots remains `C:\Program Files\Webots\msys64\mingw64\bin\webots.exe`, R2025a.
- Before editing, `verify_manifest` passed all 245 original packaged checksums.
- Full command: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`. All 91 tests passed; output is `20260916_gesture_fix_tests.log`.
- Regression coverage includes single-sided yaw versus actual two-sided shakes, detector cooldown/re-arming and face loss, both moving tilts, measured-position replanning, zero motor targets until a later nod, no-nod behavior, voice priority, STOP/SHAKE cancellation, conflicting PICKUP followed by fresh START, legacy task continuation, and separate scenario confirmation/stop.
- Controller integration tests use fake Webots devices and do not certify real recognition or simulated motion. Docker CLI/Desktop is not available; no Docker simulator regression was run.
- The original archive checksum manifest is preserved as `20260916_gesture_fix_original_SHA256SUMS.txt`. `SHA256SUMS.txt` is updated only for the 11 deliberately edited source/test/documentation files; hash changes are recorded in `20260916_gesture_fix_manifest_changes.json`. This local patch does not regenerate or replace historical submission evidence.

### Physical acceptance pending

- Restart the live session using the launch command above. Latest prior live input used Realtek microphone index 1 and camera 0 (DSHOW); current physical readiness was not re-probed for this code fix.
- Face the camera, complete neutral calibration, say START, then GO TO A, and nod to travel.
- While moving, tilt the ear toward the right shoulder. Verify the dashboard reports an alternative pending route and stationary motors; return neutral, wait for re-arming, then nod. Repeat with a left tilt for the shortest route. These select routes rather than directly turning the wheels.
- Confirm a one-sided face turn does not report SHAKE while the face remains visible; then test a deliberate left-and-right shake and voice STOP separately. Both safety stops must still require a fresh START.
- Retest a spoken destination override during travel, a pending-command conflict such as PICKUP, and head shake while waiting for confirmation. Remaining original acceptance checks above still apply.
- No live session was launched and no camera/audio/landmark data was recorded during this correction.

## Repeated tilts and missing GO TO A - 2026-09-16

### Diagnosis and correction

- The client reports that GO TO A produces no visible transcript and repeated tilts appear to work only for B. The latest existing live run (`20260916_191415_live`) actually accepted right/right/left tilts for B, then stopped on face loss at 19:16:04 BST. Later neither B nor C received tilt events. Earlier live runs accepted A, and the 18:10 run accepted a right tilt for S. These logs do not establish a destination-specific controller bug or the exact acoustic reason A was missed.
- Reproduced a camera geometry defect with synthetic landmarks: pure sideways roll also changed the computed yaw. At 640x480, a 0.55-radian pure roll generated enough false yaw to fail the tilt gate in both directions. The corrected calculation accounts for image aspect ratio and uses coordinates aligned with the eyes. Upright pitch/yaw scales, recognition thresholds, neutral calibration, and gesture meanings are preserved; roll now measures the actual image angle instead of an aspect-distorted angle.
- The detector reports which axes remain outside neutral. The dashboard tells the client to straighten the head, level the chin, face the camera, or keep neutral through cooldown before another gesture. This applies during travel and pending confirmation for all destinations. Face-loss stops still require START.
- Added bounded `go to alpha` as another spoken phrase for A, using the same 0.65 confidence requirement and fresh nod confirmation. This is a clearer alternative to try, not proof of repaired acoustic recognition of the short letter A.
- Reproduced a diagnostic defect where partial speech or silence overwrote a rejected final speech decision. The dashboard now retains the last nonempty final result and its rejection reason. Technical logs include final command transcripts and word confidences, deduplicated by recogniser/reconnect ID. Audio, frames, and landmarks remain transient; no client media was recorded.

### Verification and environment

- Full test suite: **115 tests passed** using `.venv\Scripts\python.exe -m unittest discover -s tests -v`; saved to `20260916_repeat_tilt_voice_tests.log`. Coverage includes synthetic camera geometry at multiple image aspect ratios, repeated tilts/nods after offset neutral calibration, real yaw/shake preservation, pending/travelling route selection for A/B/C/S, confidence/activation/nod boundaries, stable speech feedback, and log deduplication without media.
- `pip check` found no broken requirements. Python 3.12.10 is 64-bit; OpenCV, MediaPipe, NumPy, sounddevice, and Vosk imports passed. Webots `resources/version.txt` remains R2025a at the existing installation path.
- The Python launcher initially reported no installations inside the sandbox; outside-sandbox inspection found Python 3.12 and 3.14. Only the existing project Python 3.12 environment was used. Process inspection found no Webots or Python session running at that check. No duplicate or new live session was launched.
- Microphone enumeration still lists index 1 as the default physical Realtek Microphone Array. Camera and audible speech were not re-probed during this correction. The last historical live status reports ready devices, visible face, and calibrated gestures; this does not certify current physical recognition.
- The bundled Vosk model loaded the revised grammar, and all grammar words (including alpha) exist in its vocabulary. No client audio was used for that check.
- Docker CLI/Desktop remains unavailable; Docker simulator regression was not run. Controller integration tests use fake Webots devices; geometry tests use synthetic landmarks.
- Preserve the prior checksum manifest as `20260916_repeat_tilt_voice_original_SHA256SUMS.txt`; record local hash changes in `20260916_repeat_tilt_voice_manifest_changes.json`. Refresh only reviewed source/docs/tests and add the three new test files. `tests/test_input_adapters.py` already differed from the manifest before this correction; its existing repeated-gesture tests were reviewed and passed, and its content was preserved. Historical submission evidence is unchanged.

### Client retest still required

From this project folder, start the updated code with:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"
```

- Face the camera in a comfortable neutral posture through calibration; say START, then GO TO A. If A produces no transcript, try GO TO ALPHA and check that A becomes pending before making a fresh gesture.
- Tilt right, return to neutral until the detector is armed, then nod. Repeat while moving, and test B/C/S in separate requests. Follow the posture guidance if re-arming stalls.
- If face loss causes STOPPED, restore face visibility, say START, and give the destination again. START while a destination is already pending remains an incompatible-command safety stop.
- Retest genuine shake and voice STOP separately, pending-command conflict recovery, and fresh nod after a spoken destination replacement. These physical acceptance checks remain open; automated tests do not certify the client's recognition.

## Armed detector misses moving tilts - 2026-09-16 follow-up

- Client confirmed `Detector: armed` while left/right tilts produced no gesture during travel. The updated `20260916_194420_live` run accepted one right tilt before A travel, then no in-motion tilt events. Roughly 73 seconds of A travel had no face-loss event, so face loss does not explain that interval. Updated speech logging and accepted GO TO ALPHA prove the revised controller was loaded. The original A attempt was heard as `go to a a` and correctly rejected as outside the bounded grammar; ALPHA was accepted at confidence 1.0.
- Source review and synthetic input checks did not reproduce a movement-specific controller failure: the camera detector receives no robot state, and a held tilt at approximately 7.5 camera polls/second emits on the fourth valid frame. The client's exact angle/hold/pitch/yaw gate is unknown because previous logs intentionally did not retain poses. No threshold or safety rule was relaxed.
- Added categorical diagnostics for missing pose, insufficient roll, pitch/yaw blockers, tilt hold, neutral re-arming, and cooldown. The dashboard explains the blocked tilt while armed. The controller records only these categories plus controller/pending state at most twice per second, refreshing every five seconds. Brief intermediate categories can be missed by throttling; accepted gesture event logging remains unthrottled. No raw poses, landmarks, camera frames, or audio are saved.
- Full suite: **123 tests passed**; `20260916_moving_tilt_diagnostics_tests.log`. New checks cover held left/right tilts at the observed moving sample rate, unchanged threshold boundaries, armed-but-blocked tilts, actionable dashboard instructions, and categorical logging/rate limits during travel.
- Current enumeration still identifies physical Realtek microphone index 1. Process inspection found no Webots/Python session before the diagnostic relaunch. Existing environment remains project Python 3.12.10 and Webots R2025a; dependencies, map, activation, fresh nod, neutral hold, and safety semantics are unchanged. Docker validation remains unavailable.
- Prior manifest is preserved as `20260916_moving_tilt_original_SHA256SUMS.txt`; reviewed source/test/documentation hash changes are recorded in `20260916_moving_tilt_manifest_changes.json`. Physical moving-tilt acceptance remains open until a new live trial demonstrates recognition and a stationary pending route before the next nod.

### Observed live diagnostic trial

- Launched one session through `run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"` after checking for existing instances. Launcher PID 25696; output/error logs are `20260916_moving_tilt_live_stdout.log` and `20260916_moving_tilt_live_stderr.log`. Evidence: `20260916_195659_live/controller_events.ndjson`, session `0e663a114c50`.
- Preflight returned ready Realtek microphone at 16000 Hz and camera 0 / DSHOW / 640x480. Initial low signal/empty transcript did not verify speech. The subsequent live controller calibrated with a visible face and accepted START, GO TO ALPHA, and STOP. Nods started real simulated A travel. Thus speech and camera recognition were observed, beyond mere stream readiness.
- During A travel at 19:58:19 BST, armed left-tilt attempts crossed the roll threshold but failed yaw and then pitch gates. At 19:58:27, an armed right tilt became a valid candidate, then exceeded the yaw gate before completing its hold. The same pitch/yaw blockers also occurred in stationary pending confirmation. These observations identify the classifier gate, not proof that its pose estimate exactly matches the client's physical motion.
- A right tilt was accepted at 19:58:49 while A was pending. No `gesture_route_override_pending` was recorded during this trial, so moving-tilt physical acceptance still failed. No recognition thresholds or safety rules were changed to force a pass.
- Voice STOP was observed during travel. A START while a destination was already pending caused the expected conflict stop; a later START reactivated. The final logged actions were dashboard STOP then RESET at about 20:01:06 BST. No fresh head-shake acceptance was observed.
- Client guidance: use a small ear-to-shoulder tilt (around 15 degrees is sufficient for the configured 0.20-radian threshold), keep the nose toward the webcam and chin at the calibrated starting height, and hold until accepted. The client was asked to distinguish roll tilting from turning the nose left/right. Further recognition or calibration changes need that physical clarification; do not represent the in-motion issue as fixed yet.

## Consistent alternative routes and destination feedback - 2026-09-16

- Reproduced a pending-choice reset: RIGHT followed by a repeat of the same GO TO destination changed alternative back to shortest. Same pending requests now preserve the explicit choice and any legacy task continuation. Different destinations still default to shortest; a later fresh nod remains required.
- Reproduced false alternatives from intermediate positions: the temporary source connected to both ends of an intact edge, allowing a short detour back across the same position before following shortest. Current-position insertion now splits that edge or reuses its endpoint, with one projection connector for an off-corridor position. This changes planning correctness, not map geometry. Distinct alternatives can still share an initial corridor before diverging.
- An unavailable alternative or alternative request at an already-reached destination now reports an error and stays stationary instead of silently using shortest. Legacy long-route metadata now correctly reports an alternative.
- Every recognised tilt reports destination, choice, and outcome in a `route_selection` event and terminal status, including repeated identical selections and explicit voice-priority ignores. Confirmed route starts name the actual destination and route type. The live launcher forwards controller stdout/stderr to its launch terminal.
- The dashboard has a persistent `Selected route` row, destination-specific next-step instructions, explicit `Previous route` labels during confirmation, and accurate new pending destination instead of the old active destination. Old next-waypoint/distance values are hidden while pending. Frequent posture diagnostics no longer bury route-selection events; the last tilt remains visible.
- **136 unit/integration tests passed** with this project's Python 3.12.10. New regressions first reproduced 52 failing subcases before the fixes; coverage now checks all destinations, every graph-edge midpoint, repeated pending destinations, real alternative paths, unavailable alternatives remaining stopped, legacy metadata, repeated terminal output, pending/active dashboard snapshots, and voice priority. A synthetic dashboard preview was rendered and inspected at `20260916_route_selection_dashboard_preview.png`; it contains no client camera image.
- Test summary: `20260916_route_choice_test_summary.txt`. Prior checksum manifest is preserved as `20260916_route_choice_original_SHA256SUMS.txt`; reviewed changes are recorded in `20260916_route_choice_manifest_changes.json`. Historical evidence remains unchanged.
- No live session was launched for this code/display correction. Last physical evidence remains the preceding trial with Realtek microphone 1 and camera 0 / DSHOW. Its camera tilt recognition problem remains open; passing route-selection tests does not establish that the camera reliably accepts moving tilts. Docker simulator validation remains unavailable.
- Restart using `.\.venv\Scripts\python.exe tools\run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"`. Verify START, destination, RIGHT, same destination repeated, then a fresh NOD keeps ALTERNATIVE. Test LEFT/RIGHT and destination labels for A/B/C/S, including a moving destination replacement. Retest STOP/shake and physical tilt recognition separately.

## Console/dashboard current-status consistency - 2026-09-16

- The client screenshot shows both outputs following `GRAPH_S_A_ALTERNATIVE`, but a pinned dashboard `Last tilt` still says `awaiting NOD` after route start. Its re-arm instruction also lacks the context that the robot is already travelling. This is stale/confusing feedback, not evidence of different selected routes.
- Added a shared current-route formatter for console `[route]` transitions, the Webots status label, and the dashboard `Route status` row/current-event heading. After nod confirmation the current message becomes `TO A: ALTERNATIVE - navigating`; pending destinations, pauses, arrival, and STOP/IDLE are represented separately. Legacy arrival labels now identify the completed path as `Last route`.
- Removed the pinned historical nod instruction. Tilt events are timestamped factual selections. The event panel renders the current supplied snapshot, including direct renders; it no longer reads the previous cached snapshot. Moving re-arm guidance explicitly says `Travelling to A. For next gesture...`, with STOP advice visible within two lines. Recognition thresholds, safety rules, route planning, and device configuration are unchanged.
- Full suite: **139 tests passed** using `.venv\Scripts\python.exe -m unittest discover -s tests -q`. Controller integration compares actual printed `[route]` messages with dashboard snapshots for A/B/C/S across right selection, confirmation, moving left/right changes, a different spoken destination, STOP, and START. Dashboard tests reproduce the screenshot, exercise arrival/stop states and stale snapshots, and inspect the rendered strings so next-step guidance cannot silently clip STOP advice.
- Visually inspected `20260916_console_dashboard_status_preview.png`, generated from synthetic state with no client camera image. No live session was restarted or physical device test performed for this correction. The supplied screenshot shows ready input devices and a calibrated face in that session; current hardware readiness and reliable in-motion physical tilts remain to be retested after restart. Use the same launch command above.
- Preserve the prior manifest as `20260916_console_dashboard_original_SHA256SUMS.txt`; record reviewed file changes in `20260916_console_dashboard_manifest_changes.json`. Test summary: `20260916_console_dashboard_test_summary.txt`. Historical evidence and raw client media are unchanged; no client media was recorded.

## Interrupted live startup - 2026-09-17

- The supplied terminal output ends in `KeyboardInterrupt` while MediaPipe imports Matplotlib style files, and again in the waiting launcher. This establishes an interrupt (usually Ctrl+C), not a missing or corrupt dependency. The original wait duration and source of the interrupt are unknown. A direct MediaPipe import completed in 3.05 seconds using the existing local environment.
- Existing Python remains 64-bit 3.12.10 at `C:\Users\manik\AppData\Local\Programs\Python\Python312\python.exe`; the project uses its own `.venv\Scripts\python.exe`. The sandbox's `py -0p` reports no installations, while host inspection lists 3.12 and 3.14. No interpreter or package was replaced. MediaPipe is 0.10.14 and Matplotlib is 3.11.2. Webots `C:\Program Files\Webots\msys64\mingw64\bin\webots.exe` reports R2025a in `resources/version.txt`.
- Before editing, `tools/setup_client.py --check-only` verified all 252 packaged checksums, passed `pip check` and recognition/GUI imports, and passed the previous 139 tests. The revised suite has 142 tests, including constructor cleanup and preflight cancellation cases. Final setup verification output is saved in `20260917_startup_software_check.log`.
- Added flushed preflight messages for Vosk/microphone and MediaPipe/camera loading. Help and troubleshooting now explain that `--wait-seconds` is a retry window after initialization, not a total startup timeout. Ctrl+C produces a short cancellation message. Cancelled preflight cannot launch Webots, even without `--require-ready`; both handled Python cancellation and native Windows Ctrl+C exit statuses are recognized. If initialization is interrupted after the microphone opens, acquired adapters are closed before the exception propagates. Recognition, routes, activation and safety behavior are unchanged.
- The first device probe inside the execution sandbox could not open physical devices (`20260917_startup_devices.json`); this was not treated as proof of a Windows privacy or hardware failure. The same non-recording host probe passed (`20260917_startup_devices_host.json`): Realtek microphone 1 delivered 44 callbacks / 352000 bytes at 16000 Hz, peak 136; camera 0 / MSMF delivered valid 640x480 frames. No intelligible speech, visible face or neutral calibration was established by that probe.
- Confirmed no Webots session was running, then started one session through the updated `run_live.py --microphone 1 --require-ready` with the explicit installed executable. Its preflight completed initialization in 9.6 seconds, received 34 audio callbacks / 272000 bytes (peak 953), and received camera frames. Logs: `20260917_startup_live_stdout.log`, `20260917_startup_live_stderr.log`; launcher PID record: `20260917_startup_live_launcher.pid`.
- Live evidence: `20260917_003407_live/controller_events.ndjson`. The live controller and dashboard started successfully, recording disabled, in IDLE with ready camera/microphone. Process inspection confirms the controller uses this project's `.venv`. The latest observed status has no face and incomplete calibration; no START or navigation acceptance was established. Left this one session running for client testing. No audio, images or landmarks were saved.
- Physical acceptance remains: face the camera for neutral calibration, observe changing microphone levels and partial/final transcripts while speaking, verify START stays stationary, GO TO A waits for a fresh nod, shortest/alternative routes and moving destination changes, voice STOP/head shake/dashboard STOP/RESET, and pending-command conflict recovery. Existing moving-tilt acceptance remains open. Docker regression was not run for this startup fix.
- Preserved the verified pre-edit manifest as `20260917_startup_original_SHA256SUMS.txt`. Only the reviewed six source/test/documentation files and these notes have updated hashes; the exact changes are in `20260917_startup_manifest_changes.json`. No historical evidence was regenerated.
- For a future restart after closing this live session: `.\.venv\Scripts\python.exe tools\run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"`.
