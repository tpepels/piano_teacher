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

## 2026-11-16 — correction: strip placement was not a production defect

The "repair 1" production change (`f0da11e8`, refined in `ee368bca` and
`89874c84`) is **withdrawn**; `stream_lifecycle.gd` and
`stream_retained_lifecycle.gd` are back at their `3af263e2` content.

- Sub-pixel ink (exact axis) changed the sampling phase of the point-sampled
  glyph textures and broke `test_full_notation_difficult_cases[hanon-37]`
  (gate at `89874c84`: shard 3, 1 failed).
- Snapping the reported head positions instead broke the exact-projection
  and constant-travel contracts (`test_recovery_motion`, `test_phase1_camera`,
  `test_preparation_ink`, `test_fingering_real_placement`, 19 failures).
- So the existing behaviour is the contract: reported positions are on the
  exact world axis; Godot draws a strip's Control window, and the ink and
  status ink inside it, at whole pixels (at most 0.5 px away).
- The real defect was the note-status test model, which placed the authentic
  head alpha at the unsnapped position. It now applies the window's pixel
  snap (`_window_snap`, from the reported `clip_x`), and a new control proves
  on the baseline frame alone that the snapped placement explains the
  photographed head better than the unsnapped one. Error per head is at most
  0.24 against the unchanged 6.0 / 32.0 limits.
- Lesson recorded for the next agent: run the placement-sensitive modules
  above before changing strip geometry.

## 2026-11-16 — gate evidence at `48bf36e2`

- `ci-full.sh --all --fail-fast`: PASS 4/4 — 1296 passed / 4 skipped,
  1204 / 1 skipped, 1324, 1365 / 1 xfailed (5,189 passed in total).
  Skips: no system SF2 for `test_sampled_piano`, and parametrized cases
  that do not apply in `test_fingering_obstacle_geometry`.
- `ci-smoke.sh` 865 passed; `check-godot-syntax.sh` OK;
  `verify-hybrid-workflow.sh --focused` and `--corpus` finished 0;
  `ci-scope.py --check` complete (618 artifacts).
- **Not met:** `ci-scope.py --check-unquarantined` — one strict xfail left,
  the Chopin Nocturne Op. 9 No. 2 bars 13-16 symbol proof (131 errors).
  Blocked on the glyph minification decision described above. After that
  decision the remaining verifier items are: stem disambiguation next to a
  natural sign (prototype 5 -> 8 of 10 beams), hook boundary tolerance at
  beat 7.5, and head registration of the periodic figure at beat 12.
- Physical USB/Bluetooth MIDI acceptance: not run, cannot be run headless.

## 2026-11-16 — option 2 experiment (display-scale glyph artwork), not committed

Owner asked to try rasterizing at display scale. Prototype: every texture
draw in `glyphs.gd`, `symbol_painter.gd` and the brace in `view.gd` goes
through a helper that resamples the texture once (premultiplied Lanczos) to
the size it is shown at and draws that copy 1:1.

- Look: the natural sign keeps both strokes at every clock, 64th flags are
  clean, and the ink is crisper than with mipmaps.
- Full suite without fail-fast: 5,181 passed, 8 failed (all four shards run).
  `test_note_status_framebuffer` x3, `test_extra_symbol_pixels` x1,
  `test_native_paint_components[symbols]`, `test_native_boundary_clearance`
  x1, `test_native_singleton_tuplets[False]`, and
  `test_full_notation_difficult_cases[hanon-37]` (2 stem errors).
- Quarantined Chopin case: 131 -> 226 errors (stems 52, beams 43,
  accidentals 34): the verifiers expect hard-edged ink.
- Known prototype defects, not just thresholds: the cache is keyed by
  texture RID, which can be reused after a texture is freed ("suppressing
  artwork changed unrelated score ink"); status erase/core/fill passes draw
  differently sized copies, so the exact-tint core no longer holds; thin
  stem sprites lose brightness when resampled.
- Outcome: feasible but not a drop-in. Tree restored to `b99e6cbe`; nothing
  from the experiment is committed.

## 2026-11-16 — option 2 adopted (owner: "notation correct, not identical pixels")

Production: `_display_texture` / `_draw_fit` / `_draw_fit_region` in
`glyphs.gd`; every texture draw in `glyphs.gd`, `symbol_painter.gd` and the
brace in `view.gd` uses them. Area-average (mipmap-based) premultiplied
filter, cache keyed by texture instance id with a weak reference.

Verifier and test changes, each with its measured reason:
- `pixel_ink.rasterize_outline`: 4x supersampled coverage at a sub-pixel
  phase, binarized at `INK_COVERAGE` .63 (the cut `bright()` applies);
  `raster_matching` and the scalar oracle `symbol_pixel_proof._match_glyph`
  take the best of 8 phases. Chopin accidentals 17 -> 1 unverified.
- Unexpected-symbol scanner (`extra_symbol_pixels._template`) keeps the
  original generous cut (`SCAN_COVERAGE` 96/255).
- `stem_pixels._stem`: a shaft may end within .15 staff space of a head
  centre (antialiased head rim); Hanon 37-40 back to 0 errors.
- `procedural_rest_ownership`: same-rest axis tolerance 3 -> 5 px (3.25 px
  observed drift; a different rest is a bar away).
- `test_native_singleton_tuplets`: only a 2 px antialias contact rim of the
  removed artwork may change (max 48/255).
- `test_native_boundary_clearance`: flag ink measured as coverage, ratio
  .85 -> .75 (a clipped flag loses about half).
- `test_note_status_framebuffer`: exact tint within 16/255 (was 8; one rim
  pixel at 11).
- `test_native_tie_attachments`: tie tips measured through connected pixels
  of >= 25% coverage (tapered tips were real ink below the bright cut; the
  tie starts 4 px from the head, as Verovio places it).
- `test_native_symbol_pixel_proof`: whole and half rests have identical
  bounds; their margin is required against every other rest family, while
  their identity comes from rails (`test_phase3_rest_orientation`).

Evidence on the working tree before commit: all four shards without
fail-fast — 1245 passed / 1 xfailed, 1267 / 4 skipped, 1323 / 1 skipped,
1354. The Chopin case stays quarantined (re-measure after this commit).

## 2026-11-17 — gate evidence at `4f70c2c2` (option 2 + beam measurement)

- `ci-full.sh --all --fail-fast`: PASS 4/4 — 1245 passed / 1 xfailed,
  1267 / 4 skipped, 1323 / 1 skipped, 1354 (5,189 passed).
- `ci-smoke.sh` 865 passed; `check-godot-syntax.sh` OK; hybrid focused and
  corpus exit 0. Quarantine: still the one Chopin entry.
- Beam verifier (`4f70c2c2`): thickness from ink coverage; columns within
  .3 space of a reference level transition are recorded but not compared.
  Chopin beam groups 4 -> 9 of 10 verified; case errors 153 -> 92.

### Chopin 13-16 remaining (92 errors), captured at an 11 px staff gap
The audit fits bars 13-16 into 1536 px, half the app's practice size
(Hanon renders at 21.9 px). Remaining groups:
- flags 14 + flag absence 7 + dependent rhythm 7: down flags score
  .60-.70 Dice (needs .72); two of them separate 1 from 2 flags by only
  .02-.03. At this size the 16th flags are two very thin strokes. Lowering
  the threshold here would hide a genuine legibility question.
- beam group beat 12 (12 per-note + 1): every witness is under the playhead
  or has an ambiguous image translation (periodic figure).
- rests 8 + 4 + 4 + 4 + 4 ownership rows: rest body contour/ownership.
- structure: meter 2, key 1, measure 2, barline 2; tuplet 3; accidental 2;
  stem 2; tracking/ownership 2. Not yet examined.

## 2026-11-17 — Chopin audit at the app's real display (owner chose option 1)

Correction of an earlier note in this log: the 11 px Chopin capture was not
an audit artefact. The production view chooses the staff gap from the
passage density and the available width (candidates 22/17/14/11/8.5 px).
The app also scales its whole interface (main.gd `_configure_ui_scaling`):

| Screen | Logical score area | UI scale | Staff gap on screen |
|---|---|---|---|
| 1220x780 window | 1156x591 | 1.00 | 11 px |
| 1536x960 | 1216x610 | 1.20 | 13.2 px |
| 1920x1080 | 1358x611 | 1.35 | 14.85 px |
| 2560x1440 | 1358x611 | 1.80 | 19.8 px |

Changes:
- Production: `glyphs.gd _screen_scale` resamples artwork to PHYSICAL pixels
  (canvas transform x window final transform). Before, art was reduced to
  its logical size and the window then enlarged it again (soft ink on every
  scaled screen).
- Audit: `AuditCase.viewport` / `ui_scale`; the harness draws the logical
  score at that scale into a physical framebuffer and reports every
  coordinate in framebuffer pixels. Identities of default cases are
  unchanged (`case_types.case_fields`, `aggregate_shards.case_identity`).
- The Chopin case now runs as on 1920x1080: (1358, 611) at 1.35.
- Visible-note obligation: a head counts only when it lies wholly right of
  the 29 px gutter (it was required while still half clipped).

Chopin 13-16 at the app display: 128 errors (92 at 1536x520). Flags are
plainly two flags on screen but still score .59-.69 Dice; one eighth flag
separates 1 from 2 flags by .003, so the flag measurement itself is the
next item, not legibility. Also open: one beam group, ledgers 4, stem
attachment 4, meter/key/barline/measure 7, tuplets 3, motion transition 1,
one unexpected-symbol contour, ownership 2.

Full suite on the working tree before commit: shards 1-3 green, shard 4
one failure (job identity hash, fixed above).

## 2026-11-17 — gate evidence at `594e1ead`

- `ci-full.sh --all --fail-fast`: PASS 4/4 — 1245 passed / 1 xfailed,
  1267 / 4 skipped, 1323 / 1 skipped, 1354. Smoke 865 passed, Godot
  syntax OK, hybrid focused and corpus exit 0.
- Observed once, not reproduced: in the first shard-2 run at this commit
  `test_verification_runner_failures.py::test_outer_exit_packaging_defers_signals_and_keeps_the_first_status[2-False-False]`
  failed. The trace shows `verify-notation.sh` finished packaging and exited
  with the audit status 23 because its SIGINT trap never counted the signal
  (`first_signal_status` 0). That test case sends SIGINT to the bash pid only
  (not the process group) while bash waits for a foreground child. Neither
  the script nor the test changed in this work. It passed in the preceding
  full run, 48 of 48 isolated runs, and the shard-2 rerun on the same
  commit. Next agent: if it recurs, investigate bash's deferred SIGINT
  handling for a foreground child (wait-and-cooperative-exit) in
  `scripts/verify-notation.sh`; do not quarantine it.
