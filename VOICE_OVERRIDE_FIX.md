# In-motion voice override correction — 11 September 2026

## Confirmed defect

The live controller reused a gesture delivered in the same input poll as a new
voice destination. A coincident nod could immediately confirm B, skipping the
observable stopped/Voice Mode stage. The previous Docker scenario supplied
speech and confirmation together, so it did not prove a separate waiting stage.
No recording of the reported client's failure was available; this is a
reproduced software defect, not proof that the client's microphone is healthy.

## Correction

- A live voice destination discards its coincident non-safety gesture and waits
  for a later gesture. SHAKE still takes priority as a safety stop.
- An in-motion destination stops the navigator, sets Voice Mode, and ends that
  loop iteration before processing confirmation.
- A later nod confirms the destination and switches to Camera Mode. Without
  that nod it stays stopped; a shake cancels the pending destination.
- Deterministic test fixtures may still combine inputs explicitly. The override
  scenario now delays confirmation by two simulation seconds and checks position,
  timing, destination, and Voice-to-Camera mode changes.

## Verification

The new `tests/test_live_override_controller.py` executes the production live
controller loop with fake Webots devices and inputs, rather than ScenarioInput.
It checks commanded motor velocities throughout the pause, delayed confirmation,
mode transitions, no-nod behaviour, and shake cancellation. Restoring the old
coincident-gesture behaviour in memory makes two of these tests fail; all three
pass with the correction. The full Windows suite passes 72 tests.

The Docker full suite passed 38/38 scenarios. The tightened genuine mid-route
test then passed 3/3 repeated runs, each with travel before the interruption,
zero motor targets during the pause, a separate confirmation after two seconds,
Voice-to-Camera handoff, and arrival at B. Summary files:
`20260911_164027_853916_all.json` and
`20260911_164339_451358_midroute_destination_change.json`.

The first tightened check failed a 3 cm total-drift limit: Webots showed roughly
3.4 cm of braking displacement. The final checks explicitly distinguish this
from continued movement: both motor targets are zero, total drift is below 5 cm,
and position changes less than 1 mm between the 0.5-second settled sample and
confirmation. This is not a claim of physically instantaneous stopping. Each
packaged run includes `override_checks.json` and the sampled positions.

Real speech and gesture recognition on the client still require a physical test.

## How to use

While moving towards A, keep your head neutral and say GO TO B. Wait until the
dashboard shows the pending B destination in Voice Mode and the robot is stopped.
Then make a fresh nod. The robot should follow the new route to B in Camera Mode.
If it does not, retain the run's technical events and note the dashboard's final
transcription, rejection reason, device status, and calibration status.
