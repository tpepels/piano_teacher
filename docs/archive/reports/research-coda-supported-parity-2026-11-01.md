# Coda Gate 2 — bounded strict parity subset

**Research status:** verified on **2026-11-01**. This is symbolic
author-output parity for selected examples, **not** production feature
readiness, visual fidelity of authored expressions, or evidence of teaching
effectiveness.

## Reference and proof

- Original, unmodified author: `annieetang/coda_backend@a4eb85dfc2bd418818ca9ff775c0a11ccccb3530` (unused database initialization stub only).
- Exact implementation that produced this certificate: `634a597a23234265d6fd52e7364bc7268023b557`.
- [Successful 4-minute-limited original-Coda workflow](https://github.com/tpepels/piano_teacher/actions/runs/41342300820), artifact `13097607435`: `real-source-voices.json` and `supported-subset.json`.
- Pinned manifest: `tests/fixtures/research/coda_supported_parity_v1.json` (all six source paths, source SHA-256 fingerprints, excerpt length, both source voices, all five operation settings and their independently reviewed expected outcome).
- Contract verifier: `piano_teacher/research/coda_parity_contract.py`. The gate compares the manifest with actual author-exported MusicXML, adapter native bare MusicXML, tied sounding notes and canonical grading `TimingPlan`, as reported by `scripts/probe_coda_upstream_scores.py`.

## Declared supported subset

| Tier | Cases | Meaning |
|---|---:|---|
| **Strict transformed** | **24** | Both **written note/rest/tie** representation and sounding note timeline match the author, and both really modify the original sounding timeline |
| Exact no-op | 6 | Identical author/adapter score and sounding result, but neither actually transforms the source notes; **no exercise-algorithm parity credit** |
| Sounding-only match | 10 | Author/adapter yield the same played pitches/timing but different written notation/rest/ties; **no strict written parity credit** |
| Guarded safety difference | 11 | Adapter deliberately prevents rewriting protected beams, tuplets, written rests, or cross-measure groups; do not reproduce the unsafe/unsupported output solely to match the author |
| Known upstream defect | 5 | Four dotted-grid truncation cases at quantization 3 and one invalid disconnected original tie |
| Author returns `None` | 4 | Original rejects the exercise; do not invent an author-parity success |
| **Total** | **60** | Every selected case accounted for, no dropped/missing case |

Of the 24 strict transformed matches: 7 occur in the selected two-bar
multipage source, 7 in the authored triplet fixture, 6 in the rest-bearing
triplet fixture, and 4 in the authored-beam fixture. All **12/12 sampled
source-voice MMRs** matched the pinned author. These are **sampled output
cases**, not 24 independent real-world scores, and not verification of the
full original Score/Part/Voice inventory.

The strict subset is identified by each `(fixture fingerprint, voice,
operation)` triple. No new score, parameter, quantization or chord level is
implicitly eligible. The supported operation settings are slowdown x2/x4,
alternating dotted 3:1 and 1:3, and one chordification width (2 × source
quantization). Other Coda chord levels and original batch exercise sets remain
outside the certificate.

**Crucial distinction:** `strict transformed` means *bare symbolic
written-and-sounding parity* on a source SHA. Verovio's full graphical
engraving, original author slurs/beams/directions, full transformed native
lesson playback and grading, physical MIDI, and measured teaching improvements
are separate unverified gates. No production Coda exercise strategy was enabled.

## Fail-closed acceptance conditions

For every declared case, the checker rejects:

1. A changed upstream commit, fixture SHA-256, excerpt bar count, missing or
   additional voice, missing operation, or an ambiguous/different 128-pitch
   MMR source array.
2. A changed written or sounding comparison status, an exception, or an
   upstream-`None` case silently promoted into parity.
3. A native written sequence that cannot be proved to reproduce the exact
   grading `TimingPlan`.
4. An exact author/adapter match with no actual change to source notes
   being promoted into the strict transformed category.
5. A sounding-only match being relabeled strict, or an unexpected safety
   difference/author defect being counted as a pass.
6. An unknown source case or discrepancy type (no generalized promotion
   from similar notation).

The pinned manifest is a *reviewed expected result*, not a feature flag.
The gate checks it against independent source differential execution.
`tests/test_coda_parity_contract.py` uses synthetic input and negative
mutations to test the verifier itself; its success alone is **not** the
author-parity proof. The separately bounded original-backend workflow must
also pass, and retains the full per-case traces for investigation.

To reproduce with the original source available:

```bash
python scripts/probe_coda_upstream_scores.py \
  --upstream /path/to/pinned/coda_backend \
  --report /tmp/coda-report.json
python -m piano_teacher.research.coda_parity_contract \
  --report /tmp/coda-report.json \
  --manifest tests/fixtures/research/coda_supported_parity_v1.json \
  --certificate /tmp/coda-subset-certificate.json
```

The separate `coda-upstream-parity.yml` job installs the author's required
`music21` and runs this with a pinned original checkout. Its complete report
and certificate have **14-day artifact retention**; the durable summary is
`docs/evidence/coda-2026-11-01-strict-subset.json`.

## Research boundaries and next work

This step establishes a *limited accepted comparison subset* rather than
modifying any algorithm to chase upstream implementation quirks. The adapter's
notation-preserving restrictions remain intact.

Remaining Gate 2 work: broader independent real-score repertoire, more
original chordification widths, original Score/Part/Voice output set parity,
complete source-annotation equivalence, actual Godot framebuffer/Listen/MIDI
feedback, physical MIDI and human learning evaluation. Each must receive its
own test evidence before general parity or production readiness is claimed.

See [issue #42](https://github.com/tpepels/piano_teacher/issues/42) and
`docs/research-coda-discrepancy-causes-2026-11-01.md` for the 26 specific
excluded/notation-only discrepancies.
