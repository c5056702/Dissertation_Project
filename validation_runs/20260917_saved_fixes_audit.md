# Saved fixes audit - 17 September 2026

Project: `C:\Users\manik\Downloads\35056702_Dissertation_Final_Project~`

The recorded software fixes are present and saved. Current automated checks pass. Full physical acceptance is still incomplete; saved files and passing tests do not establish reliable recognition of every live command or gesture.

## Fresh verification

- Ran `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`: **142 tests passed**, exit 0 (2.346 seconds).
- All **252 files** in `SHA256SUMS.txt` match their recorded SHA-256 hashes; no missing files or mismatches.
- Reviewed six local fix-change manifests. All **22 unique changed files** match their latest recorded post-fix hashes. No controller, test, or tool Python/PowerShell files are absent from the package manifest.
- `pip check`: no broken requirements. OpenCV, MediaPipe, NumPy, sounddevice and Vosk import successfully.
- Project interpreter: `.venv\Scripts\python.exe`, Python **3.12.10, 64-bit**, based on `C:\Users\manik\AppData\Local\Programs\Python\Python312\python.exe`.
- Webots discovery resolves `C:\Program Files\Webots\msys64\mingw64\bin\webots.exe`; installed `resources/version.txt` reports **R2025a**.
- `py -0p` reports no installations in this sandbox, consistent with the earlier setup notes; direct execution of the project's existing Python environment succeeds.
- No current Docker simulator regression was run. Docker was not found on PATH; older packaged simulator evidence predates the latest local fixes.

## Recorded fixes present in source and regression tests

- Fresh nod required after a spoken destination override; safe stop and mode transitions.
- Moving route-selection tilts pause navigation and wait for a later nod.
- Shake detection requires yaw excursions on both sides of neutral; corrected camera pose geometry avoids roll-induced yaw.
- Repeated-gesture rearming and pitch/yaw blocker feedback.
- Bounded `GO TO ALPHA` alternative for A and retained final speech decisions.
- Repeated pending destinations preserve the selected alternative; current-position route planning produces distinct alternatives and rejects unavailable alternatives.
- Consistent console/dashboard route status, destination labels and current guidance.
- Startup progress messages, clean cancellation, adapter cleanup and prevention of Webots launch after cancelled preflight.

No missing recorded implementation was identified in this review. No source code, dependency pins, world, existing notes or checksum manifest was changed during the audit. This report is a new audit artifact outside the existing package manifest.

## What the saved live events establish

The latest live event logs contain observations newer than `client_setup_notes.md`:

- `20260917_012859_live/controller_events.ndjson`: initial IDLE (line 3), START to READY (15-16), pending A (23), later nod confirmation (30-31), head-shake stop (92-94), subsequent START (109-110), voice STOP during travel (339), restart (343-344), dashboard STOP (391), and RESET request (394). A RESET request does not by itself prove completion at S.
- `20260917_010230_live/controller_events.ndjson`: right-tilt alternative selection for C (408), later nod (417-418), moving destination override to B (684-685), and subsequent nod confirmation (713-714). Accepted speech, face calibration and arrivals are present in these later runs.
- `20260916_203230_live/controller_events.ndjson`: one successful in-motion RIGHT tilt (187), paused alternative pending (189), and later nod/alternative route confirmation (196-198). This is evidence of one success, not repeated reliable LEFT/RIGHT recognition across destinations.

These are historical observations, not a fresh device test today. The earlier client configuration used Realtek microphone index 1 and camera 0. No microphone, webcam or Webots session was opened for this audit, and no media was recorded.

## Remaining checks and documentation gaps

- Confirm repeated left and right tilts during travel, across destinations, with neutral rearming and a separate nod.
- Confirm incompatible PICKUP while awaiting a nod safely stops and accepts a fresh START; separately confirm head shake during pending confirmation.
- Confirm visible dashboard agreement and RESET completion at S, and repeat the full acceptance sequence with the current physical inputs.
- Speech remains susceptible to misrecognition: the latest run rejects `go to a a`; both literal A and ALPHA have been accepted in saved runs. This does not establish a complete repair of recognition of the short letter A.
- Run current simulator regression when Docker is available if full regression evidence is needed.
- `instructions.md:505` still reports 72 tests; the current suite has 142. `PROJECT_CHANGES_CHECKLIST.md`'s 100% implementation summary is historical and must not be read as proof that all current physical acceptance checks are complete.
- `client_setup_notes.md` stops before the two later September 17 live runs and understates their observed successes. Some live `result.json` summaries are also incomplete relative to their event logs: the 20260916_210325 summary reports one route start while its event log contains four.

## Live launch

After closing any existing project Webots session, enumerate the current microphone index with:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --list-microphones
```

If the real Realtek microphone is still index 1, run from the project root:

```powershell
.\.venv\Scripts\python.exe tools\run_live.py --microphone 1 --require-ready --webots "C:\Program Files\Webots\msys64\mingw64\bin\webots.exe"
```

Otherwise substitute its current index. Software checks pass; current physical input readiness and the remaining acceptance checks require a live session with the user.
