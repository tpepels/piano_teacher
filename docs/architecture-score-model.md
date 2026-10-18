# Architecture decision A — Semantic ScoreModel (October 2026)

Status: **Phases A and B complete; Phase C native renderer opt-in, fallback retained.**

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

## Phase B — fixed musical timeline implemented as an opt-in diagnostic

The pure `godot/score_timeline.gd` is the mathematical contract. It consumes
`/score/model` directly, never imports Verovio's X positions, and has no
internal timer. The already existing `VisualTransportClock` is the SINGLE
frontend presentation clock; its authoritative snapshots still come from
the Python transport used by the MIDI grader and Listen.

- Constant `DEFAULT_PIXELS_PER_BEAT = 96` (valid range: 24–480).
- `x(note) = onset_beats * pixels_per_beat`, `camera_x =
  (play_from_beat + clock_beat) * pixels_per_beat`.
- Fixed playhead: `screen_x = playhead_x + x(note) - camera_x`.
- Frame velocity: `pixels_per_beat * bpm / 60`, independent of note duration,
  tempo changes in notated XML, and measure boundaries.
- Count-in is one continuous negative-beat interval relative to
  `play_from_beat`, ending exactly at zero without a different bar width.
- Pause, seek, retry and BPM changes come only from authoritative transport
  transitions; this module never seeks sound, grades MIDI or re-times notes.

### Try the prototype

Run after updating the checkout:

```sh
PIANO_TEACHER_TIMELINE_PREVIEW=1 PIANO_TEACHER_PIXELS_PER_BEAT=96 ./run.sh
```

Change only `96` to `72`, `120` or `144` to tune horizontal
density. The preview is an **overlaid diagnostic with simple note markers and
duration bars**. It is deliberately NOT the Phase C sheet music renderer;
there are no drawn clefs, flags, beams, ties, etc. The legacy score remains
the default without the flag. Only the preview's visible score changes.

A semantic score is fetched asynchronously from `/score/model` whenever
the exercise revision changes. A response from a previous revision is
discarded. The preview continues to use the same transport and playing
controls. There is no new backend service or second time source.

The old Verovio camera and count-in logic remain untouched in the default
view until Phase C can draw notation from this timeline. Fitting dense
polyphonic symbols may require a one-time *whole-passsage* global scale
increase or collision indication in Phase C; it must never introduce
between-note speed changes.

Acceptance tests:
`tests/test_phase_b_timeline.py` and
`tests/godot/phase_b_timeline.gd` exercise musical onsets, mixed meters,
negative lead-in, pause, seek, and precise 40/80/120 BPM fixed velocity.

Phase C will use this semantic timeline to draw SMuFL notation in Godot,
preserving Verovio as a fallback until coverage is sufficient.

## Phase C1 — native vector notation is opt-in

The new `godot/score_native_notation.gd` directly consumes
`ScoreModel.notation_events` and the Phase B `ScoreTimeline`.
No Verovio, SVG, raster tile, external music font or page/slice composition
is needed to paint the practice notes in native mode.

Start after a clean pull:

```bash
PIANO_TEACHER_NATIVE_NOTATION=1 PIANO_TEACHER_PIXELS_PER_BEAT=96 ./run.sh
```

Change `96` to test another preferred density. Collision clearance may
choose a larger scale **once for the entire exercise** at load time, never
between notes or at the onset. The timeline, count-in, playhead, and all
notation events use exactly the same musical quarter-beat axis.

Implemented in the first opt-in renderer: two continuously drawn five-line
staves, default G/F and explicit C clefs, clef changes, meter labels,
key-signature indication, voice-aware rests, ledger lines, oval noteheads,
stems, eighth/sixteenth flags, accidentals, dots, chords, ties, and a single
stationary timing line. High/low semantic note extents are used to fit the
grand staff during viewport resizing. The existing HUD remains above the
native score. MIDI/Listen still use the existing Python lesson engine and
its authoritative visual transport.

**C2 additions:** conventional eighth/sixteenth groups are beamed
directly in Godot, with common stem direction, secondary sixteenth beams and
individual hooks. Grouping respects staff, voice, rests and measure boundaries:
quarter-beat groups in regular meters, dotted-quarter groups in 6/8, 9/8 and
12/8. No unsupported meter receives guessed beam groupings. Key signatures
place each accidental at a clef-relative staff step, and seconds in chords
receive local notehead displacements. These are *glyph corrections only*;
none change musical time or the linear scroll camera.

**Remaining limitations:** complex tuplets, 32nd/64th notes, double dots,
cross-staff beams, advanced independent-voice collision/layout, full octave
signs and a polished SMuFL music-font pipeline are not supported yet.
The renderer currently uses native vector primitives for clefs and symbols,
rather than shipping an external binary font. Dense/impossible rhythmic
spacing and unrepresentable symbols still fall back to the full Verovio
engraving. This is not yet a complete MusicXML engraver.

Use the legacy app by omitting `PIANO_TEACHER_NATIVE_NOTATION`. The previous
Phase B marker-only preview is still available separately via
`PIANO_TEACHER_TIMELINE_PREVIEW=1` when native mode is off.

Further C iterations should improve SMuFL typography, automatic cross-voice
collision handling and unsupported expressive notation *before* native mode
is considered as the default. Phase D can attach notehead
feedback to these native semantic coordinates rather than the old SVG map.
This strict separation avoids the earlier regressions in the main GUI.

## Compatibility

Existing endpoints, test fixtures, evaluation, lesson storage, Listen audio,
full-screen interface and Godot renderer remain unchanged in Phase A.

Do not feed layout pixels back into ScoreModel, and do not infer ScoreModel
notes by parsing a rendered page. Renderers consume the model; they do not
define musical truth.
