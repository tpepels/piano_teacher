#!/usr/bin/env python3
"""Explicit RubricNet checkpoint-vs-export numerical parity gate.

Run only after exporting the authenticated, official camera-ready assets.
Requires PyTorch; never executes during push CI or normal app startup.
Tests 20 deterministic feature vectors *per split* (100 vectors overall).
This validates model mathematics and scaler export, NOT MusicXML feature
extraction, published dataset accuracy, or pedagogical effectiveness.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from piano_teacher.research.rubricnet_core import RubricNetEnsemble
from piano_teacher.research.rubricnet_assets import (
    OFFICIAL_ARTIFACTS,
)
from scripts.research.export_rubricnet import verify_git_blob


def verify(upstream: Path, exported: Path, *, per_fold: int = 20,
           probability_atol: float = 1e-5) -> dict:
    import torch

    ensemble = RubricNetEnsemble.load(exported)
    result = {"folds": 0, "vectors": 0, "max_probability_error": 0.0,
              "max_descriptor_error": 0.0}
    generator = random.Random(20261030)
    for fold in ensemble.folds:
        asset = f"checkpoints/rubricnet_cameraready/split_{fold.split}.ckpt"
        verify_git_blob(upstream / asset, OFFICIAL_ARTIFACTS[asset])
        checkpoint = torch.load(upstream / asset, weights_only=True,
                                map_location="cpu")
        weights = checkpoint["state_dict"]

        def official(descriptors):
            tensor = torch.tensor([descriptors], dtype=torch.float32)
            scores = [
                torch.tanh(
                    torch.nn.functional.linear(
                        tensor[:, i:i+1],
                        weights[f"linear1.descriptor_layers.{i}.weight"],
                        weights[f"linear1.descriptor_layers.{i}.bias"]
                    )
                )
                for i in range(len(fold.feature_names))
            ]
            aggregate = torch.sum(torch.stack(scores), dim=0)
            probabilities = torch.sigmoid(
                torch.nn.functional.linear(
                    aggregate, weights["linear1.final_layer.weight"],
                    weights["linear1.final_layer.bias"]))
            return ([float(s.item()) for s in scores],
                    float(aggregate.item()), probabilities[0].tolist())

        for _ in range(per_fold):
            # Generate named raw descriptors, then scale through the same
            # StandardScaler coefficients used by both implementations.
            scaled = [generator.uniform(-2.5, 2.5)
                      for _ in fold.feature_names]
            raw = {
                name: mean + scale * value
                for name, mean, scale, value in zip(
                    fold.feature_names, fold.scaler_mean,
                    fold.scaler_scale, scaled)
            }
            actual = fold.predict(raw)
            ref_scores, ref_aggregate, ref_prob = official(scaled)
            descriptor_error = max(abs(a-b) for a, b in
                                   zip(actual.descriptor_scores, ref_scores))
            probability_error = max(abs(a-b) for a, b in
                                    zip(actual.ordinal_probabilities, ref_prob))
            result["max_descriptor_error"] = max(
                result["max_descriptor_error"], descriptor_error)
            result["max_probability_error"] = max(
                result["max_probability_error"], probability_error)
            if (descriptor_error > probability_atol or
                    probability_error > probability_atol or
                    abs(actual.aggregated_score-ref_aggregate) > probability_atol):
                raise AssertionError(
                    f"Split {fold.split}: RubricNet math mismatch at vector "
                    f"{result['vectors']}: descriptor={descriptor_error}, "
                    f"ordinal={probability_error}")
            official_class = 0
            for value in ref_prob:
                if value <= .5:
                    break
                official_class += 1
            official_class -= 1
            if actual.predicted_class != official_class:
                raise AssertionError(f"Split {fold.split}: ordinal label mismatch")
            result["vectors"] += 1
        result["folds"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--exported", type=Path, required=True)
    parser.add_argument("--per-fold", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.per_fold <= 10000:
        parser.error("Choose 1..10000 comparison vectors per fold")
    print(verify(args.upstream, args.exported, per_fold=args.per_fold))


if __name__ == "__main__":
    main()
