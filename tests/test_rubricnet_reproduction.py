"""Minimal, deterministic RubricNet inference-contract tests without ML packages.

The official checkpoint/scaler and upstream feature extractor are deliberately
NOT declared verified by these synthetic numerical tests.
"""
import hashlib
import json
from math import exp, isclose, tanh

import pytest

from piano_teacher.research.rubricnet_core import (
    RubricNetEnsemble, RubricNetFold,
)
from piano_teacher.research.rubricnet_assets import (
    BASIC_FEATURES, CHIU_FEATURES, OFFICIAL_ARTIFACTS, UPSTREAM_COMMIT,
)
from scripts.research.export_rubricnet import verify_git_blob, export_assets


def example(split=0):
    names = list(CHIU_FEATURES)
    return {
        "schema": "rubricnet-fold-v1",
        "split": split,
        "source_commit": UPSTREAM_COMMIT,
        "feature_names": names,
        "scaler_mean": [float(i) for i in range(len(names))],
        "scaler_scale": [2.0] * len(names),
        "descriptor_weights": [0.2] * len(names),
        "descriptor_biases": [-0.1] * len(names),
        "class_weights": [0.0] * 9,
        "class_biases": [2.0, 1.5, .7, -.2, -.5, -1.0, -2.0, -3.0, -4.0],
    }


def test_published_descriptor_math_probability_and_ordinal_prefix():
    bundle = example()
    fold = RubricNetFold.from_dict(bundle)
    inputs = {name: i + 2.0 for i, name in enumerate(bundle["feature_names"])}
    answer = fold.predict(inputs)
    expected_score = tanh(.2 * ((2.0)/2) - .1)
    assert all(isclose(x, expected_score, abs_tol=1e-12)
               for x in answer.descriptor_scores)
    assert answer.aggregated_score == pytest.approx(10*expected_score)
    assert answer.predicted_class == 2
    expected_prob = 1.0 / (1.0 + exp(-.7))
    assert answer.ordinal_probabilities[2] == pytest.approx(expected_prob)
    assert answer.ordinal_probabilities[3] < .5
    assert len(answer.ordinal_probabilities) == 9


def test_ordinal_decoder_counts_only_the_leading_true_prefix():
    data = example()
    data["class_biases"] = [-.1, 8, 8, 8, 8, 8, 8, 8, 8]
    pred = RubricNetFold.from_dict(data).predict(
        {name: 0.0 for name in CHIU_FEATURES})
    assert pred.predicted_class == -1  # Preserves upstream sentinel, not clamped.


def test_feature_order_is_named_and_mandatory_even_with_equal_vector_shape():
    fold = RubricNetFold.from_dict(example())
    values = {name: 0.1 for name in CHIU_FEATURES}
    assert len(fold.predict(values).descriptor_scores) == 10
    with pytest.raises(ValueError, match="descriptor mismatch"):
        fold.predict(dict(values, wrong=7))
    with pytest.raises(ValueError, match="descriptor mismatch"):
        fold.predict({name: 0.1 for name in BASIC_FEATURES if name != "rh_pitch_range"})
    data = example()
    data["feature_names"][1] = data["feature_names"][0]
    with pytest.raises(ValueError, match="duplicate"):
        RubricNetFold.from_dict(data)


@pytest.mark.parametrize("field,new_value", [
    ("scaler_scale", [0.0]*10),
    ("descriptor_weights", [0.0]*9),
    ("class_biases", [1.0]*8),
])
def test_incompatible_assets_fail_before_inference(field, new_value):
    payload = example()
    payload[field] = new_value
    with pytest.raises(ValueError):
        RubricNetFold.from_dict(payload)


def test_ensemble_requires_all_five_identical_feature_contracts(tmp_path):
    for split in range(5):
        (tmp_path / f"fold_{split}.json").write_text(
            json.dumps(example(split)), encoding="utf-8")
    folds = RubricNetEnsemble.load(tmp_path)
    assert len(folds.predict({name: 0.0 for name in CHIU_FEATURES})) == 5
    data = example(4)
    data["feature_names"] = list(reversed(data["feature_names"]))
    (tmp_path / "fold_4.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="compatible"):
        RubricNetEnsemble.load(tmp_path)


def test_reference_asset_manifest_and_untrusted_pickle_are_fail_closed(tmp_path):
    assert len(OFFICIAL_ARTIFACTS) == 10
    assert all(len(sha) == 40 for sha in OFFICIAL_ARTIFACTS.values())
    assert all(name.startswith("checkpoints/rubricnet_cameraready/")
               for name in OFFICIAL_ARTIFACTS)
    with pytest.raises(PermissionError):
        export_assets(tmp_path, tmp_path / "output", allow_pickle=False)
    assert not (tmp_path / "output").exists()

    binary = tmp_path / "sample.bin"
    raw = b"reference fake content"
    binary.write_bytes(raw)
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
    assert verify_git_blob(binary, sha) == raw
    binary.write_bytes(raw + b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        verify_git_blob(binary, sha)
