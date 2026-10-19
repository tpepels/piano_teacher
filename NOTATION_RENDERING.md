# Piano Teacher — native Godot notation (Phase 1)

## Current decision (2026-10-19)

Continue the existing **native Godot notation engine** in
`godot/score_native_notation.gd`. Do not replace it with a different
Verovio rendering architecture. Native Godot lays out the continuous score using the backend's
semantic `/score/model` and draws **genuine Verovio glyph shapes**
from the installed Leipzig/Bravura font. Godot must not approximate clefs,
noteheads, rests, flags, dots, accidentals or time-signature digits with
custom polygons, arcs, circles, or UI fonts.

The architecture is:
- Python `notation_symbols.native_glyphs()` extracts individual original
  Verovio glyph SVG paths, bounds and font-space origins.
- `/score/layout` carries that glyph manifest separately from the source
  page geometry.
- `godot/score_verovio_glyphs.gd` imports each glyph only once as a native
  `ImageTexture`, preserving its original silhouette and origin.
- `godot/score_native_notation.gd` positions these genuine glyph assets on
  the musical-time axis using Godot draw calls. The staff rules, stems,
  beams and ties are native structural lines; their spacing stays native.
  **No full Verovio page image** is used in native mode. The musical
clock, not Verovio page geometry, owns every horizontal position.

The original user-visible switch is restored:
```bash
PIANO_TEACHER_NATIVE_NOTATION=1 ./run.sh
```

The existing raster score remains the default **for now**, and is a
whole-passage fallback when `Geometry.supported(model)` or
`required_density` rejects a passage. We have not yet demonstrated that
every user MIDI is supported by the native glyph renderer.

`PIANO_TEACHER_EXACT_VEROVIO_GRID=1` is a **separate raster prototype**
and is disabled by default. It is not the workstream for this phase and
must not run when native notation is selected.

## Phase 1: continuous, deterministic movement

- `score_timeline.gd` owns `x(beat) = beat * pixels_per_beat`.
- `VisualTransportClock` follows the authoritative Python music clock.
- The fixed playhead stays at 42% of the viewport, at all supported BPMs.
- The selected starting measure is an absolute beat offset.
- Negative count-in beats share the same coordinate system. No different
  travel speed between lead-in and the first note.
- `ScoreNativeNotation` must use this same transform for every note,
  barline, rest, beam and tie. No per-note scroll easing.
- Determine the common density once on passage load. Unsupported
  extremely close attacks must produce an explicit fallback rather than
  change scroll speed halfway through a bar.

### Implemented in this increment

- The original native launch switch is enabled again.
- Replaced hand-drawn noteheads, clefs, rests, accidentals, flags, dots and
  meter numerals with separately cached **Verovio font artwork**.
- The glyph atlas is mandatory. Missing/unparseable glyph data triggers
  full-passage fallback instead of rendering imitated shapes.
- The user MIDI screenshot tests require the actual native renderer to be
  active and retain the authentic glyph cache during count-in and playback.
- `ScoreNativeNotation` indexes measures and sorts note events once.
- Grand-staff vertical fitting and chord offsets are cached for a given
  viewport height, instead of rescanning the entire piece every frame.
- Offscreen noteheads are culled with a binary search in beat order.
- Beam work is culled to groups crossing the visible viewport.
- Tie connectivity is computed when a lesson loads, not every draw.
- Engineering labels on the native score are hidden by default;
  `PIANO_TEACHER_NATIVE_DIAGNOSTICS=1` enables them.
- The phase C unit test checks count-in and beat positions at 40, 80,
  and 120 BPM, plus viewport culling and cached staff geometry.
- The graphical MIDI test can capture the native rendering of Ala
  using `scripts/check_user_midi_desktop.py --native --only Ala`.

### Reopening a piece: versioned preprocessing cache

Imported MIDI/MusicXML data and validated Verovio score layouts are stored
under `$XDG_DATA_HOME/piano-teacher/preprocessed/` (or
`~/.local/share/piano-teacher/preprocessed/`). Rendered score PNGs are
reused at the same requested resolution. Entries are keyed by source SHA-256,
cache version, selected curriculum stage, notes, hand, first/last measure,
and tempo; changing a file or switching exercises cannot silently reuse
another exercise's engraving. The cache is bounded to 256 MiB and evicts
oldest artifacts when a new engraving is generated.

`piano_teacher/preprocessing_cache.py:CACHE_VERSION` is the explicit
preprocessing-version switch. Increment it if the score importer, exercise
generator or Verovio engraving algorithm changes. Cache files are
compressed JSON or PNG, never deserialized Python objects; corruption
or cache permission failures trigger a fresh computation.
Use `PIANO_TEACHER_DISABLE_CACHE=1 ./run.sh` to bypass it for diagnostics.

The native Verovio glyph atlas is currently delivered via `/score/layout`
and cached in Godot after its first successful import. The semantic model
does not load into native notation before those genuine glyph textures are
available, preventing a false "font atlas is not loaded" fallback.

### Still to do

- Confirm the CI graphical native MIDI capture and fix any failure.
- Test all seven imported real MIDI files, including explicit fallback
  reasons for unsupported notation and hand changes.
- Profile CPU/frame pacing on the actual Arch Linux laptop and MIDI keyboard.
- Compare glyph placement, stem attachment, header clearance,
  tuplet labels and tied-note geometry against Verovio screenshots.
- Improve visual notation details without changing the working time axis.
- Long-term: fetch the cached glyph atlas separately from individual page
  layout responses to avoid sending the full font manifest each lesson.
- Make native mode the default only after end-to-end acceptance on the
  provided MIDI corpus. No claim of completion until then.

## Acceptance

1. Onset position: for any event, its screen X equals
   `0.42 * viewport_width + (event_beat - play_from_beat - clock_beat)
   * pixels_per_beat`, within 2 px.
2. No speed change at beat zero, meter boundaries, pause/resume, seek,
   Retry, hand change or Listen.
3. A long score renders only events near the viewport. Frame work does
   not grow linearly with all notes in the file.
4. The native score always shows both five-line staves (inactive hand
   dimmed, never removed), with source-accurate clefs and meters.
5. Unsupported rhythms use a complete, explicit fallback; a rejected
   model never leaves stale notes on screen.
6. The seven real MIDI fixtures remain unchanged, with screenshots and
   numeric regression evidence checked before changing defaults.
