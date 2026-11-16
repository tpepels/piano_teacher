# Current-application CI scope audit

Audit of every pytest module, native Godot harness and GitHub workflow
against the current product: one Godot 4.7 desktop process with embedded
CPython, native Verovio notation, one immutable score stream and a single
MIDI/transport timeline. Started at `893be609` (2026-11-16). The reviewed
registry is `tests/ci-scope.json`; `python scripts/ci-scope.py --check`
enforces that every artifact has an existing source owner and a contract.

## Method

1. **Inventory.** `scripts/ci-scope.py --inventory`: 452 pytest modules
   (2,799 test definitions), 144 Godot scripts, 32 workflows at the start.
2. **Ownership trace.** For each pytest module the imported
   `piano_teacher`/`scripts` modules and every literal source path it reads
   were resolved against the tree; no module imports or reads a missing
   product file (the only unresolved paths are deliberate negative fixtures
   and retirement lists). The owner in the registry is the product source
   the module exercises most, corrected by hand where a generic module
   (`music.py`, `server.py`, `main.gd`) outweighed the real subject.
3. **Reachability.** The import closure of `piano_teacher.inprocess` and
   `piano_teacher.__main__` covers 143 of 205 package modules; 55 more are
   used only by verification tools under `scripts/`; 7 had no user outside
   tests and were examined one by one (below).
4. **Execution.** All four shards were run without fail-fast at `893be609`
   (about 5,200 cases): every failure and every skip was read. Every Godot harness
   without a pytest driver was run headless with isolated `XDG_*`
   directories, with the arguments its workflow or gate passes.
5. **Reference integrity.** Every `tests/...::test` id, test path and
   script named by workflows, `scripts/*.sh`, `scripts/**/*.py`, README and
   `tests/quarantine.txt` exists.
6. **Case-level review.** The names of all cases mentioning legacy, removal,
   compatibility, migration, HTTP/UDP/Qt or an old contract (about 180, in
   the 104 modules the inventory flags) were reviewed; each one implying a
   retired contract was read in full together with the production code it
   calls. Other cases were judged by their module's traced owner and by
   execution, not read line by line.

## Removed (retired contracts)

| Artifact | Retired contract and evidence | Replacement |
|---|---|---|
| `tests/godot/instructional_journey.gd`, `learning_ui_review.gd`, `modes_journey.gd`, `teaching_journey.gd` | Driven by `scripts/smoke_*_godot.py` and `tests/test_*_journey.py`, deleted in `bcce6ab4` ("Delete obsolete network smoke utilities"). They read `Main.action_pending`, `library_pending` and `navigation_rail`, which no longer exist, and observe "ordinary HTTP state". No runner remained. | `godot/production_session_journey.gd`, `godot/production_ui_smoke.gd` (embedded runtime workflow); `tests/godot/practice_interactions.gd`, `guided_interactions.gd`, `library_resume.gd`, `pending_navigation.gd` |
| `tests/godot/live_playback.gd`, `ui_review.gd`, `user_midi_desktop_capture.gd` | Post to `http://127.0.0.1:8765`; the product has no HTTP listener (`test_inprocess_transport_structure`, `test_runtime_architecture_contract`). Drivers deleted in `bcce6ab4`. | `tests/godot/native_camera.gd`, `score_motion.gd`, `recovery_motion_capture.gd`, `ui_scaling.gd`, `art_direction.gd` |
| `scripts/check_desktop_ui.py` | Only launched `ui_review.gd`. | `scripts/review_art_direction.py` |
| `tests/godot/native_application.gd` | "HTTP downloads and real transport" smoke; its driver `scripts/smoke_native_notation.py` was deleted in `bcce6ab4`; cannot start without the removed external engine. | `godot/production_ui_smoke.gd`, `tests/godot/native_production.gd` |
| `tests/godot/native_library.gd` | Refuses to run unless `PIANO_TEACHER_NATIVE_NOTATION=1`, a renderer-selection switch production ignores (`test_source_organisation::test_production_renderer_ignores_retired_selection_switches`); its workflows were removed in `caa85745`. | `tests/godot/native_library_diagnostic.gd` |
| `scripts/check_native_notation.py`, `tests/test_native_smoke_consumers.py` (`test_compatibility_checker_exposes_canonical_options_without_selector`, `test_compatibility_checker_preserves_canonical_parser_failure`, `test_compatibility_main_accepts_explicit_argv_and_restores_process_args`) | Self-described "compatibility entry point" forwarding to `check_native_verovio_overlay.py`; no script, workflow or current document called it, and `test_phase4_workflows` already lists it as retired. | `tests/test_native_verovio_overlay.py`, `tests/test_verification_runner_failures.py` exercise the canonical CLI |
| `piano_teacher/application/assessment_evidence.py`, `tests/test_assessment_evidence.py` (`test_valid_graded_take_uses_original_stage_identity_and_bpm`, `test_no_fingerprint_or_ungraded_records_do_not_persist`) | `observe_assessed_take` lost its last caller when settlement moved into the teaching decision; production builds `AssessmentEvidence` in `teaching_decisions.py`. The tests exercised an uncalled helper with monkeypatched collaborators. | `tests/test_teaching_decisions.py`, `tests/test_assessment_commit.py`, `tests/test_assessment_tempo_evidence.py`; `test_coordination_boundaries::test_completed_take_owns_only_transport_and_session_persistence` now asserts the helper is gone |

## Rewritten (behaviour exists, test was outdated)

- `tests/godot/retry_camera_clock.gd`: had no runner and fed the clock a
  `transition_in_seconds` snapshot. Production takes the reverse, rest and
  deadline from `visual_preparation_schedule` backend epochs. Rewritten to
  that contract, with a negative control (no schedule, no retry clock), and
  added to `scripts/check-godot-syntax.sh`. It is the only harness that
  checks `retry_preparing`, `retry_count_in_beat` and release on an unrelated
  transport against the real clock.
- `test_retained_score_pipeline::test_real_score_framebuffer_uses_production_world_axis`:
  expected the playhead literal in `view_base.gd`; `ec133eb1` moved it to
  the single owner `notation/shared/spacing_policy.gd`. Now asserts the
  owner and both aliases.
- `test_ci_full_runner`: predated the scope and Godot-parse preflights of
  `ci-full.sh`. Its isolated checkout now carries `ci-scope.py` and a
  registry, covers a missing registry and a failing parse, and keeps the
  collection-failure shard case. `ci-full.sh` accepts `GODOT_BIN`.
- `tests/test_phase3_real_rest_protocol.py`: skipped unless
  `PIANO_REAL_PIXEL_TESTS=1`, and no gate selecting the module set it, so
  its four framebuffer cases never ran. The gate is removed; they pass in
  the full suite like the other framebuffer modules.

## Reviewed and retained

- **Removal and migration guards** (they verify the retired architecture
  stays removed): `test_inprocess_transport_structure`,
  `test_runtime_architecture_contract`, `test_native_retirement`,
  `test_source_organisation`, `test_phase5_architecture_audit`,
  `test_repository_hygiene`, `test_transport_field_ownership`,
  `test_godot_preload_paths`, the retirement cases of
  `test_retained_score_pipeline`, `test_lesson_generator_architecture`
  (removed strategies), `test_library` (saved removed strategy and obsolete
  MusicXML recents migrate), `test_lesson_settings_grading` (retired
  `count_in_max_seconds` key still loads), `test_learning_ledger`
  (one-time migration), `test_strategy_handoff`, `test_course_consolidation`
  (unversioned rows cannot restore mastery).
- **Compatibility-named cases that test API still in use:** `engine.db`
  alias (129 production uses), positional `Note` constructor, tuple-shaped
  passage plan, integer step input, `verify_midi_performance` without
  generated XML, hairpin fallback for unsupported wedge geometry.
- **Modules with no runtime importer, retained on purpose:** research
  parity (`research/coda_parity_contract.py`, `coda_polyphony.py`,
  `coda_research_strategies.py`; README keeps author-style Coda for research
  parity and the Coda workflows run them), verification policy
  (`notation/release_diagnostics.py`, `notation/support_policy.py`) and
  `instruction.py` (`next_full_attempt`, the warning-retry rule).
- **Reference rasterizer** `engraving/raster.py`: not in the runtime, used by
  `scripts/audits/capture_runner.py` as the independent Verovio reference.
- **Godot harnesses:** 135 remain. Each is driven by a pytest module, by
  `scripts/check-godot-syntax.sh` / `verify-hybrid-workflow.sh`, by a
  workflow, or is a shared fixture (`framebuffer_take`, `library_fixture`,
  `native_production_fixture`). The 11 with neither a pytest driver nor a
  syntax-gate entry were executed directly and pass; the syntax gate passes.
- **Workflows:** all 32 select existing tests and scripts and gate current
  code. They cannot be executed locally; `test_phase4_workflows` checks
  their structure. "step2/3/4" and "phase1/6" are historical names for
  current test sets.

## Skips in the local full suite

Environment or parametrization only: `test_sampled_piano` (no system SF2 /
libfluidsynth installed), `test_fingering_obstacle_geometry` (cases that do
not apply to a given source). No test is skipped to hide a failure.

## Open after this audit (Phase B, not scope)

- `tests/test_note_status_framebuffer.py`: two failing cases (missed half
  note recolour error 6.03 > 6.0; glow detached from the head mask).
- `tests/quarantine.txt`: one strict xfail (Chopin Nocturne Op. 9 No. 2
  bars 13-16 beam verifier).
- Physical USB/Bluetooth MIDI acceptance cannot run headless and stays open.

Scope audit: COMPLETE
