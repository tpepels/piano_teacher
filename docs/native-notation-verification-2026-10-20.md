# Native notation verification — 20 October 2026

> **Historical baseline.** The [21 October post-refactor audit](native-notation-verification-2026-10-21.md) verifies the current two-measure curriculum and supersedes these stage and notehead totals.

The engine keeps the established architecture: Verovio supplies authentic glyphs
and engraved fragments; Godot composes them on one continuous musical timeline.
Native application runs explicitly used `PIANO_TEACHER_NATIVE_NOTATION=1` and
checked native readiness and visibility. Legacy raster/strip tests are
compatibility checks and are not counted as native rendering evidence.

## Changes

- Whole-note and whole-chord ink now uses the whole-head centre, keeping it on
  the source attack. Chord caches reject incomplete or corrupt images and rebuild
  the original components. Pattern enumeration no longer has an arbitrary cap.
- Reusable stem masks exclude nested flags. Source beam direction selects the
  corresponding chord template. Beam fragments attach at measured stems, including
  displaced seconds, and retain the correct source leader's Y origin.
- Beam/tuplet extraction no longer truncates long passages. Beam masks exclude
  chord stems and tuplet ink. Tuplet matching handles chord members and nested
  groups; horizontal geometry accounts for the SVG viewport aspect ratio.
- Slurs retain source identity, use cropped masks, retry incomplete caches, and
  use normalised Godot texture coordinates. Their contours are actual Verovio ink.
- Chord attachments use engraved head positions. Accidentals occupy separate
  columns, and score-wide clearance includes the resulting ink footprint.
  Tick and short rules complete support for all eleven MusicXML bar styles.
- Python prepares layout, semantic IDs and assets under one revision lock.
  Responses carry that revision; Godot waits for matching layout assets before
  loading the semantic model and discards mismatched responses.

Density is chosen once for the whole exercise, using the maximum staff gap so a
resize cannot introduce a new collision. The configured preference remains
24–480 pixels/beat; automatic clearance supports up to 8192. Expressive source
attacks just 0.00625 beat before a tied barline continuation require a much larger
scale than ordinary reading. Their times, identities and grading are preserved.
Neither BPM changes nor local collisions introduce variable scrolling speed.

## Real MIDI library

The strict audit paints every notation-note ID, including tied continuations,
advancing to each still-unseen onset. A pass requires complete ID coverage and a
linear, unchanged density. It does not infer success from catalogue presence or
measure-start screenshots.

| Piece | Curriculum stages | Verified notation noteheads |
|---|---:|---:|
| Ala — Joep Beving | 59 | 2,701 |
| Autumn Leaves — Bill Evans | 88 | 3,049 |
| Chopin, Nocturne Op. 9 No. 2 | 122 | 7,253 |
| Danny Boy — Bill Evans | 63 | 1,885 |
| Merry-Go-Round of Life | 301 | 11,144 |
| Peace Piece — Bill Evans | 311 | 12,251 |
| Waltz for Debby | 97 | 3,574 |
| **Total** | **1,041** | **41,857 / 41,857** |

All stages passed with zero fallbacks and zero missing IDs. The checked-in
[machine-readable summary](evidence/native-notation-2026-10-20/library-summary.json)
records per-piece counts and density maxima. The maximum observed global scale
was approximately 7794 pixels/beat in Peace Piece.

Ala measure 9 has a dedicated regression covering right original, left skeleton,
left original and both-hand original stages. The actual desktop application was
also inspected in native mode with both-hand chords visible. A separate HTTP
application smoke checks measure 10 starts three beats into the measure-9 passage,
so a correct-looking score cannot conceal an incorrect seek.

Authentic authored MusicXML fixtures additionally exercise forced up/down beamed
chords, displaced seconds, beam/stem contact at multiple densities, close
accidentals, slur pixels, tuplets, dots and typed barlines. The source-fidelity
corpus checks import, source identity, hand assignment, grading and engraving.

## Reproduction

```bash
PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python scripts/check_native_notation.py --output /tmp/piano-native-library-audit
PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python scripts/smoke_native_notation.py --measure 10 --render
PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python -m pytest -q
PIANO_TEACHER_NATIVE_NOTATION=1 bash scripts/check_godot.sh
PIANO_TEACHER_NATIVE_NOTATION=1 .venv/bin/python scripts/check_musical_fidelity_corpus.py
```

The desktop HTTP checks require exclusive port 8765. The library audit uses no
HTTP server and does not modify source MIDI files. MIDI grading journeys exercise
the production callback with a test input adapter; this verification does not
constitute a physical USB piano or hardware latency test.

## Final checks and remaining legacy failure

The final full Python suite, with native notation explicitly enabled, completed
with **883 passed, 1 failed, 1 skipped**. All native regressions passed. The Godot
parser/layout checks and all **30 source-fidelity corpus checks** also passed.
An independent review verified the beam-contact, accidental-footprint,
note-ID-coverage and seek-offset fixes.

The remaining failure is the pre-existing
`tests/test_staff_visibility.py::test_active_staves_are_white_through_countin_and_scrolling`.
Its standalone legacy fixture reports staff-whiteness pixel failures and calls
an uninitialised HTTP request during navigation. It already failed at the initial
baseline, uses the raster renderer, and was left unchanged. The full suite is
therefore not entirely green; no native success claim relies on that fixture.
