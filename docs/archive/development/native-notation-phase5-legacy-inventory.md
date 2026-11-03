# Phase 5 notation cleanup inventory

Cleanup follows production callers and executable regressions. The functional
notation fixes use separate commits. No rendering algorithm was removed solely
because its directory or filename contains `legacy`.

## Removed implementations

The native compositor obtains beam membership and stem direction from authentic
Verovio fragments through `notation/native/score_index.gd`. The old independent
meter-based inference in `notation/native/geometry.gd` had no production caller.
Its `beam_groups`, `beat_group_length`, `_beam_finish`, `beam_level`, `stem_up`
and associated constant are removed. Live source grouping, `beamed_ids`, tuplet
grouping, chord offsets and shared geometry remain.

The mixed historical Phase C tests now exercise the production source groups.
They retain chord, signature, stem, contour, tuplet, scrolling and timing checks.
Assertions requiring the unused inference implementation were removed. The
updated tests also reject invented groups when source metadata is absent and
verify that changing the meter cannot change an authored beam boundary.

## Retired compatibility modules

Eleven facades are removed; their test and script callers use the owning modules.
None contained a separate production algorithm or needed an external dependency.

| Removed module in `piano_teacher/` | Maintained owner |
| --- | --- |
| `lesson_score.py` | `notation/lesson.py` |
| `score_model.py` | `notation/model.py` |
| `xml_import.py` | `importing/musicxml.py` |
| `reading_spacing.py` | `rendering/legacy/spacing.py` |
| `notation_symbols.py` | `notation/assets/glyphs.py` |
| `verovio_beam_fragments.py` | `notation/assets/beams.py` |
| `verovio_chord_templates.py` | `notation/assets/chords.py` |
| `verovio_note_templates.py` | `notation/assets/notes.py` |
| `verovio_slur_fragments.py` | `notation/assets/slurs.py` |
| `verovio_tie_templates.py` | `notation/assets/ties.py` |
| `verovio_tuplet_fragments.py` | `notation/assets/tuplets.py` |

`test_source_organisation.py` checks canonical ownership and rejects restored
facades or stale absolute/relative imports, including `from . import module`
and subpackage `from .. import module`. Audit, generated-lesson, engraving and
MIDI visual-comparison scripts import the canonical lesson implementation.

## Retained dependencies

| Component | Current necessary purpose |
| --- | --- |
| Godot `notation/legacy/strip.gd` | `main.gd` and `diagnostic_score.gd` still build source strips and use tile selection, textures and coordinate mapping. Explicit raster mode and native fallback remain tested. |
| Godot `notation/legacy/exact_spacing.gd` | Live strip construction calls `reflow`; complete source ink must survive unsupported expressions and fallback. |
| Godot `notation/legacy/quality.gd` | Layout preparation uses source staff-gap and raster resolution calculations before choosing native or source rendering. |
| Godot `notation/legacy/motion_curve.gd` | The live source/fallback camera uses position and velocity transforms; motion regressions still exercise it. |
| Python `rendering/legacy/engraving.py` | The server engraves generated notation; native asset preparation extracts authentic beams, tuplets and slurs from its SVG pages. |
| Python `rendering/legacy/geometry.py` | Engraving and feedback need page/system transforms, note identity and timing anchors. |
| Python `rendering/legacy/spacing.py` | Live engraving calls continuous and reading spacing; no duplicate replacement exists. |
| Python `rendering/legacy/raster.py` | The server and independent comparison scripts rasterize actual SVG references. |
| `score.py`, `raster.py`, `score_geometry.py` | Server, feedback, library health and preprocessing still import these adapters. Explicit-export and no-module-alias guards remain. |

These retained paths serve existing functionality. In particular, slashed grace
notation and expressions without native fragments still require the complete
source fallback. Removing that path would drop source notation before native
support and independent verification exist. Its continued use is not a claim
that unsupported native notation is verified.

## Verification

- Beam removal: the retirement check failed before removal and passed afterward;
  65 focused tests passed, including three serial headless Godot harnesses.
- Facade migration: 117 focused tests passed. Two relative-import bypass
  mutations first reproduced a gap in the retirement guard, then passed with
  the corrected scanner.
- Final lesson-facade migration: 80 lesson, source, model and engraving tests
  passed; another 49 native geometry, source-beam and ownership checks passed.
- The built Python wheel contains none of the eleven retired modules and
  contains the maintained notation model.

The complete application, mutation and corpus runs remain separate evidence.
Cleanup tests do not establish whole-piece visual correctness or release
readiness. See the [Phase 5 remediation record](native-notation-phase5-remediation.md)
and [strict release decision](native-notation-phase4-release-evidence.md).
