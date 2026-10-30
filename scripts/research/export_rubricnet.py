#!/usr/bin/env python3
"""Export authenticated upstream RubricNet training assets to inert JSON.

Use ONLY on a local checkout of the pinned official repository; this is not
invoked by ordinary app startup or CI. `pickle` can execute code: it is read
only after byte-for-byte Git-blob SHA validation, behind an explicit option.
No network downloads, WandB, Lightning training or shell execution occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

from piano_teacher.research.rubricnet_assets import (
    BASIC_FEATURES, CHIU_FEATURES, OFFICIAL_ARTIFACTS, UPSTREAM_COMMIT,
)
from piano_teacher.research.rubricnet_core import RubricNetFold, RubricNetEnsemble


def verify_git_blob(path: Path, sha: str) -> bytes:
    raw = path.read_bytes()
    digest = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
    ).hexdigest()
    if digest != sha:
        raise ValueError(f"Upstream integrity check failed: {path}")
    return raw


def export_assets(upstream: Path, output: Path, *, allow_pickle: bool = False) -> None:
    if not allow_pickle:
        raise PermissionError(
            "Export needs --allow-verified-upstream-pickle. "
            "Never load unverified or third-party pickle files.")
    # Reject incomplete/mismatched source trees BEFORE loading any pickles.
    official = {
        name: verify_git_blob(upstream / name, digest)
        for name, digest in OFFICIAL_ARTIFACTS.items()
    }

    # Heavy dependencies are required only by this explicit offline converter.
    import torch
    import sklearn.preprocessing  # noqa: F401  # Needed to deserialize a StandardScaler

    prepared: list[dict] = []
    for split in range(5):
        folder = "checkpoints/rubricnet_cameraready"
        scaler_name = f"{folder}/scaler_{split}.pkl"
        weights_name = f"{folder}/split_{split}.ckpt"
        scaler = pickle.loads(official[scaler_name])
        if type(scaler).__name__ != "StandardScaler":
            raise ValueError(f"Wrong fitted scaler in split {split}")
        if not hasattr(scaler, "feature_names_in_"):
            # There are both a 10-feature CHIU and a 12-feature BASIC
            # training configuration. Never guess at tensor columns.
            raise ValueError("Scaler lacks feature_names_in_; reference input order unknown")
        feature_names = tuple(str(name) for name in scaler.feature_names_in_)
        if feature_names not in (BASIC_FEATURES, CHIU_FEATURES):
            raise ValueError(f"Unknown RubricNet feature order in split {split}")
        n = len(feature_names)
        if len(scaler.mean_) != n or len(scaler.scale_) != n:
            raise ValueError("Inconsistent StandardScaler dimensions")
        # weights_only prevents executable classes from being unpickled out
        # of a Lightning checkpoint; metadata must consist of safe primitives.
        checkpoint = torch.load(
            upstream / weights_name, map_location="cpu", weights_only=True)
        tensors = checkpoint["state_dict"]
        root = "linear1."
        descriptor_weights = []
        descriptor_biases = []
        for i in range(n):
            descriptor_weights.append(
                float(tensors[f"{root}descriptor_layers.{i}.weight"].reshape(-1)[0]))
            descriptor_biases.append(
                float(tensors[f"{root}descriptor_layers.{i}.bias"].reshape(-1)[0]))
        # Refuse a checkpoint trained for a different number of descriptors.
        additional = f"{root}descriptor_layers.{n}.weight"
        if additional in tensors:
            raise ValueError("Scaler and checkpoint dimensions disagree")
        class_weights = tensors[f"{root}final_layer.weight"].reshape(-1).tolist()
        class_biases = tensors[f"{root}final_layer.bias"].reshape(-1).tolist()
        if len(class_weights) != 9 or len(class_biases) != 9:
            raise ValueError("Expected the official nine ordinal outputs")

        bundle = {
            "schema": "rubricnet-fold-v1",
            "source_commit": UPSTREAM_COMMIT,
            "split": split,
            "source_checkpoint_git_blob": OFFICIAL_ARTIFACTS[weights_name],
            "source_scaler_git_blob": OFFICIAL_ARTIFACTS[scaler_name],
            "feature_names": list(feature_names),
            "scaler_mean": [float(x) for x in scaler.mean_],
            "scaler_scale": [float(x) for x in scaler.scale_],
            "descriptor_weights": descriptor_weights,
            "descriptor_biases": descriptor_biases,
            "class_weights": class_weights,
            "class_biases": class_biases,
        }
        RubricNetFold.from_dict(bundle)  # Validate without loading PyTorch again.
        prepared.append(bundle)

    # Verify all five folds and identical descriptor order BEFORE writing.
    folds = tuple(RubricNetFold.from_dict(data) for data in prepared)
    RubricNetEnsemble(folds)
    output.mkdir(parents=True, exist_ok=True)
    for data in prepared:
        target = output / f"fold_{data['split']}.json"
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    print("Exported 5 verified RubricNet folds. Upstream parity is still required.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True,
                        help="Local checkout at the pinned upstream commit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-verified-upstream-pickle",
                        action="store_true", default=False)
    args = parser.parse_args()
    export_assets(args.upstream, args.output,
                  allow_pickle=args.allow_verified_upstream_pickle)


if __name__ == "__main__":
    main()
