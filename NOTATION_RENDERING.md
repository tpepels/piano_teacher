# Verovio engraving, Godot game timeline

## Decision (2026-10-18)

The hand-drawn Phase C notation experiment (`godot/score_native_notation.gd`)
is retired from the normal user-facing launch. It is not the basis for the
production score. `PIANO_TEACHER_NATIVE_NOTATION=1` now falls back to the
existing Verovio-engraved display; the old prototype is available *only*
with `PIANO_TEACHER_NATIVE_NOTATION_EXPERIMENTAL=1` for diagnostics.

**Verovio owns the music alphabet. Godot owns the game presentation.**
Do not attempt to implement a substitute SMuFL/font/notation engine in
GDScript. Conversely, do not treat Verovio's printed page arrangement as
the moving practice interface.

## Responsibilities

- **Source and timing, Python:** MusicXML/MIDI import, musical structure,
  meter/clef/key changes, source-note identities and rhythmic timestamps;
  use the same transport beat as scoring, Listen and count-in.
- **Engraving, Verovio:** render real musical glyphs and their relationships:
  noteheads, stems, beams, flags, rests, clefs, key/time signatures,
  accidentals, ledger lines, tuplets, dots, ties, slurs, articulations and
  barlines. Preserve context and source IDs. Keep SVG vector geometry or
  transparently rasterize once at sufficient native resolution.
- **Continuous layout, a new adapter:** produce a logical unbroken grand
  staff and a render manifest mapping each engraved ink group to a musical
  beat, staff and source IDs. Keep exactly one X scale in musical time:
  `x(beat) = beat * pixels_per_beat`. Position glyphs **by translation**,
  preserving their Verovio geometry and proportions. Do not resize raster
  strips, stretch symbols, use interpolated speed profiles, splice through
  ink, or infer missing noteheads.
- **Presentation, Godot:** move a cached static score scene using the
  transport beat; fixed playhead at 42% of viewport; keep both staves,
  dim inactive hand without erasing it, render count-in before beat zero,
  display note-attached feedback above ink, draw atmospheric background
  and subtle particles separately. Never make effects alter the score clock.

## Layout adapter requirements

The adapter must not naïvely split a Verovio system into individual note
sprites. A beam, tie, slur, tuplet bracket, accidental or articulation may
belong to several notes or cross an event boundary. It must preserve these
as complete engraved groups, with their source identities and bounding
boxes. Reserve collision-clearance within the fixed beat grid; if a piece
cannot be represented without ink overlap at the requested density,
increase *the common density* before starting playback, or show the
existing Verovio display with an explicit diagnostic. Never vary velocity
between two notes to compensate for insufficient room.

The existing backend components are useful: `score.py` generates authentic
Verovio SVG, `score_geometry.py` extracts note identities and timings,
`score_model.py` supplies semantic beats, and `score_timeline.gd` already
provides a fixed temporal X mapping. The existing `score_strip.gd`
raster-warping path is a **temporary fallback**, not a new font/layout model.

The first deliverable is a **vertical slice** through one simple 3/4 piano
piece at 44 BPM: full Verovio noteheads and stems, opening clefs and meter,
aligned to `score_timeline.gd` with a *constant* 96 px/beat, including
count-in. Then extend to chords, rests, flags and beams; then ties,
tuplets, grace notes and imported notation with mid-piece changes.
A partial adapter must use Verovio fallback for the unsupported *entire
passage* rather than mix hand-drawn and engraved symbols.

## Visual contract

- Single connected grand staff across the viewport, visually dominant
  with generous clef/ledger clearance and high-resolution sharp symbols.
- No printed page margins, multi-system pagination, cropped staff ends,
  duplicated opening clefs on system joins, or vertical line breaks.
- Fixed, bright playhead. The score advances **linearly** according to
  the backend quarter-beat clock at every BPM. Tempo change only affects
  pixels/second, not pixels/beat or glyph scale.
- Only clean measure numbers and sparse navigational guidance.
  Never display `PHASE B`, `NATIVE SCORE`, raw density metrics,
  `3.0 / 4.0` debugging text or developer state labels in practice UI.
- During count-in, show empty bars/beat markers to the left of the first
  genuine engraved note; **do not** display synthetic full-clef systems.
- MIDI visual events must use the Verovio source-note ID and the same
  logical beat mapping. A missed chord note highlights only the missed
  notehead. Listen/preview animations cannot claim a graded success.

## Acceptance (must be measured, not inferred)

1. Compare native Verovio SVG against what Godot displays for a corpus
   containing accidentals, dots, rests, beams, tuplets and mid-piece
   signatures. Every supported symbol must remain recognizably identical.
2. Record x-position at the fixed playhead at beats 0, 1, 2, 3, etc.,
   and during negative count-in, 40 / 80 / 120 BPM. Error budget: <= 2 px
   against `playhead_x + (event_beat - clock_beat) * pixels_per_beat`.
3. Hold, resume, retry, seek, and change hand. The same source note keeps
   the same engraved glyph and lands on the same clock beat; no camera jump.
4. Verify on a 1536x960 viewport and smaller supported sizes that the
   staff is large, notes are legible and both hands remain visible.
5. Measure steady-play CPU and tile uploads. Do not regenerate or upload
   Verovio notation every frame; only shift cached resources and animate
   lightweight feedback.
6. Any unsupported group or mismatch must revert to the complete Verovio
   fallback, log a precise reason, and avoid silently dropping notes.

## Developer commands

- `./run.sh`: production Verovio fallback.
- `PIANO_TEACHER_NATIVE_NOTATION=1 ./run.sh`: deprecated alias; still
  displays Verovio fallback and prints a warning.
- `PIANO_TEACHER_NATIVE_NOTATION_EXPERIMENTAL=1 ./run.sh`: old Phase C
  handwritten diagnostic ONLY. Do not use for acceptance.
- `PIANO_TEACHER_TIMELINE_PREVIEW=1 ./run.sh`: non-engraved timing diagnostic;
  not a presentation mode.

## Phase 1 implementation status (2026-10-19)

### Implemented: strict clock-locked camera over existing Verovio ink

`godot/score_beat_camera.gd` measures the *actual* projected note/rest
anchors returned by `ScoreStrip`. Only if every distinct onset belongs to
one affine `x = origin + beat * source_pixels_per_beat` time axis within
2 native raster pixels may the app use the new camera. The camera then
moves the existing cached tiles directly from the authoritative Python
clock beat (including count-in and seek offsets), at a fixed 42% playhead.
It changes only the parent canvas translation, never notes or their timing.
No easing, per-event interpolation, mid-measure speed correction, or BPM-
dependent image scaling is applied.

For unsupported/not-yet-aligned scores (including extreme ornament
intervals, duplicate onsets with different engraved positions and natural
non-proportional single-system Verovio layouts), the prior camera is used
for the complete passage. The source score is not partially translated.
The per-passage reason is recorded in `score_beat_grid` and exported by
the real desktop MIDI diagnostics. Validate with
`tests/godot/score_beat_camera.gd` and the actual source SVG/Godot corpus.

### Not yet implemented: source-glyph-group re-layout

The initial camera still receives tiles prepared by the existing
`ScoreStrip` raster pipeline. This means Verovio is still the engraving
engine, but printed score strips can still contain horizontal bitmap
spacing adjustments and the safety fallback may not achieve uniform speed.

The next Phase 1 increment must extract SVG groups with stable source IDs,
including beam/tie/slur groups that span multiple notes; translate complete
glyph groups against a common time axis without resampling ink; preserve
measure-level clefs/key/time signatures; and compare resulting symbol
pixels against original Verovio. Activate it only after demonstrating
no broken links and constant camera motion on real MIDI, including Ala,
Autumn Leaves and Chopin. Do not report Phase 1 as complete until then.
