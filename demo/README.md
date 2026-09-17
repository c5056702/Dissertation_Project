# Submission demonstration

Share `head_gesture_video_controlled_robot.mp4` to demonstrate that the video-derived gestures control the robot. It is a synchronized 33.16-second H.264, 1280 x 720, 25 fps recording with 829 frames.

- Input: the production classifier processes a consented derivative sequence cut from `tilt_gesture.mp4`.
- Detected sequence: `TILT_LEFT`, `NOD`, `TILT_LEFT`, `NOD`, `TILT_RIGHT`, `NOD`, `SHAKE`.
- Controller result: finish `S_A_SHORT`, wait at A, finish `GRAPH_A_C_SHORTEST`, wait at C, start `GRAPH_C_B_ALTERNATIVE`, then interrupt the third route with a shake in `STOPPED`.
- Layout: the gesture dashboard is on the left and the actual matching Webots recording is on the right, aligned to the same timestamps.
- Guidance: the dashboard identifies `MODE: VOICE` or `MODE: CAMERA` and displays the valid `NEXT STEP` for the current state.
- Privacy: the subject's face is persistently blurred throughout the saved presentation; the detected gesture labels remain visible. The raw source clip is not packaged.
- Voice: text-only `start A`, `go to C`, and `go to B` fixtures; no microphone audio.
- SHA-256: `7D699F80EC7955AAFFA6423DB2E95C95C83D0F5BA89B5E771D54565024C6E7F0`.

This is the only MP4 included in the submission ZIP. Its contact sheet, thumbnail, and final stop frame are derived from the same blurred copy.
