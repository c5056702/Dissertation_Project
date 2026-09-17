# Project usage instructions

## 1. What this project does

This project runs an e-puck robot in a Webots R2025a simulation. The robot can
be given destination and task commands by voice, while head gestures select a
route, confirm a command, or stop the robot.

The main world contains four labelled locations:

- `S`: start location in the lower-left.
- `A`: pickup location in the upper-left.
- `B`: pickup location in the lower-right.
- `C`: drop-off location in the upper-right.

The robot navigates autonomously after a command is confirmed. It uses its GPS,
compass, internal waypoint graph, and `ps0`–`ps7` proximity sensors. There are no
coloured route lines on the floor. The enlarged green e-puck body, yellow
heading arrow, translucent locator, active destination, and status overlay make
the simulation easy to follow without changing the tested robot physics.

## 2. Project location

The project directory is:

```text
F:\Head gesture thesis\head_gesture_car
```

Open PowerShell and enter the project before running any command:

```powershell
cd "F:\Head gesture thesis\head_gesture_car"
```

## 3. Required software and hardware

### Required for live voice and gesture control

- Windows 10 or Windows 11.
- Webots R2025a installed on the Windows computer.
- Python 3.12 recommended.
- A working microphone.
- A working webcam.
- Permission for desktop applications to access the microphone and camera.
- The local Vosk model in
  `models\vosk-model-small-en-us-0.15`.

Voice and camera processing runs locally. It does not require a cloud speech
service, an LLM, or an internet connection after Webots resources and Python
dependencies are installed.

### Required for automated simulation testing

- Docker Desktop.
- The official `cyberbotics/webots:R2025a-ubuntu22.04` Docker image.

Docker tests use deterministic command and gesture events. They verify the
controller and robot behavior, but they do not test the physical Windows
microphone or webcam.

## 4. First-time setup

Recommended command with 64-bit Python 3.12 installed:

```powershell
py -3.12 tools/setup_client.py
```

This creates a local environment, installs dependencies, verifies package
checksums when available, checks imports, and runs tests. `AGENTS.md` provides
the full setup procedure for Codex on a new laptop. Paths shown elsewhere in
this guide are development examples; substitute the actual extracted folder.

### 4.1 Create the Python environment

From the project directory, run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The main packages are Vosk for offline speech recognition, MediaPipe and OpenCV
for head-pose recognition, and `sounddevice` for microphone input.

### 4.2 Configure the Webots executable

The live launcher automatically checks an explicit `--webots` argument, the
`WEBOTS_EXECUTABLE` environment variable, `PATH`, and standard Program Files and
Local AppData installation locations. If automatic discovery fails, use:

```powershell
$env:WEBOTS_EXECUTABLE = "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"
```

Confirm that the selected file exists:

```powershell
Test-Path -LiteralPath $env:WEBOTS_EXECUTABLE
```

The result should be `True`. This environment variable applies to the current
PowerShell window. Set it again in a new PowerShell window if necessary.

### 4.3 Check the offline speech model

Run:

```powershell
Test-Path -LiteralPath ".\models\vosk-model-small-en-us-0.15"
```

The result should be `True`.

## 5. Prepare the microphone and camera

Before starting Webots:

1. Enable Windows camera and microphone permission for desktop applications.
2. Connect the intended webcam and microphone.
3. Close applications that may exclusively hold the webcam.
4. Set the intended microphone as the Windows default input device, or select
   it explicitly using the commands below.
5. Place the webcam approximately at eye level with the face well lit.

Run the non-recording device check:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --wait-seconds 15
```

A successful report contains values equivalent to:

```text
"ready": true
"voice": "ready"
"gesture": "ready"
"media_saved": false
```

The check reports the microphone ready only after receiving real callback data
and reports the webcam ready only after receiving valid frames. It closes both
devices when the check finishes and does not save audio, video, frames, or face
landmarks.

Before choosing a microphone, list every Windows input device:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --list-microphones
```

Say `start` during the live session and watch the dashboard. A changing
microphone `level`, increasing `callbacks`, and `hearing: start` prove that
audio is reaching the local Vosk recognizer. If callbacks increase but level
stays near zero, the selected device is silent or is the wrong input.

### Selecting a particular camera or microphone

Use a camera index such as `0` or `1`:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera 1 --wait-seconds 30
```

Select a microphone by its device number or name:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --microphone "Realtek" --wait-seconds 30
```

To save only the technical readiness report:

```powershell
.\.venv\Scripts\python.exe tools\check_live_inputs.py --camera auto --output validation_runs\device_check.json
```

## 6. Start live voice and head-gesture control

Use the Windows live launcher because Windows must provide the physical camera
and microphone:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py
```

The launcher performs a device check and then opens
`worlds\epuck_waypoint_navigation.wbt` in real-time Webots mode.

It also opens the separate `E-puck Live Input & Traceability` dashboard. The
camera preview is the external webcam used by MediaPipe, not the simulated
e-puck camera. The preview is labelled `LIVE - NOT RECORDED`.

If a device is initially unavailable, the default launcher opens Webots with
the robot safely stopped and retries the missing device every three seconds.
Use strict mode to refuse to launch until both devices are ready:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --require-ready
```

Useful alternatives are:

```powershell
# Select a camera and microphone and allow a longer initial wait.
.\.venv\Scripts\python.exe tools\run_live.py --camera 1 --microphone "Realtek" --wait-seconds 30

# Change how often an unavailable device is retried.
.\.venv\Scripts\python.exe tools\run_live.py --retry-seconds 5
```

### Live dashboard controls and traceability

- `STOP` immediately clears pending input, stops both motors, enters `STOPPED`,
  and records `dashboard_stop` as the safety source.
- `RESET AT S` stops first, records the reset request, resets Webots, places the
  e-puck back at S, and reopens a fresh dashboard session.
- Closing the dashboard is treated as a safety stop; restart the live launcher
  to reopen it.
- The input panel shows camera/microphone health, calibration percentage, face
  presence, head pose, candidate/confirmed gesture, cooldown, microphone level
  and callback count, partial/final transcript,
  confidence, and acceptance or rejection reason.
- `Last speech` and `Decision` keep the latest nonempty final result visible
  while new partial speech arrives. Rejected final commands are also logged
  with word confidences; microphone audio is never saved.
- The coloured `MODE: VOICE` or `MODE: CAMERA` badge shows the current control
  mode. A valid voice command switches to Voice Mode. A valid ordinary gesture
  switches back to Camera Mode. `stop` and head shake remain higher-priority
  global safety actions.
- The `NEXT STEP` panel gives live instructions: say `START`, say a destination,
  tilt left/right, nod to confirm, return to neutral while the gesture detector
  re-arms, reconnect a device, or choose a valid paused-state command.
- The robot panel shows state, pending command, nod requirement, route,
  origin/destination, GPS, next waypoint, distance, sensor peak, and safety.
- The event panel shows the newest technical command, gesture, route, device,
  reset, and safety transitions. It never contains camera pixels or audio.

Dashboard updates are limited to 8 FPS so the 32 ms navigation controller
remains responsive. Docker scenarios do not open this Windows-host window.

## 7. Camera calibration and gestures

When the camera connects, look directly at it and keep the head in a comfortable
neutral position for approximately two seconds. The system uses about 45 valid
frames to learn the user's neutral head pose.

Do not nod or tilt during calibration. After calibration, perform gestures
slowly and clearly, then return to neutral before performing another gesture.

| Gesture | Meaning |
| --- | --- |
| Tilt head left (ear toward shoulder) | Select the graph's shortest route. During travel, pause and request that route to the same destination; return neutral, then nod. |
| Tilt head right (ear toward shoulder) | Select a distinct alternative route when one is available. During travel, pause and request it to the same destination; return neutral, then nod. |
| Nod | Confirm a pending, state-valid command or route choice. |
| Shake head left and right | Immediately cancel pending work, stop both motors, and enter `STOPPED`. |
| Neutral head | Calibration and re-arming position; it does not issue a command. |

Keep looking toward the camera when tilting; move the ear toward the shoulder.
Turning the nose to one side is not a route-selection gesture. A shake requires
turning to both sides of the calibrated neutral position within the detector's
short motion window. A turn to just one side and back to neutral is not a shake.

Gestures use confidence thresholds, smoothing, a short hold requirement, and a
cooldown. A single quick head movement may intentionally be ignored. A held
gesture is emitted once and must be followed by a stable neutral pose before it
can be detected again.

After each tilt or nod, return to your starting posture and wait for `Detector:
armed`. The next-step prompt now identifies whether to straighten the head,
level the chin, face the camera, or hold neutral longer. The same readiness
rules apply to A, B, C, and S. If the state is `STOPPED`, say `START` before
requesting a destination again.

If the camera loses the face, incomplete motion is discarded. During live
operation, a camera disconnection stops the robot. When the camera reconnects,
the MediaPipe session is restarted and neutral calibration must be completed
again.

## 8. Accepted voice commands

Speak one command at a time. Use the phrases in this table; ordinary free-form
sentences are intentionally rejected.

| Voice command | When it is used | What happens |
| --- | --- | --- |
| `start` | `IDLE` or after a safety stop | Activates the controls and enters `READY`. It does not move the robot. |
| `go to A` | `READY`, `ARRIVED`, navigating, or paused | Requests A as the destination. During movement it pauses and replaces the current destination; a nod is required before the new route starts. |
| `go to alpha` | Same as `go to A` | An alternative spoken name for A, using the same confidence and nod requirements. |
| `go to B` | `READY`, `ARRIVED`, navigating, or paused | Requests B as the destination. A nod is required. |
| `go to C` | `READY`, `ARRIVED`, navigating, or paused | Requests C as the destination. A nod is required. |
| `go to S` | `READY`, `ARRIVED`, navigating, or paused | Requests the start location. A nod is required. |
| `left` or `turn left` | While navigating | Stops safely and opens the bounded mid-route clarification state. It does not steer the wheels left. |
| `right` or `turn right` | While navigating | Stops safely and opens the same clarification state. It does not steer the wheels right. |
| `continue` | Navigating or paused | Continues the already confirmed autonomous route. |
| `forward` | Navigating or paused | Same safe meaning as continue; it never directly drives the wheels. |
| `alternative route` | Paused with an active destination | Requests a different valid graph route. Nod to confirm. |
| `reverse` | Navigating or paused | Requests a route from the measured current position back to the active route origin. Nod to confirm. |
| `stop` | Any state | Immediately stops the motors, clears pending work, and enters `STOPPED`. |
| `start A` | Legacy pickup workflow | Activates and requests the pickup workflow through A. Select a route and nod. |
| `start B` | Legacy pickup workflow | Activates and requests the expanded pickup workflow through B. Select a route and nod. |
| `pickup` or `pick up` | At A or B in the legacy workflow | Requests pickup confirmation. Nod to confirm. |
| `drop off` | After confirmed pickup | Requests travel to C. Nod to confirm. |
| `return` | At C after drop-off | Requests the return journey C→A→S. Nod to confirm. |

## 9. Basic point-to-point example

To travel from S to A using the shortest route:

1. Complete neutral camera calibration.
2. Say `start`.
3. Confirm that the overlay shows `READY`. The robot must remain stationary.
4. Say `go to A`.
5. Tilt the head left to explicitly select the shortest route. This step can be
   omitted because the shortest route is the default.
6. Nod once.
7. The overlay changes to `NAVIGATING`, and the robot travels autonomously.
8. At A, the motors stop and the overlay changes to `ARRIVED`.

At startup the dashboard is in Voice Mode and explicitly asks for `START`.
Both wheel motors are explicitly set to zero before input devices and the main
simulation loop start, and the dashboard shows `ROBOT LOCKED AT S - say START`.
After `START` it asks for a destination; head gestures alone cannot move the
robot because no destination has been chosen. After `GO TO A/B/C/S`, the
dashboard asks for a nod or route-selection tilt. That valid gesture switches
the badge to Camera Mode and confirms/chooses the route as appropriate.

For live microphone use only, if Vosk hears the short word `start` as
`start A` or `start B`, the startup gate treats it only as `START`. The robot
still waits for a separate `GO TO A/B/C/S` command, so recognition ambiguity
cannot cause movement.

To request the alternative route, tilt right before nodding in step 6.

Every recognised route tilt is reported in the launch terminal and dashboard,
for example `TILT RIGHT -> TO A: ALTERNATIVE selected; awaiting NOD` or
`TILT LEFT -> TO B: SHORTEST selected; awaiting NOD`. The persistent `Route
status` row keeps the destination and choice visible during neutral re-arming.
It matches the console's `[route]` line: after confirmation, both change from
`TO A: ALTERNATIVE - awaiting NOD` to `TO A: ALTERNATIVE - navigating`.
Timestamped tilt history describes past selections without an expired nod
instruction. During travel, re-arming guidance is for the next gesture; it
does not mean that the confirmed route is waiting to start.
The older route is labelled `Previous route` while a new request awaits a nod.
The terminal also reports the destination and actual route type when it starts.

Repeating the same pending destination preserves your chosen route. A different
destination starts a new selection, defaulting to shortest. A tilt sampled
alongside speech is explicitly reported as ignored because voice has priority;
make a fresh tilt after the pending prompt. If no distinct alternative exists,
the robot stays stopped and reports that, without falling back to shortest.

After arriving at A, another point-to-point journey can be started by saying,
for example, `go to C`, followed by a nod.

## 10. Changing the route while moving

To change the route using the camera, tilt the head right for an alternative
or left for the shortest route. The robot pauses and keeps the destination.
Wait for the pending route prompt, return the head to neutral, then make a
fresh nod. The route is replanned from the robot's measured position. Without
the nod, the robot stays stopped; a shake or voice STOP cancels the request.
These gestures select a graph route rather than directly steering the wheels.
They also work after a spoken left/right command has paused the robot.

The robot is autonomous; directional voice commands are safe interventions,
not direct steering commands.

Example:

1. While the robot is navigating, say `turn right`.
2. The robot stops and enters `PAUSED`.
3. Give one bounded response:
   - Say `continue` to resume the current route.
   - Say `alternative route`, then nod, to calculate another path.
   - Say `go to A`, `go to B`, `go to C`, or `go to S`, then nod, to replace
     the destination.
   - Say `reverse`, then nod, to return towards the route origin.
   - Say `stop` to enter the emergency-stopped state.

Route replacement, an alternative route, and reverse all use the robot's
measured GPS position. The robot does not teleport back to the beginning of a
predefined route.

If the robot is moving in Camera Mode and the user says `go to B`, the voice
command immediately takes priority, pauses the current route, replaces the
destination, and switches the badge to Voice Mode. It remains in Voice Mode
until a valid gesture is made. Nod confirms the pending shortest route, while a
route-selection tilt chooses a route and also returns control to Camera Mode.

## 11. Legacy pickup and drop-off example

To run the original S→A→C→A→S task:

1. Complete neutral calibration.
2. Say `start A`.
3. Tilt left for the short S/A route or right for the long S/A route.
4. Nod to begin moving to A.
5. At A, say `pickup`, then nod.
6. Say `drop off`, then nod. The robot travels to C.
7. At C, say `return`, then nod.
8. The robot returns through A to S and finishes in `READY`.

For the expanded B workflow, begin with `start B`. The robot first travels to A
and then continues to B for pickup before travelling to C and returning to S.

## 12. Emergency and safety behavior

The following actions have immediate priority over navigation:

- Say `stop`.
- Shake the head left and right.
- Press the Webots keyboard emergency key supported by the controller (`End`).
- Trigger a proximity-sensor obstacle threshold.
- Lose valid localisation or an active live input device.
- Encounter a controller failure.

After an emergency stop, both motors are zeroed, pending work is cleared, and
the state becomes `STOPPED`. Correct the cause, say `start`, wait for `READY`,
and issue a new destination command.

Invalid, unrecognised, low-confidence, ambiguous, or state-invalid commands do
not initiate movement. If voice and gesture events arrive together, safety
actions such as `stop` or head shake always win.

## 13. Understanding the Webots display

- The large green circular body with dark sides is the enlarged e-puck visual.
- The yellow arrow on the robot shows its forward direction.
- The translucent yellow locator underneath helps identify its position.
- S, A, B, and C are coloured square waypoint markers.
- The active destination marker is visually emphasised.
- The top overlay reports the state, most recent action, active graph route,
  destination, and safety reason.
- No floor route lines are displayed. Their absence does not affect navigation.
- The small upper-left inset is the simulated e-puck camera view during rendered
  or live operation.

Common states are:

| State | Meaning |
| --- | --- |
| `IDLE` | Waiting for `start`; no movement is permitted. |
| `READY` | Active and waiting for a valid destination or task command. |
| `NAVIGATING` | Following a confirmed autonomous route. |
| `PAUSED` | Stationary and waiting for a bounded route decision. |
| `ARRIVED` | Stationary at the requested point. |
| `STOPPED` | Emergency/safety stopped; say `start` after correcting the cause. |

The legacy workflow also uses pickup, drop-off, and return states displayed by
the same overlay.

## 14. Run automated Docker verification

Start Docker Desktop, wait until the Docker engine is ready, and enter the
project directory. Run one complete baseline workflow with:

```powershell
.\tools\run_docker_validation.ps1 -Scenario baseline_short
```

Useful suites are:

```powershell
# All four canonical pickup/drop-off workflows.
.\tools\run_docker_validation.ps1 -Scenario workflows

# Expanded point-to-point routes and mid-route interventions.
.\tools\run_docker_validation.ps1 -Scenario navigation_changes

# Already-transcribed command strings; no real audio is used.
.\tools\run_docker_validation.ps1 -Scenario transcriptions

# Emergency stops, obstacles, lost devices/localisation, and injected failures.
.\tools\run_docker_validation.ps1 -Scenario safety
```

Repeat a test or request rendered evidence:

```powershell
.\tools\run_docker_validation.ps1 -Scenario baseline_short -Repeat 10
.\tools\run_docker_validation.ps1 -Scenario goto_a_shortest -Visible
```

Record the deterministic all-changes demonstration:

```powershell
.\tools\run_docker_validation.ps1 -Scenario demo_showcase -Visible -RecordDemo
```

Results are saved in `validation_runs\<run-id>\`, with aggregate summaries in
`validation_runs\suite_summaries\`. Docker containers are temporary and are
removed after each completed run.

## 15. Run the local tests

The project includes offline tests for commands, gesture logic, graph routes,
device recovery, navigation safety, metrics, and world configuration:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The verified project currently contains 72 offline tests.

## 16. Replay an existing gesture video

To test a recorded head-gesture clip through the same MediaPipe classification
path without retaining its frames or face landmarks:

```powershell
.\.venv\Scripts\python.exe tools\analyze_gesture_video.py "C:\path\to\gesture_video.mp4" --no-realtime --output validation_runs\gesture_clip\analysis.json
```

The JSON result contains technical event categories, timestamps, threshold
evidence, and face-detection coverage only.

For the approved project demonstration, launch Webots with
`F:\Head gesture thesis\tilt_gesture.mp4` and timed, already-transcribed text
fixtures. This does not open or emulate a microphone:

```powershell
.\.venv\Scripts\python.exe tools\run_trace_demo.py
```

Build the consented derived dashboard video and technical report with:

```powershell
.\.venv\Scripts\python.exe tools\build_trace_dashboard_demo.py
```

## 17. Demonstration video

The primary professor-ready gesture-controlled presentation is:

```text
F:\Head gesture thesis\head_gesture_car\demo\head_gesture_video_controlled_robot.mp4
```

It is a silent, captioned, synchronized end-to-end run. The dashboard on the
left replays selected consented sections of `tilt_gesture.mp4` through the
production classifier; the Webots robot on the right receives those exact
classified categories and timestamps through the normal controller path. The
sequence is left tilt, nod, left tilt, nod, right tilt, nod, and shake. The
first command completes `S_A_SHORT` and reaches A before the second command
starts. The second completes `GRAPH_A_C_SHORTEST` and reaches C before the third
starts. The third begins `GRAPH_C_B_ALTERNATIVE`, then the video-derived shake
interrupts it and stops the robot. Text-only `start A`, `go to C`, and `go to B`
fixtures provide the bounded voice commands required by the multimodal
workflow; no microphone audio is used. The subject's face is persistently
blurred in the saved professor presentation.

Older development recordings remain available in the working directory but
are excluded from the submission ZIP. Its only MP4 is the blurred presentation
above, and the raw source clip is not packaged.

Rebuild it from the newest rendered evidence with:

```powershell
.\tools\build_showcase_video.ps1
```

To reproduce the synchronized gesture-controlled copy, build the classified
sequence and dashboard, run `tools\run_gesture_control_webots.py` through the
Docker compose service, then run:

```powershell
.\tools\build_gesture_control_demo.ps1
```

## 18. Privacy and stored results

During normal live operation, microphone samples, camera frames, and face
landmarks are processed transiently and are not written to project files. The
dashboard retains only the newest frame in memory. The project stores only
technical results such as:

- Recognised or rejected command categories.
- Recognised gesture categories.
- State transitions.
- Selected route and destination.
- GPS position and route progress.
- Response and execution times.
- Safety-stop source and test outcome.

The final presentation contains selected sections of the supplied gesture clip
after the user confirmed subject permission. It was created explicitly as demo
media; automatic runtime recording remains disabled and the raw clip is not in
the submission ZIP.

## 19. Troubleshooting

### The launcher says to run dependency/model setup

Check all three items:

```powershell
Test-Path -LiteralPath ".\.venv\Scripts\python.exe"
Test-Path -LiteralPath ".\models\vosk-model-small-en-us-0.15"
Test-Path -LiteralPath $env:WEBOTS_EXECUTABLE
```

Create the virtual environment, install `requirements.txt`, confirm the model
folder, and set `WEBOTS_EXECUTABLE` to the actual Webots R2025a executable.

### Startup pauses while loading MediaPipe

The preflight prints its current loading stage before Webots opens. Recognition
imports, Vosk model loading and camera discovery happen before the
`--wait-seconds` device retry window, so that option is not a total startup timeout.
Allow initialization to finish. A `KeyboardInterrupt` traceback means the process
received an interrupt, usually Ctrl+C; by itself it does not indicate a broken
MediaPipe or Matplotlib installation. The updated launcher reports cancellation
briefly and does not start Webots after a cancelled preflight.

### The camera remains in `waiting`

- Enable Windows camera permission for desktop applications.
- Close Teams, Zoom, browser tabs, or camera software using the webcam.
- Disconnect and reconnect the camera.
- Try `--camera 0`, `--camera 1`, or `--camera 2`.
- Improve lighting and keep the complete face visible.
- Run the device check again with `--wait-seconds 30`.

### The microphone remains in `waiting`

- Enable Windows microphone permission for desktop applications.
- Confirm that the microphone input meter moves in Windows settings.
- Set the intended device as the default input.
- Select it using `--microphone "device name"` or its device number.
- Close programs that may exclusively hold the microphone.

### Voice is ready, but a command is not accepted

- Use exactly one of the bounded phrases in section 8.
- Speak one command at a time at a moderate pace.
- If the short letter A does not produce a transcript, try `go to alpha`.
  Watch the microphone level and wait for the pending A prompt before tilting
  or nodding. This alternative phrase still needs physical speech testing.
- Check `Last speech` and `Decision` for the last final result; an unclear
  word remains visible while the recogniser listens for another command.
- Reduce background noise and move closer to the microphone.
- Check the state overlay; a valid phrase can still be rejected in the wrong
  state.
- Remember that route/destination changes usually require a confirming nod.

### A gesture is not recognised

- Face the camera neutrally for approximately two seconds after connection.
- Keep the face centred and well lit.
- Make one deliberate gesture and hold it briefly.
- Return to neutral before the next gesture.
- Wait for `Detector: armed`; follow the next-step posture guidance if it
  stays on `rearming`. A face-loss safety stop requires a fresh `START`.
- If the detector is armed but a moving tilt is missed, watch `NEXT STEP`:
  it identifies a simultaneous chin movement or face turn that blocks the
  tilt, and tells you when to keep holding a detected tilt. Keep looking at
  the camera, move your ear toward your shoulder, and hold for about one
  second or until the robot pauses. Return neutral and nod to confirm.
- `gesture_detection_status` events record categorical detector readiness
  and blockers during operation. These diagnostics contain no head-pose
  coordinates, landmarks, webcam frames, or microphone audio.
- Avoid performing a tilt and nod at the same instant.
- If the webcam reconnected, complete neutral calibration again.

### The robot does not move

- Check that the state is `READY`, not `IDLE` or `STOPPED`.
- Say `start` if necessary.
- Say a destination command and nod to confirm it.
- Check the overlay for a rejected command, missing face, device loss, obstacle,
  or localisation error.
- Ensure the robot is not waiting in `PAUSED` for `continue` or another bounded
  response.

### The robot stops unexpectedly

Read the safety reason in the overlay and inspect the newest
`validation_runs\<run-id>\controller_events.ndjson` file. Correct the obstacle,
camera, microphone, or localisation problem, then say `start` and issue a new
command.

### Docker cannot start the validation

- Start Docker Desktop and wait for the engine to report ready.
- Confirm Docker is on `PATH` using `docker version`.
- Confirm the official image is available with
  `docker image inspect cyberbotics/webots:R2025a-ubuntu22.04`.
- The first world load may require internet access for official Webots PROTO
  resources if they are not already cached.

### Rendered Docker tests are slow

This is expected when Webots uses Mesa software rendering. Headless tests are
much faster. Use `-Visible` only when screenshots or a movie are needed, and
allow the movie encoder to finish before closing Docker.

## 20. Safe shutdown

Before closing a live demonstration:

1. Say `stop` or shake the head.
2. Confirm that the overlay shows `STOPPED` and the robot is stationary.
3. Close the Webots window.
4. Close the PowerShell launcher if it remains open.

This leaves no live validation container running and releases the Windows
microphone and webcam.
