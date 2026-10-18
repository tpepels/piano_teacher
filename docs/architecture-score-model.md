# Architecture decision A — Semantic ScoreModel (October 2026)

Status: **Phase A implemented; renderer migration NOT started.**

## Why

The legacy practice view derives musical position from Verovio's glyph X
coordinates and then tries to interpolate its camera at each MIDI onset.
That makes short-note scroll speed and count-in spacing depend on typography.
Phase A introduces an explicit data contract separating **what the learner
plays** from **where an engraver chooses to paint it**.

## Single source of truth

```
LearningPlan.active_phrase (the exact exercise variant)
                 │
      build_lesson_score(...)     ← existing deterministic MusicXML compiler
                 │
       +---------+--------------+
       |                        |
       v                        v
ScoreModel v1 (/score/model)   Legacy Verovio renderer (/score/layout, /score.png)
       |                        |
 Future native Godot renderer   Existing Godot score (untouched)
```

The Python grader still consumes `LearningPlan.active_phrase`. Listen, MIDI,
tempo and lesson progression still operate as before. The ScoreModel uses the
**same** source-note identities and the **same** generated notation as the
existing code: it does not re-import MIDI or infer notation from SVGs.

## API contract: GET /score/model

JSON with `schema: "piano-teacher-score-model-v1"` and:

- `revision`: backend score revision.
- `beat_unit`: always `quarter`. All times are floating-point quarter-note
  beats *relative to the selected exercise's beginning*, including pickups.
- `first_bar`, `last_bar`, `duration_beats`.
- `staff_order`: right and left. `active_hand` and `active_note_ids` describe
  the selection; both staves and all semantic symbols remain available.
- `notes`: **source attacks**; IDs, pitch, velocity, onset, actual held
  duration, hand, track, voice, channel, and optional pitch spelling. One event
  per physical note. These correspond one-to-one to the existing MIDI grader.
- `measures`: exact measure boundaries, original meter and clef context.
  Unequal meter and pickup durations stay intact.
- `notation_events`: rendered musical instructions, **not pixel positions**.
  Includes staffs, voices, MIDI pitch and enharmonic spelling, rests, dots,
  tuplets, chords, tie start/stop, displayed durations and absolute beat.
  A note spanning bars has multiple notation events that point to ONE source
  attack ID. Generated rests have stable IDs within an individual response.

**Guaranteed:** Verovio is not imported or invoked by `/score/model`.
The endpoint does not request PNGs, rasterization, SVG layouts, or any
font. It is a pure semantic projection of the active lesson.

**Deliberately excluded:** BPM, scroll velocity, pixel positions, cursor X,
engraving pages, textures, SVG, animation state, MIDI device state, and
network latency. These never belong in an immutable score description.

**Validation:** every source attack must appear as exactly one notation attack;
every notation segment must point to a real source note; MusicXML segment
durations and offset within measures are checked. Corrupt mismatches raise
errors instead of silently producing a plausible but incorrect lesson.

## Phase B — not implemented

Introduce an independent `TransportClock` with exact beat origin and tempo;
on the Godot side, use one user-tunable `pixels_per_beat` and a constant
velocity. The visual position is `x(note) = lead + note.onset_beats *
pixels_per_beat`, and the camera offset follows the same constant directly.

A preliminary collision pass should choose a **fixed scale for the whole
passage** before playback if notation glyphs cannot fit at the desired scale.
It may not accelerate between individual attacks to compensate for spacing.
Count-in must occupy negative beats on the same axis, not be extrapolated
from Verovio's first two noteheads.

Phase C will draw notation from this model using a music font and preserve the
old Verovio path as a fallback until symbol coverage is sufficient.

## Compatibility

Existing endpoints, test fixtures, evaluation, lesson storage, Listen audio,
full-screen interface and Godot renderer remain unchanged in Phase A.

Do not feed layout pixels back into ScoreModel, and do not infer ScoreModel
notes by parsing a rendered page. Renderers consume the model; they do not
define musical truth.
