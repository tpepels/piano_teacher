# P1 — Guided Learn and contextual keyboard

Baseline: `7670eb5`; P0 evidence/plan committed as `151d7d8`.

## Working student path

Opening an imported MIDI from the library enters **Learn notes**. Python selects
one or two source measures from the current generated variant and waits for
fresh attacks at each note/chord. Musical time does not advance the target.
Wrong notes and a three-second hesitation reveal a compact keyboard with exact
pitch/octave labels, expected-key triangles and separate heard-key rings.
Persistent hints are optional. Green success and amber assisted success remain
distinct; neither earns timed clean-run credit.

The same active variant supplies guided targets, source-stable IDs and real
engraving. Chords require fresh pitches physically down together within 250 ms.
Repeated pitches require release and another attack; held note-ons do not count
again. Releases during rendering and delayed callbacks are handled without
advancing obsolete targets. Pause/Resume, Stop, Retry, hand/stage changes,
disconnected input and stale score acknowledgements are covered.

**Try rhythm** restores the full active variant, waits for its score revision
and begins the existing timed count-in. Direct legacy timed API use is retained.
The new controls use the existing dark practice screen; no catalogue or fixed
exercise content was introduced.

## Verification

- Full local suite: **292 passed in 36.42 seconds**, fresh root verification.
- Real Godot parser: pass.
- Independent P1 review: 47 controller/backend/UI/keyboard checks passed before
  the final two loading-event regressions; reported held-key issues were fixed
  with red/green tests.
- Actual imported-MIDI learner journey: **seven rendered frames**, ordinary UI
  controls and HTTP polling, real Mido messages through `PracticeEngine._receive`.
  Wrong pitch → precise keyboard → fresh repeated chords → assisted completion
  → Try rhythm → moving Practice → Stop; zero mastery.
- Compact journey: **seven rendered frames**, 800×600 requested and 800×526 actual
  desktop canvas. Hints retained 140 px of score height, at least 30 unoccluded
  notehead pixels and all three highlighted keys; primary/Stop controls fit.
- Standalone keyboard: actual pixels and geometry at 800×600, 1024×768 and
  1536×960, including widely separated hands. It cannot submit student answers.
- Sensitivity check: the real journey failed when wrong-note hint processing
  was temporarily disabled in its test process. No mutation was retained.

Artifacts:

- `/tmp/piano-teaching-p1/`: normal desktop learner journey, JSON state, MIDI
  journal, PNGs and logs.
- `/tmp/piano-teaching-p1-compact/`: compact learner journey and clean shutdown.
- `/tmp/piano-teaching-p1-keyboard/`: chord/wide-register keyboard captures.

Commands: `python -m pytest -q`, `./scripts/check_godot.sh`,
`python scripts/smoke_teaching_godot.py --output-dir /tmp/piano-teaching-p1`,
and the same script with `--resolution 800x600`.

## Deliberate remaining work

P2 adds instructional recovery and recurring-trouble guidance. P3 adds audible
Listen and uninterrupted Perform. P4 refines the pause/HUD experience and note
feedback readability; P5 handles saved trouble spots and natural guided-unit
progression. Guided Learn currently teaches the selected short fragment before
full-passage rhythm practice; automatic successive ideas belong to P5.

Physical USB instruments, real speaker audibility, MIDI/audio latency and pedal
behavior remain pending target-machine acceptance. The port's closed flag is
checked during state updates; device-name discovery still follows the existing
polling lifecycle. Software-generated MIDI/pixels do not establish hardware
acceptance.
