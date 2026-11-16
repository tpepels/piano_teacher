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

## 2026-11-16 — Phase B repair 2 and open items (session stopped by usage limit)

- Gate at `f0da11e8`: shard 1 1189 passed, shard 2 1323 passed, shard 3
  halted on `test_fingering_real_placement.py[hanon-low]` (Godot timeout);
  shard 4 not run.
- Cause: the test extracted `view.gd` from commit `04da92b` (2026-10-25) and
  ran it against current modules for a `before.png` no assertion reads.
  `72ee35e3` removed `Geometry.required_density`, so that script no longer
  parses and the harness never quits. The pinned-history capture is removed
  from the test and from `native_fingering_real_placement.gd` (9 passed).
  This is a retired-compositor dependency; add it to the scope audit table.
- Strip windows now have BOTH edges on whole pixels (seam safety). **Not yet
  verified on a framebuffer.** Suspicion to check first next session: in
  the Chopin capture `native-7.35000.png` the natural sign at x≈344 lacks its
  left stroke while the same sign is complete in `native-6.00000.png`; a
  one-pixel seam gap from the `f0da11e8` rounding is the likely cause.
  Re-capture and add a seam regression (adjoining windows: right == left).
- The first baseline missed modules (shard plan changed mid-run); only a
  full `ci-full.sh` run is evidence.

### Quarantined Chopin Nocturne bars 13-16 (131 errors, was 234)
Native ink matches the Verovio reference by eye. Separate causes found:
1. `connector_pixels._stem`: a natural sign's long stroke beside a down-stem
   is a second stem candidate, so "ambiguous or too broad". Prototype (not
   committed): judge breadth on the contiguous column cluster holding the
   longest candidate and reject a disjoint rival >= 0.9 of its length.
   Result 5 -> 8 of 10 beams verified. Needs mutation controls.
2. Beat 7.5 beam: the 32nd hook starts 3 px later than the linearly mapped
   reference (x 1099 vs 1096); needs a small level-boundary tolerance.
3. Beat 12.0 beam: every witness is either under the playhead or has
   "Ambiguous image translation" (periodic figure); head registration.
4. Still unexamined: 64th flags (12), stems m13 (7), flag absence (7),
   tuplet bracket at 11.0, opening key/meter, m16 barline, ownership.

### Remaining
Full gate on one clean commit, then smoke, Godot syntax, hybrid focused and
corpus (not yet run), and an empty quarantine.

## 2026-11-16 — session 3

- Strip windows open outward (floor left / ceil right); nearest rounding
  could cover half a pixel of the strip's own ink. Regression in
  `stream_retained_lifecycle.gd` fails with nearest rounding.
- The "clipped natural" in the Chopin capture is NOT a seam. Raw pixels are
  binary (245/39): glyph textures are rasterized at `RASTER_SCALE` 1.75 with
  250 units per staff space and minified about 40x at an 11 px staff gap
  with no mipmaps, i.e. point sampled. A stroke thinner than a pixel
  disappears at some sub-pixel phases (present at clocks 7.25 and 7.50,
  absent at 7.35) and 64th flags alias into hatching.
- Experiment (reverted, not committed): mipmaps + `LINEAR_WITH_MIPMAPS` on the
  native view restores the stroke and smooths flags, but softens all ink and
  raises the Chopin verifier errors from 131 to 165 (34 accidental contours
  no longer match). This changes how every glyph looks and what every pixel
  oracle measures. **Owner decision needed**: keep crisp point-sampled ink,
  rasterize glyphs at display scale, or adopt mipmaps and retune the oracles.
  The Chopin quarantine entry cannot be cleared honestly before that.
