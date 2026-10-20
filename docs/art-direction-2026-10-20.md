# Score-first art direction

The references are `moodboard/moodboard.png` and its five detail boards.
Their forest depth, ivory-on-dark notation, serif music titles, quiet supporting
type and mint action hierarchy inform the application. No board thumbnails or
screenshots were extracted, enlarged or used as application assets.

The visual thesis is a softly lit forest rehearsal stage: the grand staff is
the main workspace; lesson context is a compact header; feedback stays with
the music; Retry, Play/Pause and Listen are the routine controls. Navigation
and practice options have their own quieter workspace.

## Composition and interaction

- A single header replaces the separate navigation and metadata rows. The
  desktop score stage occupies about 67% of the viewport height. A hand ribbon
  sits inside the stage without shifting notation between transport phases.
- Larger authentic Verovio fragments, a genuine Verovio font brace and a
  restrained strike light connect the grand staff. The measure progress rail
  remains visible above the native canvas. One global beat scale still drives
  every timed event. Exceptionally dense source segments keep the previous
  compact ink size, selected once at load time within the existing scale limit.
- Physical transport keys have distinct icons, shortcut keycaps and finite
  hover/press transitions. Earned streak and coaching animations sleep at rest.
- `native_score_feedback.gd` separates assessment presentation from notation.
  It projects exact source IDs onto the compositor's painted noteheads rather
  than legacy raster coordinates. Preview and Listen clear assessed effects;
  polling cannot replay a physical MIDI reward.
  Native mode keeps coaching feedback on the music rather than showing a card
  over the lower staff when the hint keyboard is open.
- The library uses readable music shelves. Lesson progression and practice
  choices share a responsive view. Settings use bounded form rows in a two-column
  desktop arrangement and a scrolling single column on small screens.
- The backdrop is generated from broad canopy light and quiet silhouettes.
  Beat lighting follows the existing transport; there is no ambient timer or
  replacement clock. No new external art or font dependency was introduced.

## Full-resolution review

Run the actual application, backend and real Ala MIDI with:

```sh
rtk proxy env PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python scripts/review_art_direction.py \
    --render --output /tmp/piano-art-review
```

The review captures ready, playing, paused, library, lesson path and settings at
1920×1080 and 800×600. It asserts native readiness, visible noteheads, matching
asset/model revisions, acknowledged actions, physical PNG dimensions and usable
control geometry. The server-free pytest fixture separately checks production
layout, captions and settings-control proportions.

Full-resolution inspection found and corrected settings captions wrapping into
single-letter columns and a progress rail escaping above secondary screens.
Screens were recaptured after those fixes; source images are retained at their
original resolution:

- [Practice, desktop](evidence/art-direction-2026-10-20/practice-desktop.png)
- [Practice, compact](evidence/art-direction-2026-10-20/practice-compact.png)
- [Library](evidence/art-direction-2026-10-20/library-desktop.png)
- [Lesson path](evidence/art-direction-2026-10-20/lesson-path-desktop.png)
- [Settings](evidence/art-direction-2026-10-20/settings-desktop.png)
- [Native chord lesson](evidence/art-direction-2026-10-20/native-chord-lesson.png)
- [Capture evidence](evidence/art-direction-2026-10-20/capture-summary.json)

## Verification

The complete 887-test pytest collection was run with
`PIANO_TEACHER_NATIVE_NOTATION=1` in two serial batches: the long instructional
MIDI journey alone, then the remaining collection. Result: **886 passed,
1 skipped, 0 failures**. The skip requires an unavailable system SoundFont and
FluidSynth. This includes the actual Godot/native application, Ala measure 9
curriculum variants, Peace Piece's short tied attacks, source-fidelity checks,
and the existing MIDI learning/Listen/Perform journeys. The instructional
journey completed 36 rendered frames, all six clean full-passage takes through
240 BPM, the original chord variant, Listen audio, all-missed Perform and saved
trouble review without false mastery.

`scripts/check_godot.sh` passed parser, exact-score-spacing and responsive
checks at 1536×960, 1280×800, 1024×768 and 800×600. A final focused run passed
25 fragment, spacing/chord, barline and art-direction checks. All 12 actual
application capture views passed native readiness/revision and geometry checks.

The previously failing legacy staff-pixel fixture now derives unobstructed
rail samples from the original source PNG. Preserved ivory glyph columns are
excluded independently of the rendered frame. All 180 checks, the original
`.97` white threshold and `.98` active-rail fraction remain, with an additional
minimum-coverage assertion. The offline fixture also avoids issuing HTTP calls.

- [Test results](evidence/art-direction-2026-10-20/test-summary.json)
- [MIDI learner results](evidence/art-direction-2026-10-20/midi-journey-summary.json)
