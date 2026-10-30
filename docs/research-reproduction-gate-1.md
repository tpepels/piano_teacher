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
features; upstream numerical prediction parity has **not** been tested yet.
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
- [ ] Run `scripts/research/export_rubricnet.py` on the pinned official
      checkout: it verifies all ten Git blob hashes, safely loads checkpoint
      weights, and after explicit opt-in deserializes only the authenticated
      sklearn scalers. This exports five inert JSON fold files. The tool and
      digests are committed, but real binary conversion has not run yet.
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

The explicit `scripts/research/verify_rubricnet_parity.py` now compares
20 deterministic vectors per fold (100 total) against PyTorch inference on the
authenticated camera-ready weights. See `scripts/research/README.md` for
pinned checkout, export, and parity commands. **It has not yet been run against
the real trained assets.**

1. Export authenticated real camera-ready files to five inert JSON folds.
2. Compare the numerical predictions to upstream PyTorch on a shared set of
   at least 20 deterministic input vectors (including pathological boundaries).
3. Run the official `inven01.musicxml` descriptor oracle through the original
   extractor, compare all 12 raw descriptors, and evaluate held-out examples
   against the upstream split IDs/labels.
4. Only after parity, expose `rubricnet-trained` in the app; do **not**
   relabel `feature-gated` or route students via unverified predictions.
