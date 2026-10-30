# Research reproduction — gate 1 source audit
Date: 2026-10-30. Repository: tpepels/piano_teacher, main.
Status: **source inventory started; no algorithm-reproduction gate accepted**.

This supersedes the *research fidelity* meaning of "complete" in the Step 2–4
engineering trackers. Those trackers still describe tested **adaptations**.
A strategy is not counted as reproduced until there is reference parity,
specified applicability, independent test data and documented deviations.

## Traceability matrix

| Method / primary source | Published algorithm and required components | Existing Piano Teacher mapping | Source/model availability | Missing evidence / reproduction gate |
| --- | --- | --- | --- | --- |
| RubricNet, Ramoneda et al. 2024, arXiv:2408.00473 | Twelve symbolic descriptors (six per hand), scaler per fold, descriptor-wise affine+tanh, aggregation, nine-class ordinal sigmoid, five trained folds and interpretability | `difficulty.py` and `FeatureGatedStrategy`: untrained rule-based features only | **Public MIT repository, training code, extractor, 5 camera-ready checkpoints and scalers**: https://github.com/PRamoneda/rubricnet (verified master at `3ff4a9342948b9588541a2a8524eab68045f6001`) | Validate published extractor on reference score, verify exact input ordering against training, safely export each scaler/checkpoint, match upstream predictions on fixed feature vectors and full MusicXML; held-out 9-class validation |
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

**Important unresolved input-contract risk:** `features/clean_data.py`
lists the same 12 names in another order. Do not treat checkpoint results as
trustworthy until scaler metadata and a prediction oracle confirm the *actual*
training order. Feature scaling is separate for each fold.

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
- [x] Documented model input feature-order ambiguity and unsafe pickle risk.
- [ ] Authenticate and export five official checkpoint/scaler pairs into a
      deterministic, local, read-only format with pinned asset digests.
- [ ] Run upstream and local CPU inference side-by-side on equal prepared
      vectors: decoded classes, 12 descriptor scores, aggregate regression
      and nine ordinal probabilities must match.
- [ ] Implement/exercise the **actual upstream** 12 feature extractors on real
      MusicXML. Upstream `inven01.musicxml` and `predict.py::check_features_extractor`
      supply a reference descriptor fixture.
- [ ] Verify dataset splits, labels, per-fold scaler input order and accuracy.
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
