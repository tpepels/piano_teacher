# Coda: note-output equivalence and independent learning evaluation

**2026-11-02. Status: expanded software evidence, no blanket original
backend output parity and no measured learning effect.**

## 1. Actual note-level production audit

Every **emitted** Coda MIDI stage is now checked independently of its
generator by `piano_teacher/research/coda_live_note_audit.py`.
The audit validates the original source attack ID, source index, pitch,
hand, channel and track, and checks that note-on/off timings remain finite
and within the selected score excerpt. It rejects incomplete terminal
performances, duplicate source IDs, an unmarked timing change, or a
supposed rhythm transformation that changes no MIDI event.

It also checks each stage's actual `TempoMap` x2/x4 slowdown BPM
and the same `expected_note_seconds()` function used for MIDI grading.
No attempt is omitted silently; the bounded CLI
`python -m scripts.audit_coda_live_notes --output /tmp/coda-notes.json`
exits unsuccessfully on a rejected independent MIDI fixture.

**Observed:** all 16 independent MIDI corpus fixtures and all 134
generated exercise stages passed, with zero rejected fixtures.
See [bounded CI 41459191110](https://github.com/tpepels/piano_teacher/actions/runs/41459191110)
and its attached JSON artifact for every audited stage.

This proves source-identity and executable note-clock consistency
under the selected test corpus. It does **not** compare each generated
MusicXML pitch/rest/tie to the original author's output.

## 2. Original author parity: remains bounded

The pinned original Coda backend consumes **MusicXML**, while the
product consumes MIDI. Author operations can return `None`, produce
invalid disconnected written ties or change/destroy source attacks.
Our adapter deliberately rejects such cases.

Previous author differential evidence:
[the accepted strict subset](research-coda-supported-parity-2026-11-01.md)
found **24 strict transformed matches** from **60 selected cases**,
with every other observed outcome classified. The independent
[causal discrepancy register](research-coda-discrepancy-causes-2026-11-01.md)
explains the observed rest coverage, written subdivision, source-beam,
tuplet, meter and upstream-defect divergences. The
[original excerpt/catalog contract](research-coda-author-excerpt-contract-2026-11-02.md)
is separately verified at the pinned author SHA.

Full blanket original-author note-by-note equivalence for every
playable catalog alternative is **not established** and is not a
sensible safety acceptance criterion for known invalid outputs.
For production, the fail-closed source-note and grading-clock
contract is mandatory; historical author-output comparisons remain
a separately labeled research measurement.

## 3. Independent pedagogy comparison: reproducible but unobserved

Added `piano_teacher/research/coda_pedagogy_pilot.py`,
`scripts/evaluate_coda_pedagogy.py`, and
`tests/test_coda_pedagogy_pilot.py`, following the
[prospectively specified pilot design](coda-independent-pedagogy-pilot-2026-11-02.md).

For consenting human players, the tool creates concealed,
deterministic, 1:1 randomized A/B strategy allocations via HMAC,
then analyzes **independent physical-MIDI** pre/post recordings of
the same complete original score at identical BPM after
15 minutes of practice. It requires comparable assessment version,
piece, training exposure, source attack count and matching
allocation, and computes the pre-specified within-piece difference
in accuracy gains with a permutation test.

This prevents the typical invalid "Coda is better" assertion based
only on synthetic MIDI, number of exercise stages or internal
mastery scores. The algorithm is tested with synthetic records to
verify its mechanics, not to infer real learning.

**No real human outcome data have been collected.** The study
requires participant consent, controlled practice allocation,
external preregistration and a retention follow-up to support
any efficacy claim. Software alone cannot fill that evidentiary gap.

## Verification

- [Coda research and full-stage audit 41459191110](https://github.com/tpepels/piano_teacher/actions/runs/41459191110):
  **227 passed, 1 skipped; 16/16 fixtures and 134 emitted stages audited**
- [Fast application contracts 41459191172](https://github.com/tpepels/piano_teacher/actions/runs/41459191172):
  **398 passed, 6 skipped**
- [Pinned author catalog source 41450764682](https://github.com/tpepels/piano_teacher/actions/runs/41450764682):
  verified excerpt input and operation parameters

**Bottom line:** comprehensive note ownership and clock parity for the
current MIDI corpus is tested. Full historical MusicXML note-output parity
and the comparative teaching advantage remain open scientific claims.
