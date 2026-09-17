# Selected verification evidence

This folder contains non-identifying technical evidence selected from the full
development alidation_runs directory. The full transient run history is not
required for submission.

- suite_summaries/: baseline, transcript, navigation, safety, rendered, and
  final enlarged-robot suite results.
- uns/enlarged_robot_showcase/: final rendered all-changes run, excluding the
  intermediate raw movie because the finished video is under demo/.
- uns/enlarged_robot_navigation/: rendered S-to-A visibility/navigation run.
- uns/voice_stop/, uns/head_shake/, and uns/blocked_corridor/: final
  rendered safety evidence.
- uns/post_dashboard_baseline/: passing Docker baseline after dashboard and
  Docker shared-memory hardening.
- uns/self_contained_asset_baseline/: fresh passing Docker baseline after
  packaging the Webots R2025a resources locally.
- uns/voice_destination_override/: passing Docker proof that START remains
  stationary and a microphone destination command replaces an active route
  after nod confirmation.
- uns/explicit_voice_camera_mode/: passing Docker proof of stationary START,
  Voice-to-Camera gesture handoff, Camera-to-Voice mid-route override, and the
  confirming Voice-to-Camera handoff before arrival at B.
- uns/final_voice_camera_vosk_regression/: final passing Webots regression
  from the same code that explicitly enables Vosk word-confidence output.
- uns/startup_motor_lock_regression/: passing post-fix evidence that the
  controller begins in IDLE, START is activation-only, and a separate
  destination plus nod is required before movement.
- uns/gesture_video_control/: passing rendered run driven by the exact
  production-classified gesture-video manifest; the intermediate raw movie is
  excluded because the synchronized professor copy is under demo/.
- gesture/: technical analysis of the supplied gesture clip; no frames or
  landmarks are retained, plus the consented derived-dashboard report. The raw
  source clip is not packaged.
- device_readiness/: non-recording device-readiness and microphone callback
  pipeline reports; no audio is stored.
- client_audit/: fresh Windows environment installation/test log and latest
  complete Docker regression log. Physical client devices remain unverified.