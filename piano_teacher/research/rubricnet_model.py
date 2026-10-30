"""Verified camera-ready RubricNet ensemble, available offline.

This module intentionally accepts ONLY the published 12 descriptor values.
It will not manufacture them from Piano Teacher's unrelated heuristic
features; MusicXML source-descriptor parity is a separate research gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from statistics import median
from typing import Mapping

from .rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT
from .rubricnet_core import RubricNetEnsemble, RubricNetPrediction


@dataclass(frozen=True)
class RubricNetResult:
    """Five separately calibrated folds, not an invented learner-level class."""
    predictions: tuple[RubricNetPrediction, ...]
    source_commit: str

    @property
    def median_class(self) -> int:
        return int(median(sorted(p.predicted_class for p in self.predictions)))

    @property
    def all_classes(self) -> tuple[int, ...]:
        return tuple(p.predicted_class for p in self.predictions)


@dataclass(frozen=True)
class RubricNetModel:
    ensemble: RubricNetEnsemble

    @classmethod
    def bundled(cls) -> "RubricNetModel":
        from .rubricnet_core import RubricNetFold
        folder = files("piano_teacher.research").joinpath("models", "rubricnet")
        folds = []
        for i in range(5):
            import json
            data = json.loads(folder.joinpath(f"fold_{i}.json").read_text(
                encoding="utf-8"))
            if data.get("source_commit") != UPSTREAM_COMMIT:
                raise ValueError("Unexpected bundled RubricNet provenance")
            folds.append(RubricNetFold.from_dict(data))
        ensemble = RubricNetEnsemble(tuple(folds))
        if ensemble.folds[0].feature_names != BASIC_FEATURES:
            raise ValueError("Official RubricNet camera-ready input contract changed")
        return cls(ensemble)

    def predict_descriptors(self, features: Mapping[str, float]) -> RubricNetResult:
        return RubricNetResult(self.ensemble.predict(features), UPSTREAM_COMMIT)
