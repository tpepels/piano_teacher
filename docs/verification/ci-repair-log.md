# CI scope audit and repair log (durable hand-over record)

Read this first in every agent turn; append, never rewrite history.
Current status is the last section. Scope decisions and their evidence are
in `docs/verification/ci-current-scope-audit.md`.

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

## 2026-11-16 — session 2: Phase A complete

- Baseline without fail-fast at `893be609` (shards 3/4 ran after an
  intermediate commit moved modules between shards, so it is diagnostic
  only): shard 1 1356 passed; shard 2 1 failed / 1262 passed; shard 3
  3 failed / 1281 passed; shard 4 1303 passed.
- Stale tests repaired: `test_retained_score_pipeline` playhead owner,
  `test_ci_full_runner` (scope + Godot preflights; `ci-full.sh` accepts
  `GODOT_BIN`).
- Removed with evidence: nine orphan Godot harnesses, `check_desktop_ui.py`,
  `check_native_notation.py` + `test_native_smoke_consumers.py`,
  `application/assessment_evidence.py` + `test_assessment_evidence.py`.
- `retry_camera_clock.gd` rewritten to the scheduled-epoch contract and added
  to `check-godot-syntax.sh`. `test_phase3_real_rest_protocol.py` no longer
  hides behind an env switch nothing set (4 cases, passing).
- `ci-smoke.sh` uses `.venv/bin/python` when present (the system Python has
  no pytest; hosted CI is unchanged).
- Verified at the Phase A commit: `ci-scope.py --check` (618 artifacts),
  `ci-smoke.sh` (865 passed), `check-godot-syntax.sh`, 5,193 cases collected,
  shard plan 112/113/113/113 modules.

### Phase B queue
1. `tests/test_note_status_framebuffer.py::test_recolor_replaces_the_white_head_without_a_doubled_contour`
   — missed `head_half`, mean error 6.03 > 6.0.
2. `tests/test_note_status_framebuffer.py::test_glow_is_extremely_subtle_and_follows_the_notehead_mask`
   — glow detached from the head mask (missed `head_black` in a chord).
3. Quarantine entry: Chopin Nocturne Op. 9 No. 2 bars 13-16 beam verifier.
4. Then the full gate, smoke, Godot syntax, hybrid focused and corpus on one
   clean commit.

## 2026-11-16 — Phase B repair 1: note-status framebuffer

- **Recolour error (production defect).** `StreamLifecycle.project` placed
  each strip's clip `Control` at a fractional x. Godot renders a Control at
  whole pixels, so the strip's ink sat up to half a pixel off the world axis
  (0 px for a strip clipped at the integer gutter, about +0.43 px for the
  next one), while projected notehead positions stayed exact. Measured on the
  retained PNGs: ink and tint agreed with each other but both were 0.375-0.5
  px from the reported head in later strips; mean recolour error up to 7.18.
  Fix: the window sits on a whole pixel and the source takes the remainder.
  After the fix every head measures at most 0.24 (limit 6.0, unchanged).
  Regression: `tests/godot/stream_retained_lifecycle.gd` (fails without the
  fix), plus the unchanged framebuffer thresholds.
- **"Detached glow" (test model defect).** The 72/100 flagged pixels were the
  recoloured ink of the other head of the same chord inside a shared crop.
  The check now accounts for every coloured head whose authentic mask
  reaches the crop with the same 3 px rule; a new negative control proves one
  stray tinted pixel beside a chord head is still reported.
- Files: `godot/notation/native/stream_lifecycle.gd`,
  `tests/godot/stream_retained_lifecycle.gd`,
  `tests/test_note_status_framebuffer.py`.
- Run: note-status and palette framebuffer modules (22 passed), Godot syntax
  gate, seven stream harnesses, 14 placement-sensitive framebuffer modules
  (60 passed).
