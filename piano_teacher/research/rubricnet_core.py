"""CPU-only inference of the *published* RubricNet ordinal architecture.

This module reproduces the upstream inference equations without depending on
Lightning/WandB, loading pickle, or replacing missing trained weights with a
heuristic. It accepts only a separately exported, provenance-checked bundle.
Feature extraction and numerical parity with upstream remain separate gates.

Upstream: PRamoneda/rubricnet@3ff4a9342948b9588541a2a8524eab68045f6001
License: MIT (upstream); implementation here expresses the paper equations.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import exp, isfinite, tanh
from pathlib import Path
from typing import Mapping


def _vector(bundle: dict, key: str, length: int) -> tuple[float, ...]:
    values = bundle[key]
    if not isinstance(values, list) or len(values) != length:
        raise ValueError(f"RubricNet {key} must contain {length} numbers")
    if any(isinstance(v, bool) or not isinstance(v, (float, int))
           or not isfinite(v) for v in values):
        raise ValueError(f"RubricNet {key} has invalid numbers")
    return tuple(float(v) for v in values)


def _sigmoid(x: float) -> float:
    # Numerically stable version of torch.sigmoid at inference time.
    if x >= 0:
        return 1.0 / (1.0 + exp(-x))
    y = exp(x)
    return y / (1.0 + y)


@dataclass(frozen=True)
class RubricNetPrediction:
    model_split: int
    predicted_class: int
    descriptor_scores: tuple[float, ...]
    aggregated_score: float
    ordinal_probabilities: tuple[float, ...]


@dataclass(frozen=True)
class RubricNetFold:
    split: int
    feature_names: tuple[str, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    descriptor_weights: tuple[float, ...]
    descriptor_biases: tuple[float, ...]
    class_weights: tuple[float, ...]
    class_biases: tuple[float, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "RubricNetFold":
        if data.get("schema") != "rubricnet-fold-v1":
            raise ValueError("Unrecognized RubricNet model bundle")
        names = data["feature_names"]
        if (not isinstance(names, list) or len(names) not in (10, 12)
                or any(not isinstance(n, str) or not n for n in names)
                or len(set(names)) != len(names)):
            raise ValueError("Invalid or duplicate RubricNet feature names")
        split = data.get("split")
        if type(split) is not int or not 0 <= split < 5:
            raise ValueError("RubricNet split must be in 0..4")
        n = len(names)
        obj = cls(split, tuple(names), _vector(data, "scaler_mean", n),
                  _vector(data, "scaler_scale", n),
                  _vector(data, "descriptor_weights", n),
                  _vector(data, "descriptor_biases", n),
                  _vector(data, "class_weights", 9),
                  _vector(data, "class_biases", 9))
        if any(scale <= 0 for scale in obj.scaler_scale):
            raise ValueError("Nonpositive RubricNet scaler standard deviation")
        return obj

    @classmethod
    def load(cls, path: str | Path) -> "RubricNetFold":
        with Path(path).open(encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    def predict(self, features: Mapping[str, float]) -> RubricNetPrediction:
        if set(features) != set(self.feature_names):
            missing = sorted(set(self.feature_names) - set(features))
            extra = sorted(set(features) - set(self.feature_names))
            raise ValueError(f"RubricNet descriptor mismatch: missing={missing}, extra={extra}")
        scaled = []
        for name, mean, scale in zip(
                self.feature_names, self.scaler_mean, self.scaler_scale):
            raw = features[name]
            if isinstance(raw, bool) or not isinstance(raw, (float, int)) or not isfinite(raw):
                raise ValueError(f"Invalid RubricNet descriptor: {name}")
            scaled.append((float(raw) - mean) / scale)
        scores = tuple(tanh(x*w + b) for x, w, b in zip(
            scaled, self.descriptor_weights, self.descriptor_biases))
        aggregate = sum(scores)
        probabilities = tuple(_sigmoid(aggregate*w+b) for w, b in zip(
            self.class_weights, self.class_biases))
        # Upstream _prediction2label: consecutive leading P>0.5, minus one.
        # Return -1 rather than inventing a valid class if none pass.
        prefix = 0
        for probability in probabilities:
            if probability <= .5:
                break
            prefix += 1
        return RubricNetPrediction(
            self.split, prefix - 1, scores, aggregate, probabilities)


@dataclass(frozen=True)
class RubricNetEnsemble:
    folds: tuple[RubricNetFold, ...]

    def __post_init__(self):
        if (len(self.folds) != 5 or {fold.split for fold in self.folds} != set(range(5))
                or any(fold.feature_names != self.folds[0].feature_names for fold in self.folds)):
            raise ValueError("RubricNet requires five compatible official folds")

    @classmethod
    def load(cls, directory: str | Path) -> "RubricNetEnsemble":
        return cls(tuple(RubricNetFold.load(Path(directory)/f"fold_{i}.json")
                         for i in range(5)))

    def predict(self, features: Mapping[str, float]) -> tuple[RubricNetPrediction, ...]:
        return tuple(fold.predict(features) for fold in self.folds)
