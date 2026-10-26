# Native audit ties and ledger proof implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the parent-owned
> tasks and bounded disjoint workers for atlas/native code and ledger diagnosis.

**Goal:** Resolve one or two independently reproduced recurring audit causes,
without changing source music or weakening independent verification.

**Architecture:** Retain the existing model, Verovio atlas, native compositor,
pixel verifier and bounded audit runner. Correct generic tie endpoint artwork
for flags using actual Verovio engraving. Consider a second ledger correction
only after a separate current-source/current-renderer reproduction.

**Tech stack:** Python, Godot GDScript, Verovio, existing PNG/SVG pixel proofs.

**Spec:** User handoff "Resolve remaining native notation audit failures",
26 October 2026. The evidence/progress report is
`docs/notation-audit-progress-2026-10-26.md`.

## Constraints and review focus

- Work directly on main; preserve archives, bundle, user data and fingerings.
- No complete corpus audit or infrastructure redesign. Existing two-worker
  defaults, memory limits, watchdogs, checkpointing and provenance remain.
- Historical captures are diagnostic evidence only until their exact current
  source, canonical configuration and renderer hashes pass compatibility.
- Keep pitches, MIDI clocks, velocities, performing hands and grading intact.
- Preserve the ordinary half-note template and existing unison/chord/beam/
  tuplet/repetition/preparation behavior; no arbitrary shortening or masking.
- Exercise flagged start and end notes, both stem directions, chord members,
  polyphonic ties, cross-bar continuations, shifted heads and compact staff
  spacing. Endpoint geometry must come from independently visible heads.

## Task 1: historical baseline and current reproduction

- [x] Inventory shard 0 and both ZIPs without rerendering. Save source/hash/
  family data separately. Current historical inventory: 630 completed,
  332 passed, 298 failed, two capture errors; 301 summary error entries.
- [x] Check canonical configuration and renderer/source provenance. No retained
  root capture is directly compatible with current code; preserve all files.
- [x] Reproduce Autumn Leaves measures 37–40 with the current canonical
  pipeline at clocks 3.6, 4, 11.6 and 12. Keep the before capture and reference.
- [x] Add `tests/test_native_audit_ties.py`; observe the expected RED: six of
  eight ties verify, G4 (`midi-t0-e360`) and F4 (`midi-t0-e389`) do not.

## Task 2: authentic flag-aware tie endpoints

**Files:** `notation/assets/ties.py`, native `glyphs.gd` and `view.gd`;
`tests/test_native_audit_ties.py`, related existing attachment tests.

**Interface:** Extend the existing `native_tie_templates` atlas. Retain the
ordinary `up`/`down` entries and add genuine flag-aware contours with explicit
source head-family metrics. Choose them using actual rhythm, stem direction
and tie side; do not key behavior to a source ID or lesson.

- [x] Add failing atlas/native tests for flagged starts and ends. Compare the
  exact original half-note entries and reference head-edge clearances.
- [x] Generate the appropriate contour and endpoint clearances through
  Verovio. Version the existing tie atlas cache; no new rendering subsystem.
- [x] Use the correct source first/last head-family centres and unchanged
  native visible-head offsets when mapping the contour to the beat layout.
- [x] Pass the actual Autumn 8/8 independent tie proof and deliberately erased,
  detached, straightened and broken curve negatives on both affected pitches.
- [x] Verify original attachment, chord/voice, shared/unison and source-owner
  regressions. Inspect real before/after PNGs and full reference SVGs.

## Task 3: ledger diagnosis, integration and delivery

- [x] Inspect representative retained ledger failures with exact source pitch,
  clef and current staff assignment. Reproduce only a small affected case set.
  Implement a second correction only if its root is demonstrable; otherwise
  record the unresolved observation and its evidential limitation.
- [x] Run affected focused suites, then `./scripts/verify-notation.sh --ci`.
- [x] Independently review the changes and corruptions. Complete the concise
  progress report, preserving historical counts as historical counts.

Delivery remains the authorized commit/push to main after final status,
worktree and preservation checks. No temporary branch or worktree was created.

## Execution rulings and verified result

- The tie-only candidate-span shortcut was also a confirmed verifier defect:
  a new complete-proof assertion in the existing actual whole-head attachment
  regression failed before the correction. Its new admissible lower bound
  derives from the same `.9` endpoint/head-rectangle distance test. Slur
  pruning and every final acceptance threshold are unchanged.
- The second family is a verifier correction, not a ledger renderer rewrite:
  independent external glyph alpha removes transparent padding from measured
  head edges. Six new corruptions preserve the strict three-pixel wing test.
- A shared tie destination rectangle also reserves the corrected ink for
  fingering layout; the old reservation fails a real numeral-clearance test.
- Focused final scope: **199 passed**; expanded fast CI: **658 passed, 6 skipped**,
  followed by Godot parse success, overall exit 0. Independent review approves.
- Autumn: 8/8 ties at 1536×520 and 1216×455; original obstructed frames still
  fail; all 34 source records and 48 notation events are identical. Changed
  pixels stay inside the two independently measured tie corridors.
- Final fresh Liszt 78 capture: 2/2 ledgers, all 45 native PNGs identical to the
  earlier producer. Whole-case dot/meter/key/rhythm limitations stay explicit.
- Exact evidence, source IDs, current versus historical classification and
  the next nine-case bounded verification command are in the progress report.
