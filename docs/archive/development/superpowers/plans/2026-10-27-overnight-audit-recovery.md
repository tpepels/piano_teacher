# Overnight notation audit recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans for evidence-led fixes and focused red/green checks. The profiling and native-engraving workers have disjoint file ownership.

**Goal:** Establish the overnight audit's actual coverage and termination, correct the most impactful confirmed defects and verifier limitations, and make a measured recommendation about resumption.

**Architecture:** Preserve immutable retained audit evidence. Keep the native renderer and independent pixel verifiers; reuse exact full-image motion evidence rather than column-only candidate shortlists. Optimize only measured hot paths while preserving scoring, ownership and coverage.

**Tech Stack:** Python, NumPy, Pillow, Verovio, Godot/GDScript, pytest, cProfile.

**Spec:** User request dated 2026-10-27 in this conversation: inspect all shard/checkpoint results and diagnostic ZIP; profile unexpected-symbols before optimizing; fix confirmed recurring problems using source/Verovio/framebuffer evidence; focused regressions/corruptions and fast CI only; commit and push main. Findings travel with this plan in `docs/verification/overnight-audit-recovery-2026-10-27.md`.

## Global constraints

- No complete audit or 24-shard sweep.
- Preserve existing successful/failed/interrupted captures, checkpoints and ZIPs; hash manifest saved before analysis.
- No relaxed pixel thresholds, skipped source obligations or renderer-reported geometry as proof.
- Preserve source MIDI/XML events, hands, grading, fingering, fixed horizontal scale and continuous transport.
- All shell commands start with `rtk`; direct main implementation/push is explicitly authorized.
- Historical archive branches and preservation bundle remain intact.

## Review focus

- An ambiguous repeated pattern must not become a confident motion registration.
- Low-ink, different-size, frozen and reversed frames must retain strict treatment.
- An optimization must preserve exact candidate decisions and corrupted-negative detections.
- A reported missing tie/ledger may be an oracle failure; require actual source and pixel evidence before changing engraving.
- Completed checkpoints, timed-out cases, pending cases and source/measure coverage are different denominators.

## Task 1: Reconstruct and preserve the run

- [x] Record initial clean main `71cfdf4`; inspect worktrees.
- [x] Save hashes of all existing JSON/checkpoints/logs/archives before changes.
- [x] Compare ZIP summary with local shard 7; inventory all eight available shards and case receipts.
- [x] Inspect worker stacks, per-case stages, recorded termination and available kernel/system logs; distinguish handled signal, deadline and renderer rejection from OOM.
- [x] Record accurate case/pass/fail/pending totals and recurring first-failure categories in the final evidence report.

## Task 2: Profile and optimize unexpected-symbols

**Owner:** profiling worker; `piano_teacher/notation/extra_symbol_pixels.py` and new focused tests only.

- [x] Profile actual retained slow Peace/Hanon frames with bounded CPU/time/memory before changing code.
- [x] Identify measured hot path and implement only an exact optimization justified by those measurements.
- [x] Verify positive output equivalence and deliberately corrupted negatives at unchanged thresholds/coverage.
- [x] Record same-input before/after wall/CPU measurements and resource limits.

## Task 3: Repair strict structural motion registration

**Files:** `piano_teacher/notation/feature_pixels.py`; `tests/test_extra_symbol_shard_regressions.py` or a dedicated retained-frame test.

- [x] Reproduce `_frame_shift` returning `None` for both genuine 15 px Hanon frame steps while the existing full-2D matcher verifies them.
- [x] Add a failing retained-Hanon structural motion regression plus ambiguity/freeze/reverse/corruption controls.
- [x] Replace the column shortlist with exact 2D candidate evidence, retaining the 0.80 contour threshold and 0.02 competing-shift margin.
- [x] Run focused motion/structure tests and recheck a small set of retained real structure reports without rewriting them.

## Task 4: Correct confirmed engraving defects

**Owner:** engraving worker; native `view.gd`/geometry/glyph files and new focused fixtures/tests only.

- [x] Inspect retained Bill Evans tie and Ala ledger complaints against exact source XML, Verovio and native PNGs.
- [x] Change underlying engraving only if a genuine defect is established; otherwise document the verification limitation.
- [x] Add positive framebuffer and deliberate-corruption negatives for every correction; protect source identity and ordinary notation.

## Task 5: Review and deliver

- [x] Integrate independent worker evidence and request a final review of strictness, profiling and regressions.
- [x] Run focused tests and fresh `./scripts/verify-notation.sh --ci`; never start the full sweep.
- [x] Save compact durable forensic/profile/PNG evidence and unresolved categories in the report.
- [x] Verify retained audit hashes and archives, clean generated files, inspect status/worktrees, commit and push main, verify remote SHA.

## Continuation after main advanced (October 28)

- [x] Integrate onto clean main `6e56142`, preserving intervening native layout and application refactors and earlier fixes in `6301fab`.
- [x] Add outgoing boundary alpha/stroke constraints with source/preparation/repeat framebuffer positives and old-collision negative; ordinary repeat stays 96 px/beat.
- [x] Profile and implement bounded lossless photo-cache handoff with SHA-256 invalidation and strict negative/equivalence/resource tests.
- [x] Recover original local vector tuplet art without allocating a giant page; adapt scale to bitmap bounds; retain intrinsic opacity.
- [x] Keep Peace complete-bracket alignment/reference downsampling unresolved; verify recovered numeral positively and reject real erased/moved negatives.
- [x] Register brackets jointly against unchanged contour/hook/continuity gates; protect Moonlight plus five corruptions.
- [x] Review local vector allocation; fix confirmed over-rejection of valid large fragments.
- [x] Complete final native/cache review and fast CI, update evidence report and push main.

Final gate: 101 focused tests; CI 976 passed, 6 skipped, Godot main parse exit 0. All 67,349 retained hashes unchanged. Worktree prune completed; only main and intentional archives remain. Full audit not recommended yet; see recovery report for unresolved cases.
