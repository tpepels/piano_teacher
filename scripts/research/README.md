# Reproducing reference research systems

The regular piano teacher does not require PyTorch, sklearn, model weights, or
network access. The research reproduction tools are explicit local commands,
not CI jobs and not part of lesson startup.

## RubricNet: authentic camera-ready inference

Research source: https://github.com/PRamoneda/rubricnet
Pinned upstream revision: `3ff4a9342948b9588541a2a8524eab68045f6001`
License: MIT. No checkpoint, scaler or pickle is stored in Piano Teacher.

From the `piano_teacher` repository root:

```bash
# Separate checkout; never mix third-party training files into Piano Teacher.
git clone https://github.com/PRamoneda/rubricnet.git /tmp/rubricnet-upstream
git -C /tmp/rubricnet-upstream checkout 3ff4a9342948b9588541a2a8524eab68045f6001

# Use a separate environment with torch and scikit-learn.
# Install these explicitly, outside the normal Piano Teacher runtime:
python -m pip install torch scikit-learn

python -m scripts.research.export_rubricnet \
    --upstream /tmp/rubricnet-upstream \
    --output /tmp/rubricnet-export \
    --allow-verified-upstream-pickle

python -m scripts.research.verify_rubricnet_parity \
    --upstream /tmp/rubricnet-upstream \
    --exported /tmp/rubricnet-export --per-fold 20
```

The export tool first checks the exact published Git blob SHA-1 hash of all ten
camera-ready files, and only then reads the five sklearn pickles. **Unpickling
is capable of code execution**, so this opt-in is only suitable for the verified,
trusted upstream assets; do not repoint at arbitrary models. The other five
files load with `torch.load(weights_only=True)`.

The output consists of five inert JSON files containing the actual trained
parameters, fitted StandardScaler statistics, feature ordering, upstream
revision and source blob identities. These are usable by the dependency-free
`piano_teacher.research.rubricnet_core` inference implementation.

All five camera-ready upstream scalers have the same **12 explicitly named
features**, confirmed by reading their binary metadata without executing
pickle. The original training source also defines a 10-feature alternative,
but the pinned camera-ready scalers use 12.

The parity tool compares **100 deterministic input vectors** (20 per fold)
against PyTorch using the *official original checkpoint tensors*. It checks
every descriptor score, aggregate and sigmoid output and ordinal class.

This checks the inference numerical path only. **The complete RubricNet
algorithm requires the original MusicXML feature extractor and independent
held-out dataset validation as well.** The current feature-gated app strategy
is still heuristic and must not be presented as trained RubricNet.

The official reference checkpoint-parity run **passed** on GitHub Actions:
[run 41092489234](https://github.com/tpepels/piano_teacher/actions/runs/41092489234).
It checked 100 vectors across 5 folds with maximum probability error 1.68e-7.
The 5 verified parameter JSON files and upstream MIT license are now included
under `piano_teacher/research/models/rubricnet/`, allowing offline inference:

```python
from piano_teacher.research.rubricnet_model import RubricNetModel
model = RubricNetModel.bundled()
# descriptors must contain the EXACT 12 original upstream feature names.
result = model.predict_descriptors(descriptors)
classes = result.all_classes
```

A passing test in `tests/test_rubricnet_reproduction.py` additionally
exercises these **real bundled** model assets and strict descriptor contracts.

Next: reproduce `predict.py::check_features_extractor` with
`inven01.musicxml`, then validate the public CIPI split labels and
reported metrics. Keep optional heavy dependencies off routine push CI.

## Held-out evaluation against original CIPI data

```bash
python -m scripts.research.validate_rubricnet_cipi \
    --download --check-published
```

This explicitly downloads two official **SHA-checked** JSON files from the
pinned commit and evaluates each camera-ready fold only on its matching test
split, using real precomputed symbolic descriptors. It requires no optional ML
dependencies. It made 660 test predictions, with mean balanced accuracy
41.3453% and mean macro MSE 1.7157 (official published ~41.4% and 1.7).
GitHub [verification run 41093460920](https://github.com/tpepels/piano_teacher/actions/runs/41093460920)
passed, along with the 10 model tests. These checks do not yet establish
MusicXML descriptor-extraction parity; that remains the next gate.

## Official MusicXML descriptor oracle and source-to-model path

The full upstream feature extractor has additional dependencies (including
music21, SciPy, scikit-learn and a PyTorch fingering module imported by the
original research source). It is run in a **separate, pinned upstream checkout**,
not inside the application server. For the official reference score:

```bash
python -m scripts.research.verify_rubricnet_source_features \
  --upstream /tmp/rubricnet-upstream --check-oracle

python -m scripts.research.predict_rubricnet_musicxml \
  --upstream /tmp/rubricnet-upstream \
  --score /tmp/rubricnet-upstream/inven01.musicxml \
  --output /tmp/invention-rubricnet.json
```

The oracle confirms every one of the **twelve** descriptors against the values
recorded in the upstream `predict.py::check_features_extractor`. The predictor
then applies the authentic shipped camera-ready models. It emits the source
file SHA256, upstream commit, descriptor names and values, five complete fold
outputs and the median class. This isolates the research code and prevents
unvalidated MusicXML features from reaching a learner session.

A separate three-minute, one-shot GitHub Actions check runs the original source
oracle with these optional dependencies. The resulting source-to-model command
is **not** yet an app-native difficulty strategy: packaging/porting the exact
extractor, input-score parity and classroom/device acceptance remain open.

## Offline application strategy (optional)

The full published extractor's 14 required original Python modules are
vendored **byte-for-byte** under
`piano_teacher/research/_upstream_rubricnet/`, including the MIT license.
The trained five-fold model is already bundled separately. The program
requires **no internet access when using RubricNet** after one-time setup.

To install optional extractor requirements without adding Torch or training
modules to the normal Piano Teacher environment:

```bash
cd ~/Projects/piano_teacher
bash scripts/setup-rubricnet.sh
./run.sh
```

`run.sh` uses `.rubricnet-venv/bin/python` for the isolated optional worker.
The trainer, checkpoint loader and full research checkout are **not**
imported into the practice service. If launching the backend manually,
set `PIANO_TEACHER_RUBRICNET_PYTHON` to that interpreter path.

In Godot Settings → Practice, select **RubricNet · trained score difficulty
(optional setup)**. This sets an independent `rubricnet-trained` profile;
the default `legacy` strategy and existing `feature-gated` heuristic
remain unchanged. Switching an open score validates trained extraction before
saving the selection and stopping the current session.

The actual source MusicXML is passed to the original extractor, which returns
12 named descriptors. The five authentic trained models predict whole-piece
difficulty. **Exercise selection after prediction is our explicit heuristic
rule, not a learned RubricNet policy:** classes 0–2 use the baseline path,
3–5 Coda part-splitting, 6–8 combined Fukuda+Coda source-preserving drills.

The upstream extractor assumes a conventional two-hand score. Short,
rest-only, sparsely pitched, or otherwise unsupported scores can produce
undefined features; those are refused with an error and **no surrogate
difficulty**. Broader positive/negative fixture acceptance is tracked in
`tests/test_rubricnet_real_scores.py`. Only the optional research test job
imports Torch/scientific packages. Ordinary CI stays short.

The trained difficulty class is not calibrated to the learner's skill and
does not establish that the selected exercise improves learning.
