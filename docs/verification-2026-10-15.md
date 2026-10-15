# Local verification — 2026-10-15

Implementation: `53659ad` on `fix/practice-experience`, based on latest main
`5cb31c46f39f6fd96d126acf5f47d8b3d9dde29b`. Main was fetched again before finishing;
it had not changed. Nothing has been pushed to the shared branch.

Software playback and UI were checked with the real Godot 4.7.2 X11/OpenGL
desktop renderer on Linux. Physical MIDI and speaker acceptance remain open.

## Results

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q` | **207 passed**, 8.51 seconds |
| `./scripts/check_godot.sh` | Pass, real Godot parser |
| `python scripts/smoke_phase0.py` | Pass: import, engraving, PNG, HTTP clock, ungraded preview |
| `python scripts/smoke_godot.py` | Pass: real practice scene, PNG, moving count-in/playback, clicks, completion |
| `python scripts/smoke_adaptive_godot.py` | Pass: three clean synthetic MIDI takes, mastery, skeleton→outline, revision acknowledgement, persistence |
| `python scripts/check_generated_lesson.py <actual MIDI>` | Pass: opening skeleton and original variants match required notes |
| `python scripts/check_generated_lesson.py --complete-song <actual MIDI>` | Pass: all **2,346** source notes, 2,679 engraved glyphs including tied continuations, **24 pages** |
| `python scripts/check_visible_playback.py --output-dir /tmp/piano-verified-visible` | Pass: **36 actual rendered samples**, 30/40/80/120 BPM |
| `python scripts/check_desktop_ui.py <actual MIDI> --output-dir /tmp/piano-release-ui` | Pass: normal `./run.sh`, every screen, tempo/metronome/MIDI preview controls, three window sizes; no runtime errors |
| Desktop `tests/godot/score_motion.gd` with 40-bar real engraving | Pass: rendered count-in/playback and system/page join captures |
| `git diff --check` | Pass |

The actual MIDI is the user's Merry-Go-Round-of-Life file. Checks use isolated
XDG progress/preferences; they do not overwrite source files or the user's
existing database. Tests do not require a connected piano.

## Visible motion evidence

The live check retains the application's ordinary HTTP polling and frame
processing. It follows the **same note ID** across count-in and playback,
checks actual contrasting note pixels, verifies a fixed timing line and stable
scale, pauses/resumes, restarts, and completes an ungraded preview naturally.

| BPM | Same note x, first→last playback sample | Timing-line drift | Paused-note drift | Minimum detected ink pixels |
|---|---|---|---|---|
| 30 | 983.7→484.6 | <0.001 px | 0 px | 76 |
| 40 | 916.3→484.3 | <0.001 px | 0 px | 83 |
| 80 | 871.3→483.7 | <0.001 px | 0 px | 83 |
| 120 | 865.6→483.2 | <0.001 px | 0 px | 83 |

The first x sample is during count-in; the last is during playback. Measurements
are render-target pixels, including the actual window/viewport transform.

Local artifacts:

- `/tmp/piano-verified-visible/`: PNG frames, samples.json and backend/Godot logs.
- `/tmp/piano-release-ui/`: home, library, practice, lesson, settings and MIDI
  menu captures; 1536×960, 1024×768 and 800×600 layout checks.
- `/tmp/piano-final-multipage/`: desktop frames at musical system/page joins,
  samples and source raster/geometry fixtures.

These temporary artifacts can be regenerated with the committed check scripts.

## Changes verified

- Correct alpha-aware cropping; real Verovio rest events and measured staff
  bounds; exact raster coordinates despite rounded PNG page heights.
- Direct musical projection instead of camera lag/clamps. All score systems
  preload as separate tiles and use one backend-authoritative clock. Feedback
  holds the completed passage still rather than jumping to the beginning.
- Compound rests and tied/fractional note lengths preserve subsequent attack
  times. Source measure boundaries and meter changes reach the production
  renderer. Whole-piece required-note alignment passes with **zero backward
  timing anchors**.
- Consistent interstaff spacing uses the passage's measured requirements.
  All ten staff rails align across normal, held-note, crossed-hand and multi-page
  fixtures. Estimated extra-note feedback uses the same strip interpolation.
- Dark library/practice/lesson/settings, real MIDI activity, saved metronome,
  target tempo, pause/restart and responsive controls. A virtual MIDI Through
  port is never automatically mistaken for a piano; explicit ungraded input is
  available from the MIDI menu.
- MIDI discovery detects missing/closed ports, abandons interrupted assessment,
  preserves reconnection preference and handles discovery/open/close failures.
  Eight hardware-free regression cases cover this lifecycle.
- Curriculum: **1,209→301 stages**, 45 learning sections, 44 boundary bridges and
  a complete original performance. Eleven difficult two-bar units remain. All
  source notes and introductory/ending time are preserved through bar 237,
  beat 712. Three-clean mastery, recovery and target-tempo continuity remain.
- Additive course-version/session migration preserves old mastery and maps the
  saved musical span/hand/stage; changed required notes reset stale clean streaks.

Independent review found the extra-marker interpolation and bass-staff spacing
issues above; both received failing-then-passing real Godot regressions. No
unresolved important review findings remain.

## Remaining acceptance and limitations

Physical speaker audibility, audio/MIDI latency, pedal behavior and a complete
practice session on the student's USB piano remain unverified. Mocked reconnect
tests establish software handling, not a particular instrument driver's behavior.

Curriculum consolidation uses conservative density/chord/rhythm heuristics.
General phrase analysis and learner-specific diagnostic skipping remain future
work. Piano synthesis, fingering, hand corrections and pedal grading are not
implemented. Large complete scores preload all cropped textures and can use
substantial memory; neighboring-system streaming remains a future optimization.
