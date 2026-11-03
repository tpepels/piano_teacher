# Supported notation release contract

The user's 23 October clarification replaces the former rule that every
nonverified obligation must block the entire application. Release readiness and
complete independent verification are separate claims. Existing ledgers and
their full denominators remain authoritative and unchanged.

## Decision

Use an explicit, versioned support policy alongside the existing independent
semantic and visual boundaries. Do not infer application support from a
detector's status or reason string. Unknown cases fail closed.

Each obligation has one release disposition:

- **Required supported evidence:** a mismatch is a correctness failure;
  unsupported, ambiguous or unverified evidence is a quality-gate gap. Both
  block release. Every visual aspect of the renderer's supported common
  notation stays required, including rhythm, stems, flags, dots, accidentals,
  connectors, signatures, barlines, placement and collision/extra-ink checks.
- **Inherent source limitation:** the source cannot uniquely establish an
  authorial fact, such as intended MIDI spelling, hand, voice or overlap
  pairing. Retain its original status and exact scope. It can be nonblocking
  only when independently checked, versioned interpretation rules pass and
  all related supported musical/graphical obligations pass.
- **Explicit capability outside supported scope:** name the limitation and
  keep it out of verified totals. This classification must come from a
  maintained capability contract and source facts, never from a failing
  detector or a score filename. A previously supported feature cannot be
  downgraded merely to obtain a green gate.

A MIDI file's absent authoritative written score therefore does not itself
block release. Its transcription must independently satisfy documented import,
hand assignment, timing/display, legal rhythm, tie, measure and source-identity
rules. Those checks are new required obligations, not a relabeling of the
authorial limitations as verified. Physical attack/release preservation remains
independently required. Orphan releases and zero-duration event handling are
verifiable import rules, not inherently unverifiable facts.

## Reports and integrity

Keep `complete` as the existing strong every-element claim. Add a separate
supported-scope decision and coverage, with every excluded limitation listed by
source and reason code. Full coverage tables retain unsupported/ambiguous rows.
Release readiness requires the supported-scope gate, complete source/case/window
inventory, immutable provenance, all required mutation tests and intact evidence.
Neither manual review nor a producer's `passed` flag can clear a blocker.

Separate structural/integrity errors from incomplete musical coverage in the
aggregator through explicit data fields. Do not filter error strings. Keep the
existing strict aggregation mode; CI can explicitly select the new supported
release scope. Independently replay MIDI rule checks from packaged original,
written and model artifacts at the release boundary where possible.

## Work already in progress

Retained-frame staff recovery and distinguishable adjacent-head assignment are
detector repairs. They do not make all dense notation verified. Remaining
common-notation detectors must supply per-feature image evidence and mutation
coverage; absent detectors remain blockers under this contract.

## Integration

Run development and corpus checks locally before pushing. Preserve the UX
corrections, manual BPM controls, fixed-playhead architecture and tested practice
behavior. Integrate shared framework/remediation fixes into the appropriate
dependent branches without duplicate implementations. Merge Phase 3, then Phase
4, then Phase 5 only after their required local and final hosted checks pass.
Record the exact revision and unresolved limitations; do not equate merging
framework code with certifying notation outside its supported evidence scope.

The chosen implementation reuses existing ledgers and adds a release disposition;
rewriting unsupported rows to verified would overstate evidence, while retaining
the former universal blocker would contradict the clarified MIDI release scope.
