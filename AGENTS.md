# Client setup instructions for Codex

## Purpose and scope

This folder is a Windows Webots R2025a e-puck simulation controlled by local Vosk speech recognition and MediaPipe head gestures. When the user asks to set up or run it, perform the following setup and verification. Use this extracted folder as the project root; discover it from this file, not from a development-machine drive letter. Read README.md, instructions.md, and CODE_EXPLANATION.md as needed.

## Establish the client environment

1. Confirm Windows and writable extraction outside the ZIP. Keep all project subfolders together. Do not reuse or copy another computer's .venv.
2. Inspect available Python installations (`py -0p`). Use 64-bit Python 3.12. Do not install these requirements into a global interpreter or substitute Python 3.13/3.14. If missing, obtain Python 3.12 from its official distributor within the user's setup authorization.
3. Find Webots R2025a using `tools/run_live.py` discovery or the installed application path. If missing, use the official Cyberbotics distribution within the user's setup authorization. Do not assume F: exists. Set WEBOTS_EXECUTABLE in the launch process or pass --webots with the full existing executable path.
4. From this folder run `py -3.12 tools/setup_client.py`. It verifies packaged SHA-256 checksums, creates .venv if needed, installs requirements, checks dependency compatibility/imports, and runs tests. Internet is needed for the first dependency installation; the Vosk model and Webots assets are bundled. An existing incompatible .venv should be preserved/renamed before creating a replacement; do not delete unrelated data.
5. If setup fails, inspect the actual output, fix the cause, and rerun the failing check. Do not change pinned recognition dependencies merely to suppress an error. Record resolved paths, versions, failures, and remaining hardware checks in validation_runs/client_setup_notes.md.

## Physical inputs and live launch

1. Run `.\.venv\Scripts\python.exe tools\run_live.py --list-microphones`. Select the client's real mic by returned index/name; Steam virtual mic, loopback, and disconnected Bluetooth inputs are not proof of usable speech. Do not reuse the developer's device index.
2. Run `.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --microphone INDEX --wait-seconds 15 --output validation_runs\client_devices.json`.
3. Callbacks/bytes prove an audio stream exists, not that speech is audible. Ask the user to speak while observing a changing signal level and partial/final transcription in the live dashboard. Face presence and completed neutral calibration require the user to face the actual camera. Never declare physical input verified from Docker fixtures or a silent virtual microphone.
4. If Windows denies camera/microphone access, explain the permission needed and let the user enable desktop-app access. Do not bypass privacy settings. Close only task-owned capture sessions; another program may hold the webcam.
5. Launch `.\.venv\Scripts\python.exe tools\run_live.py --microphone INDEX --require-ready` (add `--webots "actual path"` if needed). For device hot-plug troubleshooting omit --require-ready; the robot stays stationary and retries. Do not launch duplicate Webots/controller instances.
6. The live launcher strips inherited EPUCK_* replay/fault settings. Never use run_trace_demo.py or run_validation.py as the normal client live entry point. The raw demonstration clip is intentionally not included.

## Acceptance check with the client

- On startup verify IDLE, Voice Mode, and no movement at S. Say START: verify READY and still no movement. In physical live IDLE/STOPPED, START A/B is reduced to activation only.
- Say GO TO A: verify pending confirmation and stationary motors. Nod to start the shortest route, or tilt right, return neutral, then nod for the alternative.
- While travelling, say GO TO B: verify a stop/pending destination and Voice Mode. Nod to confirm the new route and return to Camera Mode.
- Keep your head neutral while saying the destination. Wait for the pending-destination prompt, then make a fresh nod. A nod detected in the same input sample as speech is intentionally discarded; it must not bypass the stop/confirmation stage.
- Say STOP and test a head shake separately. Both must stop; a new START is needed. Test dashboard STOP and RESET AT S when safe to restart this simulation.
- Verify the dashboard tells the correct next step, including the selected alternative route. Keep a record of which checks were actually performed and which still need the user/hardware.
- While a destination awaits a nod, issue an incompatible command (for example PICKUP); verify a safe stop and that a fresh START is accepted. Also test a head shake during pending confirmation. These live-controller branches require client acceptance in addition to automated model/scenario tests.

## Automated verification

Run `.\.venv\Scripts\python.exe -m unittest discover -s tests` after setup. Docker is optional for live use and is the supported deterministic simulator validation environment. When Docker Desktop is available, run `powershell -ExecutionPolicy Bypass -File tools\run_docker_validation.ps1 -Scenario midroute_destination_change`, then workflows, transcriptions, navigation_changes, and safety when a full regression is requested. Download the official cyberbotics/webots:R2025a-ubuntu22.04 image if absent. Read the generated summary and result.json; don't infer success just because a container exited.

## Constraints and troubleshooting

- This is a simulation with kinematic e-puck configuration; do not represent it as real-robot dynamics or hardware certification.
- Do not change the map, gestures, safety rules, activation sequence, or dependencies to make a demo appear to pass. Diagnose first and keep requested fixes minimal.
- Runtime microphone audio, webcam frames, and face landmarks stay transient. Do not record the client or package raw media. The included professor video has a blurred face.
- Webots processes must use this computer's .venv. The controller bootstrap selects it on Windows; check the Webots console if Python/recognition imports fail. Launch through run_live.py so microphone/camera/model settings are explicit.
- Camera scans/driver calls may take time; a device reporting 'opened' without valid frames is not ready. Slow/hung OS drivers require client troubleshooting; do not claim software can guarantee every device.
- The shipped tools/build_submission_zip.ps1 is a development evidence packager and needs original development documents/runs. It is not required for setup and cannot rebuild missing source evidence from a client ZIP. Do not run it during client installation.
- Historical evidence paths may refer to the development computer or /project Docker mount. Use current local paths for execution.
- Finish by telling the user the launch command, actual software/device readiness, and any checks still waiting for their physical input. Do not say 'everything works' without that evidence.
