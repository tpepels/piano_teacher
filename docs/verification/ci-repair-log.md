# CI scope audit and repair log (durable hand-over record)

Read this first in every agent turn; append, never rewrite history.
Phase A is **not complete**: `docs/verification/ci-current-scope-audit.md`
does not exist yet and `scripts/ci-scope.py --check` still fails.

## 2026-11-16 — session 1 (Claude Code, interrupted by usage limit)

### Done
- `scripts/local-ci-agent.sh` now drives Claude Code by default
  (`claude -p … --permission-mode auto --output-format stream-json --verbose`,
  stdin closed), Codex via `CI_AGENT_CLI=codex`. One blocker-investigation
  turn after a turn without a commit, stop after the second. Covered by
  `tests/test_local_ci_agent_launcher.py` (4 passed, stub CLI). A real
  `claude -p` call with these flags returned a successful result event.
- Inventory at 893be609: 452 pytest modules (2799 test definitions),
  144 Godot harnesses, 32 workflows. Every test id, test path and script
  named by workflows, `scripts/*.sh`, `scripts/**/*.py` and quarantine exists.
- Draft `tests/ci-scope.json`: 620 owner/contract entries. Owners were derived
  from what each test imports/reads and then hand-corrected; Godot and
  workflow contracts are hand-written. **Not yet verified case by case.**
- Baseline, no fail-fast, at 893be609: shard 1 = 1356 passed (the
  `test_note_status_framebuffer` half-note failure did not reproduce).
  Shards 2-4 were still running when the session ended; no result recorded.

### Findings still to act on (evidence gathered, nothing deleted yet)
- Nine Godot harnesses have no runner (no pytest module, script or workflow)
  and are the only artifacts missing from the registry:
  `instructional_journey`, `learning_ui_review`, `live_playback`,
  `modes_journey`, `teaching_journey`, `ui_review`,
  `user_midi_desktop_capture` use Main members that no longer exist
  (`action_pending`, `library_pending`, `navigation_rail`, `rendered_clock`)
  and/or post to `http://127.0.0.1:8765`, which the product no longer serves.
  `native_library` requires the retired `PIANO_TEACHER_NATIVE_NOTATION=1`
  switch. `native_application` uses only existing Main members: run it
  before deciding. `scripts/check_desktop_ui.py` only launches `ui_review.gd`.
- `tests/godot/retry_camera_clock.gd` has a registry entry but no runner;
  if it passes standalone, add it to the fixture loop in
  `scripts/check-godot-syntax.sh`, otherwise trace and delete.
- `scripts/check_native_notation.py` is a self-described compatibility entry
  point for `check_native_verovio_overlay.py`; only
  `tests/test_native_smoke_consumers.py` (3 cases) and archived docs use it,
  and `test_phase4_workflows` lists it as retired from workflows. Candidate:
  delete script and module together.
- `piano_teacher/application/assessment_evidence.py::observe_assessed_take`
  has no production caller (only `test_assessment_evidence.py` and a source
  assertion in `test_coordination_boundaries.py`). Trace whether settlement
  replaced it before keeping or removing those cases.
- Test-only but intentionally retained (research parity / verification
  tooling): `instruction`, `notation.release_diagnostics`,
  `notation.support_policy`, `research.coda_parity_contract`,
  `research.coda_polyphony`, `research.coda_research_strategies`.
- Compatibility-named cases reviewed and kept because production still uses
  the API: `engine.db` alias, positional `Note` constructor, tuple-shaped
  passage plan, integer step input, retired `count_in_max_seconds` key.

### Remaining
1. Finish shards 2-4 baseline; triage every failure (obsolete vs defect).
2. Run each Godot harness that has no pytest driver standalone (isolated
   `XDG_*` dirs; several load `main.gd` and write preferences).
3. Apply the deletions above with reasons, complete the registry, write
   `docs/verification/ci-current-scope-audit.md`, pass `ci-scope.py --check`.
4. Phase B: `bash scripts/ci-full.sh --all --fail-fast`, then smoke, Godot
   syntax, hybrid focused/corpus, empty quarantine (one Chopin Nocturne beam
   entry is still quarantined).

Physical USB/Bluetooth MIDI acceptance is not executable here and stays open.
