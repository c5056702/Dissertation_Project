# Submission package contents

This package is the self-contained submission copy of the multimodal Webots
e-puck waypoint-navigation prototype.

## Included

- `AGENTS.md`: client-machine setup and verification instructions for Codex.
- `tools/setup_client.py`: Python 3.12 environment creation, integrity check,
  dependency checks, and tests.
- `CODE_EXPLANATION.md` and `CLIENT_READINESS_AUDIT.md`: code guide and audit.

- The single active Webots world: `worlds/epuck_waypoint_navigation.wbt`.
- The complete `epuck_waypoint_controller` source.
- Local voice and gesture dependencies in `requirements.txt`.
- The offline Vosk English model.
- Docker, Windows live-launch, live-dashboard, and consented replay tools.
- Local official Webots R2025a e-puck and appearance resources required by the
  world, avoiding runtime asset downloads.
- All current offline tests.
- `README.md`, `instructions.md`, `plan.md`, the project-change checklist, and
  the submission guide.
- The two academic DOCX documents and the approved changes CSV.
- Selected non-identifying test summaries, results, logs, and screenshots.
- The latest synchronized gesture-controlled robot demonstration with the
  subject's face blurred, plus blurred previews.
- `SHA256SUMS.txt`, containing an integrity hash for every other packaged file.

## Deliberately excluded

- The unrelated legacy Toyota world, controller, libraries, plugins, and PROTO
  assets.
- Webots `.wbproj` project-state files and old world thumbnails.
- `.venv`, Python caches, and compiled bytecode.
- The full `validation_runs` working directory.
- Intermediate and superseded recordings.
- Raw participant audio, video, frames, or face landmarks.

## Main entry points

- Detailed usage: `instructions.md`.
- Quick overview: `README.md`.
- Live launch: `tools/run_live.py`.
- Consented clip/text replay: `tools/run_trace_demo.py`.
- Docker validation: `tools/run_docker_validation.ps1`.
- Main world: `worlds/epuck_waypoint_navigation.wbt`.
- Primary gesture-controlled video: `demo/head_gesture_video_controlled_robot.mp4`.
- The package deliberately contains no other MP4 files.
