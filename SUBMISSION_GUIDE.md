# Submission guide

## Project

This package contains the complete multimodal e-puck waypoint-navigation prototype. It includes the Webots world and controllers, offline Vosk speech model, MediaPipe gesture pipeline, deterministic validation tools and tests, selected result evidence, academic documents, and a professor-ready demonstration video.

Webots, Docker Desktop, Python, webcam drivers, and microphone drivers are platform software and are not bundled in the ZIP. The supplied project files and offline speech model do not require a cloud speech or LLM service. The official Webots R2025a e-puck and appearance resources used by the world are stored under `protos/vendor`, so Webots does not need to download them when opening the submitted world.

## Accepted interaction

The bounded voice commands are `start`, `start A`, `start B`, `go to A`, `go to B`, `go to C`, `go to S`, `pickup` (or `pick up`), `drop off`, `return`, `forward`, `reverse`, `left`, `right`, `continue`, `alternative route`, and `stop`. Standalone `start` activates the controller without moving; `start A` and `start B` retain the assessed pickup workflow. For general point-to-point navigation, say `go to ...`; tilt left for the shortest route or right for an alternative, then nod to confirm. While moving, `left` or `right` pauses and asks for a bounded choice; `continue` or `forward` resumes, `alternative route` replans, `reverse` returns toward the route origin, and `go to ...` changes destination after confirmation. These directional commands never directly steer the motors. Saying `stop` or shaking the head stops immediately from any state.

## Quick automated verification

From this package directory, with Docker Desktop running:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_docker_validation.ps1 -Scenario baseline_short
```

The wrapper uses the official `cyberbotics/webots:R2025a-ubuntu22.04` image. Run the larger deterministic suites with:

```powershell
.\tools\run_docker_validation.ps1 -Scenario workflows
.\tools\run_docker_validation.ps1 -Scenario transcriptions
.\tools\run_docker_validation.ps1 -Scenario safety
.\tools\run_docker_validation.ps1 -Scenario navigation_changes
```

The supplied historical evidence records 40/40 workflow trials, 16/16 safety scenarios, 5/5 already-transcribed voice scenarios, and 12/12 expanded navigation scenarios passing. The client-readiness audit passes 69 Windows offline tests and a fresh dependency installation; see CLIENT_READINESS_AUDIT.md for the latest complete Docker regression and remaining physical-device acceptance checks. Headless validation disables the simulated camera and host dashboard; live mode opens the traceability dashboard automatically.

The Webots world contains no coloured or neutral floor route lines. Navigation
still uses the same GPS/compass waypoint graph and proximity-sensor safety
logic. The active route is named in the on-screen state overlay, while the
destination marker and robot locator remain visible. The primary presentation
copy is `demo/head_gesture_video_controlled_robot.mp4`; it places the production
gesture dashboard and the actual matching Webots run side by side, with the
subject's face persistently blurred. It is the only MP4 in the submission.

## Local Python setup and tests

For guided setup on the client's Windows laptop, ask Codex to read `AGENTS.md`.
The repeatable setup command is `py -3.12 tools/setup_client.py`; it installs
dependencies in a new local .venv and verifies imports, package integrity, and
tests. Use `--check-only` to audit an existing environment without installing.

Python 3.12 is recommended. Create a machine-local environment after extracting the ZIP:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The `.venv` directory is intentionally excluded because it is large and tied to the source machine. Python requirements are version-constrained in `requirements.txt` (some use ranges), and the offline Vosk model is included under `models/`.

## Live microphone and camera

Install Webots R2025a on the Windows host, then check the devices without retaining audio or video:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --wait-seconds 15
```

Start live Webots input with:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py
```

The live launcher fails safely, retries unavailable devices, and stops the robot if an active device disconnects. For a presentation, verify the actual client webcam and microphone before beginning. The Docker tests validate control behavior deterministically but do not pass physical Windows camera or microphone devices into the container.

The automatic host dashboard shows the transient webcam feed, calibration,
gesture and voice decisions, robot/route progress, device health, safety, and
recent events. Its `STOP` button is immediate; `RESET AT S` resets Webots to the
initial position. Closing the dashboard stops the robot. No live media is
recorded.

To demonstrate the dashboard without microphone audio, run
`.\.venv\Scripts\python.exe tools\run_trace_demo.py`. This uses the consented
gesture clip and already-transcribed fixtures; the raw clip is excluded from
the ZIP, while the derived presentation video is included.

## Package contents

- `worlds/epuck_waypoint_navigation.wbt`: the single required and submitted Webots world.
- `controllers/epuck_waypoint_controller/`: navigation, task, speech, gesture, safety, and logging code.
- `tools/` and `tests/`: live launchers and repeatable validation.
- `models/`: bundled offline Vosk English model.
- `protos/vendor/`: local official Webots R2025a resources used by the world.
- `evidence/`: selected passing JSON/log evidence and device/gesture analysis.
- `demo/`: final demonstration video and preview images.
- `documents/`: project introduction/literature review and documentation.
- `documents/Manikanta_Project_Changes(E-puck Changes).csv`: the approved project-change requirements.
- `SHA256SUMS.txt`: integrity hashes for all other files in the package.

Raw participant video, UREC2 material, caches, full transient validation runs,
intermediate recordings, the machine-specific virtual environment, legacy
Toyota world/controller assets, Webots project-state files, and unrelated
source artwork are deliberately excluded from the submission package. Selected
non-identifying validation summaries, results, logs, and screenshots are kept
under `evidence/`.
