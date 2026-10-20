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
there are no drawn clefs, flags, beams, ties, etc. The diagnostic marker preview remains opt-in; it is separate from the
canonical native notation view.

A semantic score is fetched asynchronously from `/score/model` whenever
the exercise revision changes. A response from a previous revision is
discarded. The preview continues to use the same transport and playing
controls. There is no new backend service or second time source.

The retired Verovio page camera is retained only for explicitly selected
legacy mode or complete-score fallback. Fitting dense
polyphonic symbols may require a one-time *whole-passsage* global scale
increase or collision indication in Phase C; it must never introduce
between-note speed changes.

Acceptance tests:
`tests/test_phase_b_timeline.py` and
`tests/godot/phase_b_timeline.gd` exercise musical onsets, mixed meters,
negative lead-in, pause, seek, and precise 40/80/120 BPM fixed velocity.

Phase C will use this semantic timeline to draw SMuFL notation in Godot,
preserving Verovio as a fallback until coverage is sufficient.

## Native notation — canonical since 2026-10-20

The production practice score uses `godot/score_native_notation.gd` by default.
`./run.sh` requires **no** renderer environment flag. The former
`PIANO_TEACHER_NATIVE_NOTATION=1` flag remains accepted for existing scripts.
Choose the retired page-renderer explicitly for regression comparisons:

```sh
PIANO_TEACHER_RENDERER=legacy ./run.sh
# Or: ./run.sh --legacy-notation
```

The native renderer consumes the versioned, transport-independent
`/score/model` contract on one fixed quarter-beat axis. All notation glyphs
and compound engraving (including notes, chords, beams, ties, tuplets and
slurs) are source Verovio font outlines or independently extracted genuine
Verovio fragments. Godot owns placement, fixed-speed horizontal motion,
feedback, and non-glyph structural rules. No local per-note timing warp is
allowed. Source glyph failure keeps the **complete** old Verovio score as
an explicit compatibility fallback rather than displaying counterfeit ink.

### Python ownership

| Package / module | Responsibility |
| --- | --- |
| `music.py` | Musical source types and performance identity |
| `importing/pieces.py`, `importing/musicxml.py` | Source MIDI/MusicXML import |
| `notation/musicxml.py` | Pure shared MusicXML barline parsing |
| `notation/lesson.py` | Compile the selected exercise into MusicXML |
| `notation/model.py` | Renderer-independent semantic score contract |
| `notation/assets/runtime.py` | Verovio toolkit and bundled font paths |
| `notation/assets/glyphs.py`, `notes.py`, `chords.py`, `ties.py`, `beams.py`, `tuplets.py`, `slurs.py`, `svg.py` | Native glyph and authentic fragment extraction |
| `rendering/legacy/engraving.py`, `geometry.py`, `spacing.py`, `raster.py` | Retired page renderer and page geometry, preserved for compatibility |
| `application/score_preparation.py` | Stateless preparation of native layout payloads using the existing cache |
| `transport/http.py` | HTTP routes and response/error handling |
| `server.py` | Authoritative practice state, revision and cache invalidation, entry point |

Existing top-level module paths (e.g. `score_model.py`, `lesson_score.py`,
`score.py`) provide thin explicit compatibility imports; internal callers
should use the owning modules. Source imports and score semantics do not
depend on page rendering. Asset runtime does not depend on legacy page
engraving. The original `python -m piano_teacher` and
`python -m piano_teacher.server` entry points remain supported.

### Godot ownership

`godot/notation/shared/view_base.gd` owns the common semantic clock and
transport state, independently inherited by the native renderer and marker-only
diagnostic preview. `godot/notation/native/score_index.gd` indexes events,
chord membership, source beams, ties and slurs without drawing or owning a
transport. `godot/notation/native/barline_layout.gd` derives single, double,
heavy and repeating bar rules from the source semantic boundary. The main
native compositor remains responsible for visible event culling and paint
ordering. Existing exact beat spacing, glyph textures and source geometry are
separate collaborators.

The old page strip is still available solely for unsupported notation,
compatibility checks and legacy-specific diagnostics. This is **not** a plan
to remove Verovio fonts or genuine SVG fragment extraction. Those remain core
dependencies of the native notation engine.

### Verification

The Python suite, `scripts/check_godot.sh`, real MIDI fidelity fixtures,
Godot capture tests and the explicit native-default screenshot check must pass
before merging a source-organisation refactor. Any unsupported notation falls
back to complete original Verovio pages without changing MIDI grading, BPM,
revision identities or cache namespaces.

## Compatibility

Existing endpoints, test fixtures, evaluation, lesson storage, Listen audio,
full-screen interface and Godot renderer remain unchanged in Phase A.

Do not feed layout pixels back into ScoreModel, and do not infer ScoreModel
notes by parsing a rendered page. Renderers consume the model; they do not
define musical truth.
