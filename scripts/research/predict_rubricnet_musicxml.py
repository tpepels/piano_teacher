"""Authentic RubricNet MusicXML -> 12 features -> trained five-fold inference.

The source extractor runs in a pinned, separately installed upstream checkout.
The five camera-ready models are bundled and CPU-only at inference time.
This is an explicit research command, not yet enabled in learner settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from piano_teacher.research.rubricnet_model import RubricNetModel
from scripts.research.verify_rubricnet_source_features import reference_descriptors


def predict_musicxml(upstream: Path, score: Path) -> dict:
    descriptors = reference_descriptors(upstream, score)
    model = RubricNetModel.bundled()
    prediction = model.predict_descriptors(descriptors)
    return {
        "schema": "rubricnet-score-inference-v1",
        "model_source_commit": prediction.source_commit,
        "source_musicxml_sha256": hashlib.sha256(score.read_bytes()).hexdigest(),
        "feature_names": list(model.ensemble.folds[0].feature_names),
        "descriptors": descriptors,
        "folds": [{
            "split": result.model_split,
            "difficulty_class": result.predicted_class,
            "regression": result.aggregated_score,
            "descriptor_scores": list(result.descriptor_scores),
            "ordinal_probabilities": list(result.ordinal_probabilities),
        } for result in prediction.predictions],
        "median_difficulty_class": prediction.median_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = predict_musicxml(args.upstream, args.score)
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")


if __name__ == "__main__":
    main()
