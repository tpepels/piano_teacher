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

A passing test in `tests/test_rubricnet_reproduction.py` is a synthetic
numerical-contract test and does not substitute for the above parity run.

Next: reproduce `predict.py::check_features_extractor` with
`inven01.musicxml`, then validate the public CIPI split labels and
reported metrics. Keep optional heavy dependencies off routine push CI.
