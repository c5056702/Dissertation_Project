# Client readiness audit — 10 September 2026

## Scope

Reviewed production controller, task/graph/navigation code, live and replay
adapters, dashboard, world and vendored assets, dependency requirements,
launchers, tests, package contents, and setup documentation. This report covers
software portability and verification evidence; physical client devices require
the local acceptance checks in AGENTS.md.

## Corrections

| Finding | Correction |
| --- | --- |
| Live launcher inherited EPUCK_* scenario/replay/fault settings from its shell | Clear these settings before physical live launch, along with conflicting Python paths and stale microphone selection. |
| An invalid explicit Webots path could silently fall back to another installation | Explicit paths now fail clearly when missing. |
| Opening the world directly resolved the Vosk model relative to the controller directory | Model and manual log paths now resolve from the project root. |
| Webots preferences could select Python without this project's libraries | Windows controller bootstrap selects the machine-local .venv interpreter when present. |
| No repeatable client setup entry point | Added tools/setup_client.py for Windows/Python 3.12 64-bit, local environment creation, installation, imports, pip check, tests, and manifest verification. |
| Pending alternative route still displayed shortest-route instructions | Next-step instruction now reflects the selected alternative/long route. |
| Simultaneous voice and SHAKE while stationary or awaiting confirmation could process voice first | SHAKE now wins in both branches. |
| Conflicting pending command stopped movement but left the confirmation latch armed | Clear the pending action and latch and return to microphone mode so START can recover. |
| Pre-START gestures could change the mode label even though activation was still required | Keep microphone mode while IDLE/STOPPED; gestures cannot bypass START. |
| Client setup and developer evidence rebuilding were conflated | AGENTS.md distinguishes live setup, Docker testing, included demonstration, and development-only video/package rebuild prerequisites. |

## Verification

- Existing Windows Python 3.12 environment: pip check reports no broken dependencies.
- Vosk, sounddevice, MediaPipe, OpenCV, and NumPy import successfully.
- All 69 Windows offline tests pass. Compilation checks pass.
- Fresh project copy with a newly created Python 3.12 virtual environment:
  installation from requirements, pip check, recognition/GUI imports, and all
  69 offline tests pass. This was a clean environment on the development host,
  not a test on a different laptop.
- Final-source full Docker regression: 38/38 scenarios pass, with postflight
  tests passing. Summary: `evidence/suite_summaries/20260910_084155_498202_all.json`.
  The headless suite reports 65 tests with one skipped dashboard module; Windows
  executes all 69 tests including dashboard rendering. Docker scenarios use
  deterministic input, not real speech or a physical webcam.
- Fresh installation log: `evidence/client_audit/clean_setup.log`.
  Full Docker log: `evidence/client_audit/docker_all.log`.
- Pending-conflict recovery and simultaneous live SHAKE handling were
  code-reviewed; perform the explicit client acceptance checks in AGENTS.md.
  Deterministic scenarios do not exercise every live-adapter interleaving.
- Package builder verifies every SHA-256 entry, required files, one WBT, one
  blurred MP4, and tests after extraction.

## Client prerequisites and limits

- Python 3.12 64-bit and Webots R2025a must be installed on the laptop.
  Internet is needed for initial pip installation. A copied .venv is not portable.
- The mic must be selected from that laptop's device list. Increasing callback
  counts alone can represent silence; verify signal level and actual speech.
- The real camera must deliver frames, detect the face, and complete neutral
  calibration. Previous development probes found no webcam and a silent virtual
  mic. Those probes do not verify the client's devices.
- Reconnection scans use synchronous driver calls. Slow or hung drivers may
  delay UI/input updates; live response time must be checked on the client.
- Docker runs exercise deterministic input and simulation, not microphone
  recognition accuracy, Windows permission dialogs, or physical hot-plug timing.
- The e-puck world uses kinematic mode. The navigation tests are simulation
  evidence, not a claim of full dynamics validation or physical-robot readiness.
- Raw gesture video is intentionally absent. The included blurred MP4 is ready
  to watch. Replay/video builders need a separately supplied consented source.
- Development package rebuilding requires original external academic files and
  evidence runs; clients do not need that workflow to run the project.

## Client handoff

Extract the final ZIP, open its root in Codex, and ask: “Read AGENTS.md, set up
this project on this laptop, verify the available microphone and camera, and
launch the live simulation.” Codex should report physical checks still requiring
the user's spoken commands and gestures honestly.
