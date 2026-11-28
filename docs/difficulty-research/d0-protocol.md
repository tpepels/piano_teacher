# D0 — Corpus and evaluation protocol v1

Status: corpus and protocol established; independent annotation/reliability gate **OPEN**. No difficulty model trained or evaluated. Source revision 59885ba193938905082b9277b2910561cb04f8fb.

## Findings and method choice

The research question is local, one-hand technical diagnosis, not repertoire grading. The reviewed literature supports feature extraction, but does not supply validated technique-specific ground truth for our target.

| Work | What is supported | Limitation / decision |
|---|---|---|
| Parncutt et al. (1997), [paper](https://static.uni-graz.at/fileadmin/_Persoenliche_Webseite/parncutt_richard/Pdfs/PaSlClRaDe97_FingeringModel.pdf), pp. 341–382 | Rule costs for finger-pair span, crossings, position changes, weak fingers and black keys; compared with pianist fingerings of Czerny excerpts. | Right-hand melodic fragments with simplified timing, not general polyphony or validated absolute difficulty. Use as interpretable starting point; do not copy the table as ground truth. |
| Jacobs (2001), [abstract](https://doi.org/10.1525/mp.2001.18.4.505) | Revises span and other rules, reports improved agreement with fingering choices. | Full text paywalled in this review. Use actual keyboard geometry; no numerical constants taken from abstract. |
| Nakamura, Saito, Yoshii (2020), [paper abstract](https://arxiv.org/abs/1904.10237), [dataset](https://beam.kisarazu.ac.jp/saito/research/PianoFingeringDataset/) | Statistical fingering models and multiple human fingerings. | Agreement with a fingering is not proof of difficulty. Full preprint v2 retrieved; sections 3 and 6.2 support preserving multiple acceptable fingerings. Dataset explicitly nonprofit academic only. |
| Nakamura and Yoshii (2018), [Statistical piano reduction controlling performance difficulty](https://doi.org/10.1017/ATSIP.2018.18) ([publisher text](https://www.cambridge.org/core/journals/apsipa-transactions-on-signal-and-information-processing/article/statistical-piano-reduction-controlling-performance-difficulty/EB23810939F49C01EBF8C64C57F3DCC2)) | Local windowed negative log-probability models evaluated against annotated pitch/extra/missing errors in 90 performances of 30 works. Sequential models useful; Gaussian model reportedly strongest at available training size. | Competition performers, timing errors not included; both-hand error evidence, not technique labels. Compare density and pitch-transition baselines before HMM. |
| Ramoneda et al. (2022), [paper](https://arxiv.org/abs/2203.13010), tables 2–4, section 5.3 | Fingering-derived movement velocity gives 78±6% three-class balanced accuracy (DeepGRU), vs 64±8% note-only. | Piece labels weakly supervise nine-onset windows; attention is not validated causal localization. No use of durations in representation. |
| Ramoneda et al. (2024), [CIPI paper](https://doi.org/10.1016/j.eswa.2023.121776), [code/readme](https://github.com/PRamoneda/difficulty-prediction-CIPI) | Nine levels, publisher labels, reported 39.5% balanced accuracy and error statistic 1.1. | Full manuscript reviewed ([HTML](https://ar5iv.labs.arxiv.org/html/2306.08480), section 5.5.2); training 256-note fragments on whole-piece labels reduces nine-level accuracy substantially. Piece-level task only; not comparable to our transition metrics. |
| Ramoneda et al. (2024), [RubricNet](https://arxiv.org/abs/2408.00473), sections 3–6 | Per-hand symbolic pitch range, pitch entropy, mean onset interval, displacement, repetition descriptors, transparent ordinal aggregation. | Whole-piece aggregation loses local changes; article's example misclassifies Chopin Nocturne op. 9 no. 3. Descriptors explain the model rather than proving a technique diagnosis. |

| Miyaji, Sawada, Huang, Toda (2025), [paper](https://www.apsipa.org/proceedings/2025/papers/APSIPA2025_P441.pdf), sections III–V | Seven bar-level descriptors from basic pitch, duration and tempo; local estimates reused in piece-level regression. | No direct local difficulty labels; indirect global evaluation only. Pitch-based movement is useful as a comparator, but the assumption that half a bar always provides sufficient preparation ignores tempo and holds. |

Conclusion: D1 should first implement deterministic, explainable event/transition descriptors. D2 should compare a simple pitch-transition statistical model and ergonomic model; no deep network or exercise generation justified yet. A score alone cannot determine actual wrist rotation, tension, finger movement or personalized failure. Treat crossing candidates as implications of assigned fingers and pitch direction, not observed biomechanics.

## Dataset audit and usage policy (2026-11-28)

| Resource | Verified status | Decision |
|---|---|---|
| [PIG v1.12](https://beam.kisarazu.ac.jp/saito/research/PianoFingeringDataset/) | 150 scores, 309 fingerings, note onset/offset/pitch/finger; multiple annotators for 30-piece subset; nonprofit academic use only. | No download or redistribution in this project without permission; no severity annotations. |
| [Mikrokosmos difficulty v1.0](https://zenodo.org/records/6092709) | CC BY 4.0 archive, MD5 7e7f0f4097b614a1e6c403e63f30e6c3; table gives 147 scores (62/54/31); narrative also says 146. Semi-automatic OMR, corrections, length/tempo bias. | Optional global external benchmark, verify actual archive and edition rights before import. No localized ground truth. |
| [CIPI v0.1](https://zenodo.org/records/8037327) | Restricted downloads, nonprofit academic use, application requires affiliation; labels at whole-piece level. | Exclude until access and intended-use permission confirmed. |
| [64-score difficulty dataset](https://github.com/cperezs/piano-difficulty-dataset) | README describes MIT scripts, CC BY 4.0 annotated output, CIPI-derived reconstruction with source/output SHA256. Annotations are selected measure indices, not hands or technique. Paper citation/DOI still placeholders. | Do not treat unmarked measures as easy, annotation method unknown. No reconstruction without authorized CIPI access. |
| [RubricNet code](https://github.com/PRamoneda/rubricnet) | Implementation available, article CC BY 4.0. | No code or weights imported; verify code/license separately if later needed. |

No third-party score archive, code, weights or labels were copied into the repository. Public accessibility is not permission for commercial redistribution. Existing local MIDI encoding/edition rights must also be checked before releasing a corpus. This document does not establish permission.

## Fixed v1 corpus

See [corpus-v1.json](corpus-v1.json). 33 original synthetic cases across 16 families; 10 checked-in compositions, 31 exact half-open tick windows with context. The source MIDI blob IDs and PPQ were checked against the source commit. Windows are intentionally preselected by source position rather than a model or knowledge of learner errors. They are not certified hard/easy. Whole works are partitioned (all excerpts, hands, alternate fingerings, tempo variants and editions of the same composition stay together).

- Development: Bach prelude BWV 846, Mozart K.545 I, Satie Gymnopédie 1, Rachmaninoff op.3 no.2.
- Calibration: Bach invention BWV 772 and Joplin Entertainer.
- Held out: Moonlight I, Chopin nocturne op.9 no.2, Debussy Clair de lune, Liszt Liebestraum 3.
- Synthetic families are grouped, never random-split by individual variants; published synthetic labels are executable controls, not blind evidence.
- Original Pathétique case: blocked on exact movement/edition and hand. Keep separate from tuning; capture exact source revision, local fingering, beat/tick interval with preceding/following context before evaluation. The checked-in source is absent. Do not substitute Moonlight or an invented measure.

The repertoire is small: only four independent held-out compositions. This is a feasibility screen; it cannot establish generalization with precision. Expand with separately licensed, teacher-annotated works before D3 claims. The calibration set is deliberately not the test set.

The MIDI header scan establishes PPQ 480 for the ten works and source note tracks; some have pickups and changes of meter/tempo (Chopin and Liszt especially). Track number is not proof of hand. Preserve original tick windows, recover the meter map and align against the source notation; review hand/voice allocation and finger assignments before scoring. No claim that a MIDI file alone preserves ties, notation substitutions, or exact edition. If unavailable use unknown, not guessed truth. Each scored window at source tempo and 0.5× source tempo; apply full tempo map, document any missing markings. No global 100 BPM fallback.

### Synthetic controls

The JSON encodes original notes as onset/duration in quarter-note beats, MIDI pitch, hand, finger, voice, and optional tempo/meter maps, tie boundaries and substitution instructions. All expected features are construction labels for literal facts or hypotheses: a crossing *candidate* is not a measured physical crossing. Easy controls are candidates requiring human confirmation for severity. Geometry contrasts, release-time contrasts and speed contrasts are explicitly identified. Rotation/tension remain unknown. Do not train on held-out synthetic families, and do not count these controls as expert evidence. The labels do not prescribe a final detector threshold.

## Annotation protocol

Use [annotation-template.csv](annotation-template.csv) as a blank exchange schema. Export a score with stable attack IDs, source tick/measure locator, explicit hand, onset, release, effective fingering, context and evaluated tempo. No model predictions, highlighted candidate regions or existing learner outcomes shown. Use the selected hand only, with other hand printed as context if helpful; do not ask participants to perform painful stretches. For unknown or infeasible fingerings, allow alternatives and abstention. First annotate the source, then severity; the two questions have separate fields.

Recruit at least three independent piano teachers or experienced pianists. Record anonymized rater ID, teaching/playing background, voluntary comfortable hand-span description and whether judgment is score-only or actually played. Ask each rater to evaluate the same tempo/fingering conditions, give their preferred alternative if relevant, and state technique and uncertainty. Keep independent raw records. A separate adjudication may resolve obvious alignment mistakes, but preserve disagreements and reasons. No AI labels represented as pianist labels.

For each hand/condition annotate every destination attack (and first chord/held configurations without a predecessor), including negative and uncertain events. Use stable IDs; a localized difficulty interval is inclusive start/end attack IDs and half-open onset range for matching. Cross-bar issues are valid. Multi-label one row per category and target, plus a severity row for each attack. Long sequence labels expand to member attacks for evaluation; retain original interval for overlap. A missing annotation is unknown, never an easy example.

| Field | Values / decision |
|---|---|
| Feature type | displacement, wide span/octave, chord shape, chord transition, fast run/ornament, repeated pitch/finger, crossing candidate, substitution, held-while-moving, inferred reposition/rotation, rhythmic demand, tension (unobservable) |
| Presence | present / absent / unknown / not_applicable. Explicit evidence in free text. Distinguish observable facts and inferred motions. |
| Severity | 0 routine; 1 manageable with ordinary repetition; 2 specific technical practice likely needed; 3 severe bottleneck, cannot reliably execute at specified tempo/fingering after familiarization; unknown if insufficient basis. This is a judgment for a defined intermediate learner profile, not proof of the actual user's difficulty. |
| Confidence | low / medium / high, reasons; separately record whether target fingering is provided, preferred, inferred or unknown. |
| Localization | source tick + hand + stable attack IDs, interval, category; no measure-only label projected to each attack. |
| Observed performance | separate consented session: exposure count, attack accuracy/onset errors, inter-attack intervals, source/revision, actual BPM, device/transport state, validity exclusions. Empty during D0. |

Pilot on 12 development hand-windows (six per hand, balanced easy/hard candidates chosen before model outputs, plus 8 synthetic contrast cases), three raters independently. Randomize order with seed 20261128; separate tempo variants so memory does not drive scores. Check pairwise agreement per category, positive agreement, ordinal Krippendorff alpha (unknown excluded with coverage), severity distribution and hand effects. Review disagreements; clarify rubric and repeat pilot on new development windows if needed. Do not show held-out labels to model developers until protocol/model frozen.

## Baselines and locked evaluation

Unit: destination attack per hand, with 2 s preceding/following context (score manifest includes at least a four-quarter-note context; extend if 2 s is not covered). Aggregate within composition before cross-composition comparisons; report individual results. Primary positive = expert consensus severity ≥2 (at least two independent ratings ≥2 with at least three valid ratings). Negatives require at least two ratings 0 or 1 with at least three valid ratings. Unknown/disputed/insufficient evidence remains unscored; report fraction. For categories majority present/absent separately. Calibration uses development-fitted parameters, one fixed calibration threshold. Do not optimize against held-out.

Baselines (specify now, implement D1/D2):
1. Constant severity / no intervention: scores zero at every attack, never flags. Provides specificity baseline, not a competitive AP model.
2. Note density: attacks per second in centered 1 s window, chords counted once; note count per second separately as sensitivity baseline.
3. Pitch displacement: absolute difference of arithmetic mean MIDI pitches of adjacent attack groups. No fingering; one scalar per destination, first attack unknown.
4. Uniform measure: broadcast max density score of the measure to attacks; exposes localization loss.
5. Simple combined logistic/ordinal model using density, displacement and chord cardinality/span (trained only on development), optional Gaussian transition likelihood baseline inspired by Nakamura. Choose strongest baseline by calibration AP, freeze thresholds.

Primary metric: attack-level average precision for severity ≥2, composition-macro mean (report micro AP, each composition, prevalence; AP undefined when no positives, report separately and retain negatives in FPR). Threshold metrics precision, recall, FPR on explicitly easy controls; abstentions on valid positive events count as missed for recall; coverage separately. Per feature report precision/recall/F1 with unknown excluded and raw denominators. One-to-one matching for localized intervals of same hand/category, attack-ID IoU ≥0.5 (maximum matching; duplicate predictions FP); also strict attack matching and boundary offsets. Severity weighted kappa/MAE, probability Brier/reliability diagrams only for probabilistic models. Compare pairwise ordering of contrast cases and invariance of actual pitch/fingering facts under tempo changes.

### Proposed pre-tuning gates (not empirically justified yet)

These are conservative feasibility targets selected for the application, not published consensus or measured performance. Lock or revise based ONLY on independent pilot reliability, before any detector tuning; record a signed protocol version. Never move after held-out evaluation.

| Gate | Initial proposal |
|---|---|
| Rater pilot | Ordinal alpha ≥0.67; ≥0.60 positive agreement for each adequately sampled observable category; ≥85% valid severity labels. If not, revise rubric/limit claims. |
| Deterministic factual controls | 100% of constructed exact facts/unknowns; no assertion of observed tension/rotation or unsupported substitution. |
| Real feature recognition | Precision and recall ≥0.80 per supported observable category, ≥20 positive and ≥20 negative events from ≥3 compositions, both hands represented. Otherwise inconclusive; report separate rare-technique strata, not pass via pooled metric. |
| Local bottleneck detection | Composition-macro AP improves ≥0.10 absolute over strongest baseline; precision ≥0.80, recall ≥0.70 at frozen threshold; valid scored coverage ≥0.90. |
| Easy controls | FPR ≤0.05 among expert-confirmed routine attacks; ≤10% of expert-confirmed easy windows contain any intervention. Require ≥100 easy attack observations across ≥4 compositions, ≥20 easy windows across ≥4 compositions; do not claim pass on tiny denominator. |
| Localization / severity | IoU-based interval F1 ≥0.70, weighted kappa ≥0.60 on valid expert severity. |
| Generalization | Report composition-cluster bootstrap 95% intervals (2,000 draws, fixed seed). For superiority require paired AP difference interval excludes zero after expanded held-out corpus; v1 four compositions alone is exploratory. Stratify each hand, tempo and category; no unsupported category authorized. |

No gate is passed based on this document. Human data must establish the final numerical thresholds before model fitting. If the required denominators/coverage or agreement are absent, status is inconclusive, not successful. If predictions overflag melodies, stop. Never authorize D5 from weak global ranking or synthetic success alone.

## Reproduction and outstanding work

From the checkout run `python3 docs/difficulty-research/check-corpus.py`. This is a corpus integrity check, not model accuracy. It verifies pinned existing file blobs, synthetic IDs/timing and split isolation. Preserve manifest and annotation version with each run. Keep human annotations and prospective performance logs separately with consent and provenance; no automatic upload of personal MIDI.

D0 performed: research review and licensing triage, byte-pinned repertoire selection, exact synthetic controls, split, rubric, blank annotation schema, baseline specs, proposed metrics/gates, integrity command.

D0 remaining: independent pianist recruitment/ratings, actual source edition/hand verification for repertoire, original Pathétique source, pilot reliability calculation, user sign-off of final numerical thresholds. External datasets not downloaded/reconstructed (rights/access and no need for primary controls); Jacobs full text still unavailable and excluded from numeric rules; full Nakamura and CIPI manuscripts now reviewed. No independent results are fabricated. D1 may implement pure factual feature extraction after review, but **D0 exit remains open** until human reliability and final criteria are established, and no model tuning or production integration is authorized.

## D0 completion follow-up

See [pilot-plan.json](pilot-plan.json), [pilot-workflow.md](pilot-workflow.md) and [references/README.md](references/README.md). The exact development pilot conditions are frozen, a public-domain fingered Pathétique reference is preserved separately, and the operational annotation/reliability workflow refuses incomplete or unknown evidence. The original user's source and human ratings are not present. D0 is not marked passed until actual independent pilot evidence and threshold sign-off are available.
