# Handoff verification — 17 October 2026

This continues the regression repair at `600aa72` on `main`. The remote main
branch had no newer changes when work began. The existing dark design and
consolidated teaching curriculum were retained and audited against the handoff.

## Confirmed problems and changes

| Problem | Cause | Change |
|---|---|---|
| Zoom changed on Start and Pause | The hand ribbon and caption labels entered/left container layout with the transport phase. The hide-on-play ribbon dates to `7e13269`. | Keep the desktop ribbon's space stable; reserve one feedback line and two instruction lines using actual font metrics. Compact windows continue to omit the ribbon. Full text remains available in tooltips. |
| Clefs/meters clipped and the lower staff crossed the progress rail | Scaling fitted staff rules rather than complete raster ink. | Measure the cropped strip's actual ink and fit it uniformly above the rail. Raster notes, feedback and timing coordinates share that transform. |
| Dense expressive MIDI forced extreme horizontal spacing | Tiny release gaps became additional rests; irregular durations became ordinary notes tied to microscopic residuals. The duration splitting originated in `53659ad`. | For generated display notation, close gaps of at most 1/64 beat within the same lane and measure. Spell irregular durations as a single nearby note type with an exact duration ratio. Conventional compound and barline ties remain. |
| A failed take could leave two previous clean takes intact | Failure was committed only after feedback. Start/Restart/Stop could discard that pending result. | Immediately persist the broken clean streak. Successful mastery still requires three full target-tempo takes and completion of feedback. |
| Failed imported exercises stopped instead of repeating | The manual-review policy introduced in `0dc95d1` disabled automatic repetition for all failed full takes. | Imported Practice repeats after readable feedback. Existing beginner warm-up review, bounded review and Perform policies remain. |
| Errors spanning adjacent chunks failed to trigger recovery | Assessment considered only isolated canonical two-bar chunks. | Detect five wrong/missed required notes in a rolling two-measure interval, including mixed meter; execute at the existing boundary and retry the completed canonical chunk at 90% tempo. Saved trouble counts describe that retry unit. |
| Recent music was unreachable | Last-opened controls belonged to the superseded Home screen. | Promote the real last-opened catalog entry in Music. Continue restores the saved lesson, hand and tempo without resetting them through the starting-point picker. |
| Status text and notifications obscured useful content | The input indicator had a fixed width; the in-score phase capsule covered treble notes. | Measure status text with the actual font and suppress the capsule once notation loads. Guidance remains in captions and count-in lights. |

Canonical source notes, pitches, IDs, attack times and assessed releases are
unchanged by the display cleanup. The Python transport remains authoritative;
no camera easing or presentation-tempo correction was added.

## Rendered playback and notation evidence

`scripts/check_visible_playback.py` now starts the ordinary `./run.sh` launcher
with isolated preferences/progress and no MIDI device. It presses the actual
Play, Pause and Resume controls, uses normal HTTP polling, and captures rendered
pixels. Its regression is part of pytest when a graphical desktop is available.

The four-tempo run retained 44 PNG frames spanning count-in, beat zero, playback,
pause, resume and restart. A final silent preview completed without mastery.
Measurements from the inspected desktop run:

| BPM | Horizontal pixels per beat | Largest projected downbeat error | Scale change across phases | Paused movement |
|---|---:|---:|---:|---:|
| 30 | 381.93 | 0.191 px | 0 px | 0 px |
| 40 | 331.75 | 0.001 px | 0 px | 0 px |
| 80 | 187.61 | 0.001 px | 0 px | 0 px |
| 120 | 138.13 | 0.233 px | 0 px | 0 px |

Spatial beat density can differ between tempo-specific engravings. Within each
take it stays constant. The maximum measured timing-line displacement was below
0.001 pixel in canvas geometry; raster-ink checks independently require actual
visible notehead pixels. These are software display measurements, not physical
speaker/USB latency measurements.

The supplied dense Ala passage retains all 53 original attacks and one genuine
tie continuation at all four tempos. Final Godot spacing is approximately
352–616 pixels per beat at the headless fixture viewport, rather than the
approximately 35,700-pixel requirement documented in the preceding repair.
Each full-passage minimum/maximum differs by less than 0.3%, including rests and
system joins. Desktop captures separately show the complete clefs, key, meter,
notes and ties. The earlier report's dense-display limitation is resolved for
this reproduced passage; it is not a universal readability claim for every MIDI.

The full Merry-Go-Round source still produces 45 learning sections, 44 connecting
passages and a complete performance, totaling 301 stages instead of 1,209. Its
complete generated score passes alignment for all 2,346 required notes across
60 rendered pages. The source ending remains intact. Existing tests cover saved
progress, hand-specific variants, three clean full takes, partial-retry and
preview exclusions, actual input callbacks, guided help and tempo restoration.

## Local artifacts and validation

Evidence is retained under `playtest-results/handoff-verification/` and excluded
from Git alongside other diagnostic captures. It includes baseline and repaired
playback frames, JSON positions, dense-passage captures and spacing logs,
normal-launcher Music/Path/Settings/practice captures, and verification logs.

- Full suite: **738 passed, 1 skipped in 300.93 seconds**. The skip needs an
  optional system SF2 and libfluidsynth.
- Final UI follow-ups: **21 passed** for practice interactions and library
  continuation, including phase-capsule suppression and failed-request queue
  cleanup. The latter regression was confirmed failing at all four sizes
  before its fix.
- `./scripts/check_godot.sh`: passed, including layout at 1536×960, 1280×800,
  1024×768 and 800×600.
- `smoke_phase0.py`, `smoke_godot.py` and `smoke_adaptive_godot.py`: passed.
- `check_generated_lesson.py`: passed for both the first imported passage and
  the complete original composition.
- Final no-MIDI desktop playback: **44 samples passed at 30/40/80/120 BPM**.
  The strengthened detector rejects thick staff lines and crossed timing rules
  before accepting compact notehead ink.
- Final normal-launcher imported-piece review: **13 desktop captures passed**,
  including the compact Music Continue action restoring the saved hand/tempo.
- Final learning UI review: **18 rendered frames passed**, including keyboard
  hints, input activity, Listen, pause choices and fullscreen. The input adapter
  is simulated; the UI, backend callbacks and generated notation are real.
- `playtest.py --preflight`: **49 passed**, opened the desktop application, and exited
  cleanly with its diagnostic report and ZIP after a short idle session. It
  recorded no connected graded performance and is not hardware acceptance.
  Its 30 FPS idle cap explains the report's 60 FPS review warning; the worst
  startup frame was 149.6 ms. Active motion is checked separately above.

## Remaining acceptance

Physical USB MIDI behavior, reconnects on the user's instrument, count-in speaker
audibility and end-to-end acoustic latency still need the user hardware session.
Automated input and audio checks do not substitute for those observations.

Use the existing diagnostic entry point:

```bash
.venv/bin/python playtest.py --preflight
```

Its preflight now includes full notation bounds and dense-MIDI display regression
tests as well as the prior clock, playhead, motion, drawer and MIDI checks.
