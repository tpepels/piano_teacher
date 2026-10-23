# Supported notation release implementation

**Goal:** enforce the supported-feature release contract without losing source
coverage or claiming unverifiable authorial facts.

**Spec:** `docs/superpowers/specs/2026-10-23-supported-notation-release-design.md`.

## Constraints

- Keep semantic and visual verification independent; expected facts never come
  from renderer geometry or production transcription output.
- Preserve the original 17 × 3 × 2 release corpus and supplemental MIDI inventory.
- Keep current shape, registration and grading thresholds; no score exceptions.
- Unsupported supported features and ambiguous/unverified supported evidence block.
- Missing sources, windows, ledgers, provenance, mutations or artifacts block.
- Manual −5/+5 BPM, progression and fixed-playhead behavior remain protected.

## Tasks

1. **Retained-frame detector fixes** — review and verify the pending changes in
   `pixel_proof.py`, `phase3_pixels.py`, `raster_matching.py` and their real PNG
   regressions. Preserve erased/moved/borrowed-ink negative cases.
2. **MIDI interpretation rules** — add `midi_transcription_rules.py`, its mutation
   tests and documentation. Integrate a mandatory `midi_transcription_rules`
   obligation into the independent semantic contract/inventory and runner.
3. **Supported release policy** — add `support_policy.py` and policy tests;
   separate integrity and completeness diagnostics in `aggregate_phase3_corpus.py`.
   Update `audit_native_release.py` to retain strict completeness while reporting
   the new supported-scope decision. Test missing rule proof, unknown constructs,
   relabeled supported failures, forged source bindings and absent artifacts.
4. **Whole-piece graphical evidence** — extend per-feature independent pixel
   reports and `visual_coverage.py` integration for supported rhythm, stems,
   flags, dots, accidentals, rests, signatures, barlines and connectors. Each
   detector needs actual retained evidence and corrupt/erase/move mutations;
   unsupported cases remain named gaps until resolved.
5. **Application/UX verification** — finish the remaining actual-feedback review,
   rerun the complete local suite and workflow equivalents, inspect new raw PNGs
   and retain diagnostics. Keep these corrections separate from legacy cleanup.
6. **Revision-bound corpus and ordered merges** — regenerate required semantic,
   visual, mutation and artifact evidence; update CI to select the explicit new
   release scope. Push validated logical commits, verify hosted checks, merge
   dependent phases in order and verify resulting `main`.

## Review focus

- An unsupported-status substitution must not exempt a supported symbol.
- A missing MIDI rule row or partial rule inventory must remain blocking.
- A source limitation must not hide an actual pitch, release or visual mismatch.
- Shared or adjacent pixels must not conceal a missing distinct glyph.
- Passing source/ledger integrity must never imply complete graphical proof.

Progress is recorded by test output and immutable evidence, not task labels.
