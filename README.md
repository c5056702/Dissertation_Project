# Multimodal e-puck waypoint navigation

## Start on a new Windows laptop

Extract the ZIP to a writable folder. Install 64-bit Python 3.12 and Webots
R2025a, then run from that folder:

```powershell
py -3.12 tools/setup_client.py
.\.venv\Scripts\python.exe tools/run_live.py --list-microphones
.\.venv\Scripts\python.exe tools/run_live.py --microphone INDEX --require-ready
```

Replace INDEX with the real microphone's listed number. First setup needs
internet to install Python packages; subsequent recognition is local. Docker is
only needed for automated simulator tests. Codex on the client computer should
read `AGENTS.md` and follow its setup and physical-device acceptance steps.
The setup report is written to `validation_runs/client_setup.json`.

For an in-motion destination change, say **GO TO B**, wait for the stopped
pending-destination prompt in Voice Mode, then make a **fresh nod**. A nod sampled
alongside the spoken command is not confirmation. See `VOICE_OVERRIDE_FIX.md`
for the latest regression evidence and simulation braking tolerance.

This project is a Webots R2025a technical prototype for local voice- and head-gesture-controlled e-puck navigation. The implemented and submitted prototype uses `worlds/epuck_waypoint_navigation.wbt`; unrelated legacy worlds are not required.

For complete setup, live-control, testing, safety, and troubleshooting steps,
see [`instructions.md`](instructions.md).

## Map and workflow

- S: lower-left start.
- A: upper-left pickup.
- B: lower-right pickup.
- C: upper-right drop-off.
- The project starts with both motors explicitly locked at zero in `IDLE` and Voice Mode. The dashboard displays `ROBOT LOCKED AT S - say START`. Say `start` to activate the controls; this never selects a destination or moves the robot. Then say `go to A`, `go to B`, `go to C`, or `go to S`.
- A left tilt selects the shortest route, a right tilt selects an alternative, nod confirms, and shake cancels/stops.
- The console's `[route]` line and dashboard's `Route status` share the same current status: `TO A: ALTERNATIVE - awaiting NOD` changes to `TO A: ALTERNATIVE - navigating` after confirmation. Tilt history is timestamped. Repeating that pending destination preserves the choice; requesting a different destination defaults to shortest until another tilt.
- If the spoken letter A is missed, `go to alpha` also requests A with the same nod confirmation. After each gesture, return to your starting posture and wait for `Detector: armed`; the dashboard explains any remaining posture adjustment.
- During travel, a left/right tilt pauses and selects a shortest/alternative route to the same destination from the current position. Return to neutral, then make a fresh nod to resume. Tilt means ear toward shoulder while looking at the camera; turning the face side to side is the stop gesture.
- The original `start A`/`start B` pickup, `pickup`, `drop off`, and `return` workflow remains supported.
- Floor route lines are intentionally absent. The robot navigates with GPS, compass, internal graph waypoints, and proximity sensors; the overhead view shows the waypoint markers, destination emphasis, robot locator, and command/state overlay only.
- The overhead e-puck uses a 0.28 m non-colliding visual body, approximately 3.8 times its standard diameter. Its official wheel, sensor, and collision dimensions remain unchanged, so the larger presentation does not alter navigation results.

## Automated validation

Docker Desktop and the installed official `cyberbotics/webots:R2025a-ubuntu22.04`
image are the supported automated Webots environment. The wrapper mounts this
project read/write, runs Webots under an isolated Xvfb display, and removes the
ephemeral validation container when it finishes.

Run one complete workflow:

```powershell
.\tools\run_docker_validation.ps1 -Scenario baseline_short
```

Run all four navigation workflows:

```powershell
.\tools\run_docker_validation.ps1 -Scenario workflows
```

Run all 12 expanded destination, alternative-route, and mid-route intervention scenarios:

```powershell
.\tools\run_docker_validation.ps1 -Scenario navigation_changes
```

Run the no-audio transcription suite. It supplies already-transcribed command
strings to the production normaliser and task controller, including case and
spacing variants, invalid text, wrong-state text, and emergency stop:

```powershell
.\tools\run_docker_validation.ps1 -Scenario transcriptions
```

Run all safety/failure scenarios:

```powershell
.\tools\run_docker_validation.ps1 -Scenario safety
```

Add `-Repeat 10` for repeated trials or `-Visible` to render through Xvfb and
capture the configured Webots overview at initial, waypoint, safety-stop, and
final states. Per-run evidence is written only under `validation_runs/`;
aggregate results are stored in `validation_runs/suite_summaries/`.

## Demo recording

The primary professor-ready recording is
`demo/head_gesture_video_controlled_robot.mp4`. This 33.16-second H.264 video is
an actual end-to-end replay: selected sections of the consented clip are passed
through the production MediaPipe classifier, the emitted timestamps drive the
normal Webots controller, and the matching dashboard and robot run are shown
side by side. Left tilt and nod start the shortest S-to-A route; the replay
waits for arrival at A before a second left tilt and nod start the shortest
A-to-C route. After arrival at C, right tilt and nod start an alternative route
toward B, and the final head shake interrupts that third command in `STOPPED`.
The subject's face is persistently blurred in this saved presentation copy.

Older development recordings remain outside the submission ZIP. The blurred
gesture-controlled presentation above is the package's only MP4, and the raw
gesture clip is not packaged.

Record a new raw demo from the verified Docker simulation with:

```powershell
.\tools\run_docker_validation.ps1 -Scenario demo_showcase -RecordDemo
```

Webots writes `demo_raw.mp4` into that run's `validation_runs/<run-id>/`
directory after the complete workflow and encoder flush.

Rebuild the captioned presentation from the newest rendered showcase and
safety evidence with:

```powershell
.\tools\build_showcase_video.ps1
```

Rebuild the synchronized gesture-controlled professor copy after producing a
passing rendered gesture replay with:

```powershell
.\tools\build_gesture_control_demo.ps1
```

The local offline tests can also be run without Webots:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Live local input

Dependencies are version-constrained in `requirements.txt`, installed in `.venv`, and the offline model is located at `models/vosk-model-small-en-us-0.15`.

### Allowed voice commands and camera gestures

| Situation | Voice input | Camera input | Result |
| --- | --- | --- | --- |
| Project starts in `IDLE` | `start` | None required | Activate controls and enter `READY`; the e-puck does not move. |
| Ready or arrived | `go to A`, `go to B`, `go to C`, or `go to S` | Nod | Calculate and follow the shortest route from the current position. |
| A destination command is pending | Same destination command | Tilt left, then nod | Explicitly select the shortest route. |
| A destination command is pending | Same destination command | Tilt right, then nod | Select a distinct alternative route when available. |
| Navigating | `left`, `turn left`, `right`, or `turn right` | None required | Stop safely and ask whether to continue, change route/destination, reverse, or stop. |
| Navigating or paused | `forward` or `continue` | None required | Continue the already confirmed route; this does not directly drive the wheels. |
| Navigating or paused | `reverse` | Nod | Replan from the measured current position to the active route's origin. |
| Navigating or paused | `go to A/B/C/S` | Nod | Replace the destination and replan from the measured current position. |
| Paused | `alternative route` | Nod | Select a different valid path to the active destination. |
| Navigating or paused with an active destination | None required | Tilt left/right, return neutral, then nod | Pause and replan the shortest/alternative route to the same destination from the current position. |
| Any state | `stop` | None required | Immediately stop, clear pending work, and enter `STOPPED`. Say `start` to reactivate. |
| Any state | None required | Head shake | Immediately cancel/stop with the same priority as voice `stop`. |
| Legacy pickup workflow | `start A` or `start B` | Tilt left/right, then nod | Start the original short/long pickup journey. |
| At legacy pickup A or B | `pickup` or `pick up` | Nod | Confirm pickup. |
| After legacy pickup | `drop off` | Nod | Travel A→C or B→C. |
| At legacy drop-off C | `return` | Nod | Travel C→A→S. |

For a point-to-point demonstration, face the camera neutrally until calibration
is ready, say `start`, then say `go to A` and nod. Tilt right before nodding to
request an alternative. During movement, say `turn left` or `turn right`; the
robot pauses and waits for a bounded reply: `continue`, `alternative route`,
`go to A/B/C/S`, `reverse`, or `stop`. Route/destination changes and reverse
require a nod. `Forward` means continue the autonomous route—it is not unsafe
direct wheel control.

Speak one listed command at a time. This remains a bounded command system, so
unlisted natural-language instructions are rejected. Voice and head recognition
stay active together. Global `stop` or head shake wins first; otherwise a
state-valid microphone command has priority over an ordinary camera gesture in
the same cycle. While moving, a new `go to ...` voice command pauses the current
route and replaces its destination; tilt if desired, then nod to confirm the
switch from the robot's measured position. A newer destination voice command
also replaces one that is still awaiting confirmation. The dashboard then stays
in Voice Mode until the next valid head gesture, which switches it back to
Camera Mode. A gesture cannot start movement immediately after standalone
`start`, because a destination must be spoken first. At the physical live
startup gate, a Vosk result of `start A` or `start B` is deliberately reduced
to activation-only `start`; this prevents a speech suffix from bypassing the
stationary startup stage.

Live microphone and webcam access runs on the Windows host, not inside the
Docker validation container. Check readiness without recording media:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --wait-seconds 15
```

List the client's microphone devices, then explicitly select the device whose
Windows input meter moves if the default device is wrong:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --list-microphones
.\.venv\Scripts\python.exe tools\run_live.py --microphone 2
```

The probe reports a microphone ready only after receiving real callback data,
and a camera ready only after receiving three valid frames. This prevents an
opened virtual camera or stale driver handle from producing a false positive.

Launch real-time Webots:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py
```

An `E-puck Live Input & Traceability` window opens automatically beside
Webots. Its left panel shows the external webcam feed with a face box and
head-pose indicators. The other panels show calibration, detected gesture,
partial and final Vosk transcription, confidence, microphone callback count and
live signal level, acceptance/rejection reason, task
state, pending confirmation, route, GPS/waypoint progress, proximity peak,
device recovery, safety status, and recent technical events. A coloured
`MODE: VOICE` or `MODE: CAMERA` indicator identifies the current control mode,
and the `NEXT STEP` box gives state-specific instructions
such as saying a destination, tilting, nodding, returning to neutral to re-arm,
or saying `start` after a stop. `STOP` immediately
stops the motors. `RESET AT S` stops first and resets the Webots simulation to
its initial S position. Closing the dashboard also causes a safety stop.

The dashboard refreshes at 8 FPS and keeps only its newest transient frame. It
does not record the webcam or microphone. It is intentionally disabled during
headless and deterministic Docker validation.

The launcher waits up to 15 seconds during preflight. If either device is still
missing, Webots starts with the e-puck safely stopped and retries the missing
device every three seconds. There is no live-mode idle timeout. A disconnect
clears the pending task and stops both motors; a recovered camera creates a new
MediaPipe session and requires a fresh 45-frame neutral calibration.

Useful client options:

```powershell
# Refuse to launch unless both devices are already verified
.\.venv\Scripts\python.exe tools\run_live.py --require-ready

# Select a non-default camera or microphone and wait longer
.\.venv\Scripts\python.exe tools\run_live.py --camera 1 --microphone "Realtek" --wait-seconds 30
```

Before a client demonstration, enable Windows camera and microphone access for
desktop applications, close applications that exclusively hold the webcam,
and set the intended microphone as the Windows default input. After the camera
connects, face it directly and remain neutral for roughly two seconds while
calibration completes. Audio, frames, and face landmarks are processed
transiently and are not written to disk.

On this development machine the hardened probe confirmed more than 20 microphone
callbacks and over 160,000 audio bytes through the production adapter, and the Vosk
adapter now explicitly enables the per-word confidence results needed to accept
live commands. The selected virtual microphone carried silence during that
probe, and Windows currently exposes no usable webcam frames. Therefore
physical webcam hot-plug and recovery still require final confirmation on the
client hardware.

## Recorded camera replay

Replay a recorded camera clip through the same MediaPipe pose and gesture code without retaining frames or landmarks:

```powershell
.\.venv\Scripts\python.exe tools\analyze_gesture_video.py "C:\path\to\gesture_video.mp4" --no-realtime --output validation_runs\gesture_video_clip\tilt_analysis.json
```

Recorded timestamps preserve cooldown behavior even with `--no-realtime`. The recognizer emits each sustained tilt or nod once, re-arms after a stable neutral pose, clears incomplete motion when the face is lost, and treats rapid yaw movement as the global shake safety gesture. The JSON output contains only technical counts, event categories/times, derived threshold evidence, and face-detection coverage.

Launch the approved dashboard/Webots demonstration using the consented project
clip and already-transcribed command fixtures, without opening a microphone:

```powershell
.\.venv\Scripts\python.exe tools\run_trace_demo.py
```

Regenerate the derived dashboard demonstration and its technical report with:

```powershell
.\.venv\Scripts\python.exe tools\build_trace_dashboard_demo.py
```
