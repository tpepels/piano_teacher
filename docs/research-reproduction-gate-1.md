# Research reproduction — gate 1 source audit
Date: 2026-10-30. Repository: tpepels/piano_teacher, main.
Status: **RubricNet reference inference, official held-out evaluation and
source-to-model MusicXML oracle passed**. App-native extractor and the other
research systems remain incomplete; no pedagogical efficacy claim.

This supersedes the *research fidelity* meaning of "complete" in the Step 2–4
engineering trackers. Those trackers still describe tested **adaptations**.
A strategy is not counted as reproduced until there is reference parity,
specified applicability, independent test data and documented deviations.

## Traceability matrix

| Method / primary source | Published algorithm and required components | Existing Piano Teacher mapping | Source/model availability | Missing evidence / reproduction gate |
| --- | --- | --- | --- | --- |
| RubricNet, Ramoneda et al. 2024, arXiv:2408.00473 | Twelve symbolic descriptors (six per hand) in the published camera-ready assets, scaler per fold, descriptor-wise affine+tanh, aggregation, nine-class ordinal sigmoid, five trained folds and interpretability | `difficulty.py` and `FeatureGatedStrategy`: untrained rule-based features only | **Public MIT repository, training code, extractor, 5 camera-ready checkpoints and scalers**: https://github.com/PRamoneda/rubricnet (verified master at `3ff4a9342948b9588541a2a8524eab68045f6001`) | Validate published extractor on reference score, verify exact input ordering against training, safely export each scaler/checkpoint, match upstream predictions on fixed feature vectors and full MusicXML; held-out 9-class validation |
| Coda, Annie Tang 2025, Dartmouth thesis 76 | Three-level Score–Part–Voice MMR; part splitting, tempo shaping, polyphonic chordification, dotted rhythms | `exercise_strategies.py` Coda prefix stages; `exercise_contracts.py` restricted timing/tempo/chord blocks; `exercise_pipeline.py` | Thesis abstract verified: https://digitalcommons.dartmouth.edu/cs_senior_theses/76/ ; full PDF retrieval presently blocked (HTTP 403); reference source and models **not verified** | Obtain full thesis/reference examples or source; implement and compare all four algorithms including arbitrary polyphony, source graph, notation and temporal invariants |
| Fukuda et al. 2015, SMC, Kyoto | Instrument-specific isolated-note calibration, CQT audio features, supervised NMF transcription (beta divergence), chroma DTW score-to-audio alignment, error comparison, three simplification patterns | `FukudaStrategy` implements only partial chord/isolated-leap thinning; MIDI grading is not the paper's audio algorithm | Full paper available: https://sap.ist.i.kyoto-u.ac.jp/EN/bib/intl/FUK-SMC15.pdf ; original source code, recordings and pretrained piano basis **not verified** | Audio calibration + NMF/DTW parity on documented recordings, ground-truth error matching, all three simplification rules, comparison with published examples |
| Piano Tutor, Dannenberg et al. 1990 | Score following and tempo tracking, error-cause inference, prioritized feedback rule base, student skill model, prerequisite-ordered lessons and adaptive curriculum | `diagnosis_policies.py`, `remediation.py`, `practice_history.py` supply simplified repeated-error routing | Papers available at https://www.cs.cmu.edu/~rbd/bib-ptutor.html ; original complete expert rule base / code **not verified publicly available** | Extract explicit rule table and student-state representation; reconstructed rules individually labeled; validate against paper cases, expert annotations and simulated learners |
| Suzuki, M. 2023 | Notation-to-notation piano score rearrangement into multiple difficulty levels | No trained sequence transducer | Open paper: https://doi.org/10.1186/s13636-023-00321-7 ; trained weights/code **not verified** | Read complete tokenization / training / decoding method; determine available corpus and weights; document feasible fidelity before scheduling |
| Moringen et al. 2024 | Gaussian-process practice-mode policy using learner state, performance feedback, expertise and expert-learner demonstrations | `RepeatedErrorPolicy` is deterministic; it is not a Gaussian process | Paper: https://proceedings.mlr.press/v257/moringen24a.html ; original trained policy/paired teacher–learner data **not verified** | Reproduce state/action/observation representation; acquire expert training trajectories or collect ethically; train GP and validate next-mode recommendations |
| Hardware and pedagogy | Physical MIDI/audio sync, original-score retention and counterbalanced learning experiments | Headless timing regressions and backend simulation | App and tests in main | Real MIDI/audio protocols, multiple teachers and participants, pre/post and delayed-transfer studies; cannot pass in headless CI |

## RubricNet: verified official source and assets

**Canonical upstream ref:** `PRamoneda/rubricnet@3ff4a9342948b9588541a2a8524eab68045f6001` on `master`. Note `main` in that repository contains an unrelated placeholder README; **do not use main**.

Model structure from `rubricnet/rubricnet.py`:
`score_i=tanh(weight_i * scaled_descriptor_i + bias_i)`;
`S=sum(score_i)`; ordinal outputs
`P_j=sigmoid(class_weight_j*S+class_bias_j)`.
The published decoding is the number of consecutive probabilities greater
than 0.5 minus 1 (clamp to the valid nine classes only after parity check).
The five camera-ready `split_0..4.ckpt` checkpoint files are 34526 bytes
each. The matching `scaler_0..4.pkl` files are 1088 bytes each.

Twelve descriptor names in **upstream predict.py order**:

1. rh_pitch_set_lz
2. lh_pitch_set_lz
3. rh_pitch_range
4. lh_pitch_range
5. lh_average_pitch
6. rh_average_pitch
7. lh_average_ioi_seconds
8. rh_average_ioi_seconds
9. rh_displacement_rate
10. lh_displacement_rate
11. lh_pitch_entropy
12. rh_pitch_entropy

**Input order now confirmed for the five camera-ready scalers:** the pinned
1,088-byte scaler pickles each contain the same 12 `feature_names_in_` entries
in the above order, matching `predict.py`. This was verified by inspecting
all five official scaler blobs without executing pickle. The training source
also exposes a 10-feature Chiu configuration, but these camera-ready scalers
use 12. Runtime input validation still rejects missing, extra or reordered
features; upstream numerical prediction parity **passed** (100 vectors,
5 folds; run 41092489234).
Feature scaling remains separate for each fold.

**Upstream predict.py defects:** `~/PycharmProjects/Rubricnet/...`
checkpoint and scaler paths are developer-specific and are not portable;
importing full upstream `RubricnetSklearn` also starts Lightning/WandB
training infrastructure unnecessarily. Loading upstream pickle files is
unsafe if they have not been authenticated. Prefer an offline JSON conversion
of verified official assets, then a minimal CPU-only inference adapter.

The arXiv abstract reports **41.4% / MSE 1.7** while the current upstream
README reports **41.5% / MSE 1.52**. These are not interchangeable baseline
numbers; pin the evaluation version and metric definition.

### Initial implementation checkpoints

- [x] Verified official Git repository, license, commit and file tree.
- [x] Verified published model architecture and the checkpoint/scaler file inventory.
- [x] Resolved camera-ready input ordering by direct inspection of all five
      official scaler files; documented 10- versus 12-feature training variants
      and the opt-in verified-pickle conversion requirement.
- [x] Exported all five official trained checkpoints/scalers after checking
      all ten Git blob hashes. Five inert JSON models and the upstream MIT
      notice are bundled offline in `piano_teacher/research/models/rubricnet`.
- [x] Reference PyTorch vs independent CPU implementation: 100 checked
      vectors across the five real official folds. Maximum descriptor error
      1.9013e-7, maximum ordinal-probability error 1.6837e-7.
      Action run [41092489234](https://github.com/tpepels/piano_teacher/actions/runs/41092489234).
- [x] Ran the **actual upstream extractor** on published `inven01.musicxml`;
      all 12 descriptors matched the explicit published 
      `predict.py::check_features_extractor` values exactly. The isolated
      reference pipeline then returned real five-fold predictions [2,2,2,3,3].
      See [run 41094282081](https://github.com/tpepels/piano_teacher/actions/runs/41094282081).
- [ ] Package and isolate the exact feature extraction for offline app-native
      use, then verify multiple real scores and failure handling before
      enabling trained difficulty in lesson settings.
- [x] Verified all 660 official CIPI held-out predictions using five pinned
      split memberships and the published descriptor file (no overlap with
      training/validation IDs). Mean balanced accuracy = 0.4134530732;
      mean macro-MSE = 1.7156957494. The published arXiv figures are 41.4%
      and approximately 1.7. Independent one-shot run
      [41093460920](https://github.com/tpepels/piano_teacher/actions/runs/41093460920)
      passed, including 10 inference/provenance tests.
- [ ] Only then make the trained strategy selectable in the application.

## Source-to-code acceptance process

For each algorithm, record: exact source version and license; expected
symbolic/audio inputs and outputs; model/dataset provenance; unsupported cases;
numerical or example-level reference oracle; existing adapter mapping;
regressions; device tests; and measured fidelity. Classify states separately:
`unverified`, `paper-specified`, `reference-available`,
`inference-verified`, `end-to-end-verified`, `pedagogically-validated`.
No checkpoint is accepted solely because unit tests execute successfully.

No heavy model dependencies or binary checkpoint files are added to the
standard installation or short push CI.

## Engineering evidence for initial gate-1 work

- `piano_teacher/research/rubricnet_core.py`: CPU-only implementation of the
  published descriptor-wise affine+tanh scores, aggregate, nine ordinal
  sigmoid outputs and upstream consecutive-threshold decoder. It cannot
  pretend to be trained when model bundles are absent.
- `piano_teacher/research/rubricnet_assets.py`: pinned upstream commit and
  Git SHA-1 blob identities for all five checkpoints/scalers, plus exact
  feature-set definitions.
- `scripts/research/export_rubricnet.py`: opt-in offline converter, immutable
  source integrity verification and strict scaler metadata checks.
- `tests/test_rubricnet_reproduction.py`: deterministic inference equations,
  five-fold/schema compatibility, integrity and fail-closed behavior.
- Standard short CI at `93c1f609`: **108 passed, 4 optional skips in 1.89s**.
  This is unit-level engineering evidence only, not checkpoint or training
  prediction parity.

### Next precise gate

The authentic five-fold weights are packaged, reference-checked and validated
against the official 660 held-out CIPI test predictions. **The trained
RubricNet mathematical model is reproduced.** Its 12 MusicXML descriptors
were extracted from the published reference score by the original upstream
code with exact oracle parity; an isolated source-to-model CLI is working.
App-native extraction, broader score coverage and teacher validation remain.

1. Package the pinned original extractor (or a provably equivalent port) as
   an offline, independently testable optional worker without exposing
   Lightning/WandB/training dependencies to the teaching process.
2. Cover realistic multi-part MusicXML, invalid/absent hands, meter and tempo
   changes with deterministic extraction errors, not heuristic fallbacks.
3. Only after verified source-to-descriptor parity, expose trained
   `rubricnet-trained` in app settings as a separate strategy and compare it
   against the original heuristic on student-facing passages.
4. Keep the held-out CIPI regression as the source-of-truth checkpoint for any
   future changes to the model or descriptor ordering.

### Camera-ready CIPI per-fold held-out metrics

| Fold | N | Balanced accuracy | Macro MSE |
| --- | ---: | ---: | ---: |
| 0 | 132 | 40.7255% | 1.5848 |
| 1 | 132 | 40.5221% | 2.5884 |
| 2 | 132 | 39.6666% | 1.7198 |
| 3 | 133 | 46.6969% | 1.1196 |
| 4 | 131 | 39.1154% | 1.5658 |
| **Mean** | **660 evaluations** | **41.3453%** | **1.7157** |

All split labels and feature maps were fetched from official GitHub assets,
checked against recorded blob hashes, and processed by
`scripts/research/validate_rubricnet_cipi.py`. The models do **not** require
Torch/scikit-learn at application runtime.

**Reference source-to-model parity:**
[run 41094282081](https://github.com/tpepels/piano_teacher/actions/runs/41094282081)
installed the original pinned extractor in a bounded, isolated worker and
matched all 12 published `inven01.musicxml` descriptors exactly. The full
source-to-real-fold CLI (`scripts/research/predict_rubricnet_musicxml.py`)
returned difficulty classes **[2, 2, 2, 3, 3]**. Research-reference path:
`end-to-end-verified on the published reference fixture`; application-level
integration and broad MusicXML robustness remain **unverified**.
