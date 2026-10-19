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

### Native grand-staff engraving corrections (2026-10-19)

- Measure separators form one continuous rule from the upper staff's top
  line to the lower staff's bottom line, instead of two disconnected fragments.
  Each is placed 1.35 staff spaces *before* the next source measure's onset,
  without moving any event or transport clock position.
- No artificial count-in barline appears ahead of the opening Verovio
  clef, key signature and meter. The first source note remains on its
  exact beat, and existing staff rules stay continuous.
- The single stem of an ordinary chord starts at the appropriate outer
  notehead and spans all chord pitches. Beamed chord stems use the same
  pitch extrema, real Verovio notehead bounds and one shared beam axis.
- Ties now have a tapered, native filled curve anchored outside the
  actual Verovio glyphs. Their curvature goes away from the notehead's
  stem direction; a long tie is no longer a thin straight-looking wire.
- Staves, barlines, stems, beams and ties remain structural native Godot
  geometry. These aren't independent font glyphs; Verovio contributes
  the actual clefs, noteheads, flags, rests, dots and accidentals.
  No raster pages and no typography-based horizontal scroll are introduced.
- Numerical geometry tests cover connected barlines, chords, beat-preserving
  beam positioning and tapered ties. Graphical checks still require real
  desktop captures and visual review.

### Complete pre-engraved Verovio note templates (2026-10-19)

The original glyph atlas was not enough: single notes were still being
assembled from a head texture and a custom Godot line, with another glyph for
the flag. Standalone notes are now **actually engraved by Verovio once** as
complete head + stem + flag units in `piano_teacher/verovio_note_templates.py`.
Thirteen fixed templates cover whole, half, quarter, eighth, sixteenth,
32nd and 64th notes (up/down direction where a stem exists).

Each template is extracted from Verovio's original note SVG group, rasterized
to a transparent tinted PNG and given precise notehead-centred bounds in
Verovio staff-space units. Its individual PNG is reused for every note of the
same duration and stem direction, regardless of pitch or lesson. The manifest
is cached persistently using `PreprocessingCache`, keyed by the source
font, Verovio version and `TEMPLATE_VERSION`. On reopening the application,
the backend reads those assets from disk instead of re-engraving the templates.

Native Godot receives the manifest via `/score/layout?native=1`; ordinary
raster lessons do not request or pay for it. A native score cannot activate
until both the original glyph atlas and the complete-note template atlas are
loaded. This avoids silently reverting to synthetic standalone stems/flags.
`score_verovio_glyphs.gd` loads the template PNGs as `ImageTexture` only
once; `score_native_notation.gd` positions each at its **unchanged** source
beat. Dots and accidentals are still independent genuine Verovio glyphs.

Chords, shared-stem chords, beamed groups and ties need variable geometries
depending on actual pitches and note intervals, so they are not yet baked into
fixed templates. They retain native Godot geometry and must be audited
separately. There is no full-sheet Verovio SVG scrolling or new speed curve.

### Next native engraving pass: Verovio chord and tie compounds

The first native implementation drew chord stems and tie contours with
Godot primitive lines/polygons. To avoid competing with the music engraving
library, this revision moves two more kinds of ink to real Verovio exports:

- **Ties**: `verovio_tie_templates.py` requests actual tied notes from
  Verovio, extracts the tapered tie element alone, rasterizes it to an RGBA
  mask once, and stores the shape/anchor span in the versioned preprocessing
  cache. Godot stretches only that tie contour between the two source beats,
  without drawing any replacement curve or moving noteheads.
- **Isolated chords**: `verovio_chord_templates.py` builds Verovio chord
  samples indexed by note type, stem direction and relative diatonic intervals.
  Each unique sample is cached. Up to 32 patterns per score are imported;
  the individual original notehead positions stay available for dots,
  accidentals, ledger lines and note-specific animation. Octave-transposed
  chords reuse the same cached artwork. Unsupported patterns and chords
  belonging to a beam group keep the previous per-head native renderer.
- Both asset sets are served only when `/score/layout?native=1` is used, and
  are removed from the large layout dictionary after texture import.
  A failure to export either compound must never break legacy raster layout.
- **Beams remain unresolved**: Verovio's beam/stem geometry depends on
  the exact note sequence and engraving spacing. Stretching entire beam-group
  bitmaps would distort noteheads and violate beat positions. The next change
  needs to extract beam and stem ink separately, anchoring every notehead to
  the existing single native time axis before enabling the new rendering.
  Do not silently substitute a resized full Verovio page or alter scroll speed.

These templates reuse the installed Verovio contours, not a newly
hand-constructed glyph or copied font file.

### Source-accurate multi-anchor Verovio beam extraction

Beam construction is being migrated away from native Godot polygons.

- `piano_teacher/verovio_beam_fragments.py` uses the lesson's already
  rendered Verovio SVG pages as the **single engraving source**. It extracts
  only `g.beam` ink, omitting original noteheads and staff rules. No second
  engraving pass and no synthetic beam shape is required.
- Every contained note ID is matched to the semantic score, with one source
  notehead X/Y anchor and one measured stem tip per note. A group with
  ambiguous or inconsistent IDs, a chord, duplicate beat, or cross-measure
  mismatch is rejected instead of being stretched into incorrect notation.
- The beam mask is cached by score layout identity and extraction version,
  and transferred through `/score/layout?native=1`. Godot holds it as a
  reusable `ImageTexture`.
- The native compositor **warps X piecewise between adjacent real notehead
  anchors**. For example, a three-note tuplet/beam has three anchors on
  the native time axis, so its middle note cannot drift when Verovio's
  printed horizontal spacing differs. Y retains the original staff-space
  proportions. Original Verovio beam ink and measured stem tips replace
  the native beam polygons when all source IDs match.
- Groups without a matched source fragment retain their existing native
  geometry pending support. The independent beat positions, count-in and
  scroll model have not changed.
- Explicit regression tests cover graphics isolation (no copied notehead
  or staff ink), two- and three-anchor matching, stem-tip measurements and
  persistent disk-cache reuse.

**Still to migrate:** compound beamed chords, tuplet bracket/label ink and
more complex slur geometry. These should follow the same source-identity
and multi-anchor contract rather than adding more guessed Godot shapes.

### Source-engraved tuplets, beamed chords and slurs (2026-10-19)

The same Verovio-as-engraver/Godot-as-timeline-compositor contract now covers
three additional classes of musical geometry:

- **Tuplets:** the extractor reads explicit MusicXML tuplet groups and
  pairs them with source Verovio `tupletNum` and `tupletBracket` groups.
  On Verovio releases that place graphics outside the actual note hierarchy,
  it checks the original bracket endpoints and number centre against source
  head anchors; ambiguous matches are rejected. The bracket image is split
  at its centre and fitted between two independent beat positions; the
  original numeral is painted at its original size, without X stretching.
- **Beamed chords:** multiple notes in the same source chord count as ONE
  attack for beam spacing. The `chord_note_ids` metadata retains all chord
  members. Verovio's displaced notehead image and original stem artwork
  are cached as independent masks in addition to the full isolated chord.
  The chord head positions, a single stem and the actual beam contour are
  composed on the native beat axis, using the source-measured beam endpoint.
  Unsupported/incomplete patterns keep the older compound rendering.
- **Slurs:** only explicit MusicXML start/stop IDs may create a slur. A
  matching original Verovio `slur` graphic is accepted only if its pixel
  endpoints match the two source notes on one system unambiguously. Godot
  places the genuine mask between independent native time positions and
  tilts it to the difference between the two actual pitch positions, rather
  than approximating a Bézier curve. Cross-system and ambiguous slurs are
  deliberately rejected.
- Assets are keyed by the source engraving/cache identity and generation
  version. Artworks are transferred through the native layout endpoint and
  stripped from the temporary layout dictionary immediately after loading.
  None of these assets controls tempo, note timing or horizontal camera speed.
- Geometry-level fixtures, real Verovio integration tests and headless Godot
  tests cover the source-identity and rendering contracts. Desktop visual
  captures remain necessary for artistic quality.

The historical Godot tuplet drawing and compound beam routines currently
remain as **limited fallbacks** when a source fragment cannot be extracted.
Their remaining calls should be removed only after actual score coverage
is sufficient and validated; never replace missing Verovio shapes with
silently invented geometry.

### Short-pickup time-signature collisions (2026-10-19)

Some imported performances, including Chopin's Nocturne Op. 9 No. 2,
contain a short `1/8` opening measure immediately followed by `12/8`.
A constant pixels-per-beat camera leaves too little pre-measure space to
draw both conventional meter stacks beside the noteheads. The native
renderer now caches each measure's preceding note onset and identifies
tight meter changes. On these exceptional boundaries it paints authentic
Verovio meter digits once in an upper annotation lane, rather than two
overlapping copies through both staves. The meter remains visible even
during left-hand-only practice. It does **not** insert horizontal pixel
space, move a source onset, change BPM or reintroduce Verovio page images.

Long ties were also reduced from the detached-looking arches in the user
captures: their endpoint alignment is now closer to each notehead and their
maximum bow is limited. Tests cover the 1/8→12/8 close-boundary case,
its unchanged exact half-beat X spacing, and real native Chopin screen
captures in CI.

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
