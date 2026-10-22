# Phase 5 legacy inventory and bounded removal

Final integration also migrated the remaining lesson facade callers in four
audit/check scripts and their regression tests to `piano_teacher.notation.lesson`,
then removed `piano_teacher/lesson_score.py`. Eleven facade modules are retired.
The organisation gate now rejects imports of this last facade too. Its focused
post-removal suite passed 80 tests. The intermediate retain decisions recorded
below describe the worker's earlier write scope and are superseded by this
integration step. Live raster/source rendering remains for the actual purposes
listed below; it is not an unused precautionary implementation.

Scope: the shared Phase 5 worktree, based on `c009c4c` (Phase 4).
This inventory follows checked-in production callers rather than treating a
`legacy` directory name or a passing historical test as proof of obsolescence.

## Removal plan

- [x] Trace the Godot entry point, Python server, public compatibility modules,
  native beam index, and their tests before editing production code.
- [x] Remove only the unused native meter-based beam inference implementation
  and its private helpers; keep source-derived beam grouping.
- [x] Remove obsolete inference-only assertions inside mixed historical tests,
  retaining their renderer, chord, signature, tuplet, and timing coverage.
- [x] Verify the cleanup contract and run serial headless/unit checks.
- [x] Follow the separately authorized facade cleanup: trace all eleven
  requested facades, migrate importers for the ten without protected callers,
  and delete those ten redundant modules.

This task does not edit Phase 3/4 tests, independent oracles, workflows,
`notation/lesson.py`, `notation/model.py`, or the semantic contract. Other
workers' edits in the shared worktree remain outside this task. No desktop
captures, commits, or pushes are part of this bounded task.

## Runtime paths and decisions

| Component | Checked-in production path and test evidence | Decision |
| --- | --- | --- |
| `godot/notation/legacy/strip.gd` | `project.godot` launches `main.tscn` / `main.gd`; `main.gd` preloads `ScoreStrip`, uses `visible_tile_range`, `tile_texture`, `map_point`, and `build`. `diagnostic_score.gd` also loads it. Explicit `PIANO_TEACHER_RENDERER=legacy` / `--legacy-notation` and native fallback still use the raster strip. `test_source_organisation.py` and legacy strip/motion tests cover these resources. | Retain, including its UID. |
| `godot/notation/legacy/exact_spacing.gd` | `main.gd` preloads `ScoreExactSpacing` and calls `reflow` during strip construction. `tests/godot/score_exact_spacing.gd` and the MIDI visual regression still call it. | Retain. |
| `godot/notation/legacy/quality.gd` | `main.gd` calls `ScoreQuality.staff_gap` and `png_width`, including layout preparation before the native/raster choice. Strip/motion tests also load it. | Retain, including its UID. |
| `godot/notation/legacy/motion_curve.gd` | `main.gd` calls `ScoreMotionCurve.velocity` and `position` on the compatibility/fallback motion path. `tests/godot/score_motion_curve.gd` directly exercises it. | Retain. |
| `piano_teacher/rendering/legacy/engraving.py` | `server.py` imports `render_layout` / `EngravedScore` through `score.py`; `PracticeEngine.engraving()` calls `render_layout`, and `geometry(native_notes=True)` still starts from that engraving. `application/score_preparation.py` extracts native beam/tuplet/slur fragments from its original SVG pages. | Retain: native source assets require it as well as fallback. |
| `piano_teacher/rendering/legacy/geometry.py` | `engraving.py` imports/calls `layout_from_pages`; `score_geometry.py` exposes it and `locate_beat`, which `feedback.py` imports. `test_score_geometry.py` covers transforms, note identity, systems, pages, and anchors. | Retain. |
| `piano_teacher/rendering/legacy/spacing.py` | `_engrave_xml()` calls `space_for_reading` / `space_for_continuous_reading`. Reading-spacing and continuous-exercise tests use it, including canonical-module monkeypatches. | Retain. |
| `piano_teacher/rendering/legacy/raster.py` | `server.py` imports it through `raster.py`; `engraved_png()` calls `rasterize_score`. Native/Verovio comparison scripts also rasterize their independent reference SVGs through this API. | Retain. |
| Public `score.py`, `raster.py`, `score_geometry.py` facades | Production callers include `server.py`, `feedback.py`, `library_health.py`, and `preprocessing_cache.py`; scripts and tests also use these import paths. They contain explicit exports rather than duplicate implementations. | Retain. |
| `score_model.py`, `xml_import.py`, `reading_spacing.py` facades | No production importer. Their actual test importers are enumerated below and now use canonical owners directly. | Remove under the authorized facade follow-up. |
| `notation_symbols.py` and `verovio_{beam_fragments,chord_templates,note_templates,slur_fragments,tie_templates,tuplet_fragments}.py` facades | No production importer. `application/score_preparation.py` already uses the canonical `notation/assets` modules. Test importers now use those same owners. | Remove under the authorized facade follow-up. |
| `lesson_score.py` facade | No production importer, but `scripts/audit_scroll_velocity.py:33` imports it, in addition to three `scripts/check_*.py` scripts and 22 test files. The audit script is explicitly outside the expanded write scope. | Retain for this bounded subset because deleting it would break an actual protected caller. No hypothetical external API retention is assumed. |
| Native `geometry.gd`: `beam_groups`, `beat_group_length`, `_beam_finish`, `beam_level`, `BEAM_LEVELS`, `stem_up` | `beam_groups()` calls only its own inferred-meter/tuplet helpers. Before removal its only external calls were in `tests/godot/phase_c_beaming.gd` and `phase_c_tuplets.gd`; `beat_group_length` / `beam_level` were likewise referenced only by this dead implementation and those assertions. `stem_up()` had no caller. Production grouping and direction come from the source index below. | Remove as one cohesive obsolete implementation. |
| Native `score_index.gd`: `source_beam_groups`, and `geometry.gd`: `beamed_ids`, `tuplet_groups`, other shared geometry | `view.gd.load_score()` calls `ScoreIndex.build(timeline.model, glyphs)`. The index gets groups and stem directions exclusively from `glyphs.beam_metadata`, then uses `Geometry.beamed_ids` and `Geometry.tuplet_groups`. `view.gd` paints those source groups on the timeline. | Retain; source identity and authentic engraved grouping remain authoritative. |

Repository searches included Godot/Python production code, tests, scripts,
documentation, launch configuration, and hidden tracked configuration; addon
and generated editor-cache implementation details were excluded. In particular,
there is no production `Geometry.beam_groups` call and no dynamic call to the
removed helper names. Native model `beam_groups` result keys, glyph metadata
`stem_up` fields, and `view.gd.beam_groups` state are unrelated live interfaces
and are retained.

## Historical tests

The Phase C2/C3 files mix obsolete implementation checks with useful live
coverage, so deleting whole files would discard still-needed tests.

- `tests/test_phase_c_beaming.py`: retire only the two assertions demanding
  that the unused inference functions exist. Keep source-index wiring,
  authentic beam painting, linear time-axis, and legacy-motion independence
  checks.
- `tests/godot/phase_c_beaming.gd`: retire guessed meter groups, guessed rest
  breaks, the unused beam-level lookup, and inferred short-note boundaries.
  Keep exact source group membership and chord-leader checks against the
  renderer's actual indexed groups, all source stem/contour/scroll checks,
  signatures, chord offsets, 32nd/64th support, and fallback checks. The live
  source-group assertions also check that changing the meter cannot change
  source beam boundaries and that absent source metadata cannot invent beams.
- `tests/godot/phase_c_tuplets.gd`: retire the inference call while retaining
  explicit MusicXML tuplet semantics; check the same two beam memberships
  against the renderer's source-derived groups instead.

No complete test file or live rendering behavior is being removed. Existing
independent beam extraction and written-source preservation tests remain
unchanged.

## Authorized facade follow-up

The user's follow-up explicitly authorizes retiring facade-only modules and
migrating importing tests/scripts. An AST import inventory across production,
tests, and scripts found **zero production importers for all eleven requested
facades**. Ten have only test callers and can be removed without editing any
protected Phase 3/4/5 test or audit/aggregate script. `lesson_score.py` has the
actual protected audit caller described above, so that facade and all of its
imports are outside this subset. There are no script import migrations for
the ten selected facades because none of the scripts imports them.

| Removed path under `piano_teacher/` | Canonical owner | Actual prior importer files under `tests/` |
| --- | --- | --- |
| `verovio_beam_fragments.py` | `notation/assets/beams.py` | `test_native_beamed_chords.py`, `test_verovio_beam_fragments.py` |
| `verovio_chord_templates.py` | `notation/assets/chords.py` | `test_native_beamed_chords.py`, `test_native_spacing_chords.py`, `test_verovio_compounds.py` |
| `verovio_note_templates.py` | `notation/assets/notes.py` | `test_native_beamed_chords.py`, `test_verovio_note_templates.py` |
| `verovio_slur_fragments.py` | `notation/assets/slurs.py` | `test_native_fragment_geometry.py`, `test_verovio_slur_fragments.py` |
| `verovio_tie_templates.py` | `notation/assets/ties.py` | `test_native_beamed_chords.py` |
| `verovio_tuplet_fragments.py` | `notation/assets/tuplets.py` | `test_verovio_tuplet_fragments.py` |
| `notation_symbols.py` | `notation/assets/glyphs.py` | `test_fidelity_preparation.py`, `test_native_beamed_chords.py`, `test_native_fragment_geometry.py`, `test_native_snapshot.py`, `test_notation_symbols.py`, `test_preparation_ink.py`, `test_recovery_motion.py`, `test_score_motion_render.py`, `test_score_overlay.py`, `test_verovio_compounds.py` |
| `reading_spacing.py` | `rendering/legacy/spacing.py` | `test_continuous_exercise_score.py` |
| `score_model.py` | `notation/model.py` | `test_native_barlines.py`, `test_native_spacing_chords.py`, `test_score_model.py` |
| `xml_import.py` | `importing/musicxml.py` | `test_native_barlines.py` |

Those **18 importing test files** change only import paths/module bindings.
Module-based monkeypatches now target their actual canonical owners; no
assertion or production behavior changes accompany those import migrations.
`tests/test_phase_c_notation.py` changes its facade-specific source assertion
to require the canonical glyph import in `application/score_preparation.py`;
`tests/godot/phase_c_notation.gd` updates its Python glyph-path comment.
`tests/test_source_organisation.py` now checks maintained canonical definitions
and rejects retired facade files or remaining AST imports throughout
production, tests, and scripts. It no longer requires obsolete facades to
exist. Existing test names containing the old domain terminology remain
valid regression files; their names do not create a compatibility layer.

The canonical implementations are unchanged by this follow-up. Active
`score.py`, `score_geometry.py`, and `raster.py` adapters remain because of
their real production callers. The earlier source-organisation design and
architecture notes describe the prior facade-preservation migration; this
inventory records the newly authorized retirement and current canonical paths.

## Verification record

All Python commands use `/home/tom/Projects/piano_teacher/.venv/bin/python`
with `PYTHONPATH=/home/tom/Projects/piano_teacher_phase5` and run through `rtk`.
Godot checks in this task are serial `--headless` tests; there are no desktop
captures.
The completed runs below had no disk-quota errors. Subsequent pytest runs use
task-specific `--basetemp` directories under
`/home/tom/Projects/piano_teacher_phase5_evidence/tests/`, per the parent's
shared `/tmp` quota notice.

- Baseline and post-removal focused suite: **10 passed** each.
- Cleanup **RED**: the removal-contract audit failed with exit 1 before the
  change, listing `beam_groups`, `beat_group_length`, `_beam_finish`,
  `beam_level`, and `stem_up` as remaining obsolete static functions.
- Cleanup **GREEN**: the identical audit passed with exit 0 after the change,
  printing `Obsolete native beam helpers still present: []`. This is a code
  removal contract, not a claim of a newly fixed rendering defect; production
  already used source-derived grouping before this change.
- Post-removal regression suite: **65 passed in 10.75s**, no skips or failures.
  This includes three serial headless Godot harnesses (native notation,
  source beams, tuplets), unchanged written-source beam preservation and
  actual Verovio beam extraction tests, and retained Python geometry,
  spacing, continuous engraving, raster, and HTTP behavior.
- Scoped `git diff --check`: exit 0. Search after removal found no removed
  function definition or call; the historical Python test retains its
  negative assertion that production must not call inferred `beam_groups`.

Rerun the beam-cleanup selection (the final source includes the later facade
contract tests as well):

```sh
rtk proxy env PYTHONPATH=/home/tom/Projects/piano_teacher_phase5 \
  /home/tom/Projects/piano_teacher/.venv/bin/python -m pytest -q \
  --basetemp /home/tom/Projects/piano_teacher_phase5_evidence/tests/legacy-beams-reproduce \
  tests/test_phase_c_notation.py tests/test_phase_c_beaming.py \
  tests/test_phase_c_tuplets.py tests/test_source_organisation.py \
  tests/test_source_beam_pixel_fidelity.py tests/test_verovio_beam_fragments.py \
  tests/test_score_geometry.py tests/test_reading_spacing.py \
  tests/test_continuous_exercise_score.py tests/test_raster_pipeline.py
```

Reproduce the removal contract (the same assertion was RED before removal):

```sh
rtk proxy env PYTHONPATH=/home/tom/Projects/piano_teacher_phase5 \
  /home/tom/Projects/piano_teacher/.venv/bin/python -c '
from pathlib import Path
import re
text = Path("godot/notation/native/geometry.gd").read_text()
obsolete = ("beam_groups", "beat_group_length", "_beam_finish", "beam_level", "stem_up")
remaining = [name for name in obsolete
             if re.search(r"^static func " + re.escape(name) + r"\(", text, re.M)]
print("Obsolete native beam helpers still present:", remaining)
assert not remaining, "Unused beam inference implementation remains"
'
```

For the beam-inference cleanup, the only changed production implementation
is `godot/notation/native/geometry.gd` (114 lines deleted, two explanatory
comment lines added). Its three mixed historical test files are enumerated
above. A fresh read-only reviewer found no missed callers, lost live coverage,
or other findings in that initial five-file cleanup. There were no
configuration references to the removed functions to update.

The facade follow-up separately deletes the ten production facade files
listed in its table, migrates the 18 actual importing tests, and updates the
three organisation/path-reference test files described above. It does not
modify any remaining production implementation or any script.

Facade follow-up verification:

- Before import migration: selected asset/spacing/organisation regression
  baseline — **88 passed in 20.23s**.
- **RED:** `test_retired_notation_facades_have_no_remaining_importers`
  failed with the ten facade files still present; the canonical-owner test
  passed in the same run (**1 failed, 1 passed**).
- **GREEN:** after migration and deletion, the organisation suite passed
  **7/7**, including the same retirement contract and the import scan.
- Import collection for every changed Python test file, including desktop
  capture tests without executing them: **126 tests collected**.
- Broader post-migration unit/headless regression run: **114 passed in
  25.17s**, no skips or failures. It exercises actual Verovio asset generation,
  source-derived beam/chord/tuplet behavior, model/import/barline contracts,
  continuous spacing, revision locking, preparation overlay, and serial
  headless native geometry. The desktop capture tests are collection-only.

The read-only facade review found two contract-test issues, both addressed
without changing production code:

- **Relative import bypass:** `from . import score_model` and subpackage
  `from .. import score_model` were missed when `ast.ImportFrom.module` was
  empty. Two synthetic-source mutation cases reproduced this with **2 failed**
  (`DID NOT RAISE`) before the fix. The scanner now resolves relative imports
  against each importer's package before checking module aliases. The complete
  organisation suite then passed **10/10**, including both formerly red cases.
- **Retained adapter guards:** restored the previous wildcard-import and
  `sys.modules` restrictions for the still-needed `score.py`, `raster.py`, and
  `lesson_score.py`, also covering live `score_geometry.py`. Canonical ownership
  checks and retired-facade rejection remain in place.

The final changed-file import collection includes **129 tests**. Review-fix
checks and final regression runs use task-specific home evidence directories
for pytest temporary files; no quota failures are counted as code failures.
Final post-review regression verification: **117 passed in 33.73s**, no skips,
failures, or quota errors. Final scoped `git diff --check`: exit 0. Both review
findings are addressed; there are no deferred findings. No desktop tests,
commits, or pushes were performed.

Reproduce the facade follow-up regression run:

```sh
rtk proxy env PYTHONPATH=/home/tom/Projects/piano_teacher_phase5 \
  /home/tom/Projects/piano_teacher/.venv/bin/python -m pytest -q \
  --basetemp /home/tom/Projects/piano_teacher_phase5_evidence/tests/legacy-facades-reproduce \
  tests/test_verovio_beam_fragments.py tests/test_verovio_compounds.py \
  tests/test_verovio_note_templates.py tests/test_verovio_slur_fragments.py \
  tests/test_verovio_tuplet_fragments.py tests/test_notation_symbols.py \
  tests/test_native_spacing_chords.py tests/test_native_barlines.py \
  tests/test_continuous_exercise_score.py tests/test_source_organisation.py \
  tests/test_score_model.py tests/test_native_snapshot.py \
  tests/test_phase_c_notation.py tests/test_phase_c_beaming.py \
  tests/test_phase_c_tuplets.py \
  tests/test_native_fragment_geometry.py::test_native_fragment_anchors_and_accidental_collisions \
  tests/test_native_beamed_chords.py::test_authentic_beamed_chords_select_source_direction_before_validation \
  tests/test_native_beamed_chords.py::test_authentic_beamed_stem_masks_exclude_nested_flags \
  tests/test_native_beamed_chords.py::test_packed_accidental_ink_clears_previous_onset_at_one_global_scale \
  tests/test_score_overlay.py
```

This cleanup is not evidence of native release readiness. The Phase 3/4
independent gates retain their existing scope, obligations, and denominators.

## Changed paths owned by this cleanup

The facade table identifies the ten deletions; all other paths below are
modified, except this new inventory. Other workers' shared-worktree changes
are excluded.

```text
godot/notation/native/geometry.gd
piano_teacher/notation_symbols.py
piano_teacher/reading_spacing.py
piano_teacher/score_model.py
piano_teacher/xml_import.py
piano_teacher/verovio_beam_fragments.py
piano_teacher/verovio_chord_templates.py
piano_teacher/verovio_note_templates.py
piano_teacher/verovio_slur_fragments.py
piano_teacher/verovio_tie_templates.py
piano_teacher/verovio_tuplet_fragments.py
tests/godot/phase_c_beaming.gd
tests/godot/phase_c_notation.gd
tests/godot/phase_c_tuplets.gd
tests/test_continuous_exercise_score.py
tests/test_fidelity_preparation.py
tests/test_native_barlines.py
tests/test_native_beamed_chords.py
tests/test_native_fragment_geometry.py
tests/test_native_snapshot.py
tests/test_native_spacing_chords.py
tests/test_notation_symbols.py
tests/test_phase_c_beaming.py
tests/test_phase_c_notation.py
tests/test_preparation_ink.py
tests/test_recovery_motion.py
tests/test_score_model.py
tests/test_score_motion_render.py
tests/test_score_overlay.py
tests/test_source_organisation.py
tests/test_verovio_beam_fragments.py
tests/test_verovio_compounds.py
tests/test_verovio_note_templates.py
tests/test_verovio_slur_fragments.py
tests/test_verovio_tuplet_fragments.py
docs/native-notation-phase5-legacy-inventory.md
```
