"""Reproduce camera-ready RubricNet CIPI held-out metrics from official data.

Pure-Python inference with five exported authentic fold bundles; no PyTorch,
scikit-learn, training, network at app startup or surrogate feature extractor.

Optional --download evaluates the exact pinned public descriptor dataset and
original fold-specific test IDs, using Git blob hashes before JSON parsing.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from urllib.request import urlopen

from piano_teacher.research.rubricnet_assets import (
    OFFICIAL_EVALUATION, UPSTREAM_COMMIT,
)
from piano_teacher.research.rubricnet_core import RubricNetEnsemble
from scripts.research.fetch_rubricnet_assets import git_blob_sha


def verified_reference_data() -> tuple[list[dict], dict]:
    data = {}
    for path, expected_sha in OFFICIAL_EVALUATION.items():
        url = ("https://raw.githubusercontent.com/PRamoneda/rubricnet/"
               + UPSTREAM_COMMIT + "/" + path)
        with urlopen(url, timeout=15) as response:
            raw = response.read(1_000_000)
        if git_blob_sha(raw) != expected_sha:
            raise ValueError(f"CIPI source checksum mismatch: {path}")
        data[path] = json.loads(raw)
    return (data["features/cipi-features-ISMIR24.json"],
            data["rubricnet/cipi_splits.json"])


def evaluate(ensemble: RubricNetEnsemble, features: list[dict],
             splits: dict) -> dict:
    by_id = {item["id"]: item for item in features}
    if len(by_id) != len(features):
        raise ValueError("Repeated CIPI score IDs")
    fold_reports = []
    for fold in ensemble.folds:
        split = splits[str(fold.split)]
        test = split["test"]
        if not test:
            raise ValueError("Empty held-out split")
        if set(test).intersection(split["train"]) or set(test).intersection(split["val"]):
            raise ValueError("CIPI test/train/validation leakage")
        by_class = defaultdict(list)
        exact = 0
        squared = 0.0
        for identity, truth in test.items():
            if identity not in by_id:
                raise ValueError(f"Missing held-out CIPI descriptors for {identity}")
            pred = fold.predict({name: by_id[identity][name]
                                 for name in fold.feature_names}).predicted_class
            if not 0 <= pred <= 8:
                raise ValueError(f"Invalid RubricNet class {pred} for {identity}")
            if not 0 <= truth <= 8:
                raise ValueError(f"Invalid ground truth {truth} for {identity}")
            error = (pred-truth)**2
            by_class[truth].append(error)
            squared += error
            exact += pred == truth
        n = len(test)
        balanced_accuracy = mean(
            sum(error == 0 for error in errors)/len(errors)
            for errors in by_class.values())
        macro_mse = mean(
            sum(errors)/len(errors) for errors in by_class.values())
        fold_reports.append({
            "split": fold.split, "n": n,
            "accuracy": exact/n, "balanced_accuracy": balanced_accuracy,
            "mse": squared/n, "macro_mse": macro_mse,
        })
    return {
        "source_revision": UPSTREAM_COMMIT,
        "dataset_count": len(by_id), "folds": fold_reports,
        "total_test_predictions": sum(x["n"] for x in fold_reports),
        "mean_balanced_accuracy": mean(x["balanced_accuracy"] for x in fold_reports),
        "mean_macro_mse": mean(x["macro_mse"] for x in fold_reports),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path,
                        default=Path(__file__).resolve().parents[2] /
                        "piano_teacher/research/models/rubricnet")
    parser.add_argument("--download", action="store_true",
                        help="Fetch the pinned public CIPI data with SHA verification")
    parser.add_argument("--features", type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument("--check-published", action="store_true")
    args = parser.parse_args()
    if args.download:
        features, splits = verified_reference_data()
    elif args.features and args.splits:
        features = json.loads(args.features.read_text(encoding="utf-8"))
        splits = json.loads(args.splits.read_text(encoding="utf-8"))
    else:
        parser.error("Specify --download or both --features and --splits")
    report = evaluate(RubricNetEnsemble.load(args.models), features, splits)
    print(json.dumps(report, sort_keys=True, indent=2))
    if args.check_published:
        # The original arXiv abstract reports ~41.4% balanced accuracy and
        # macro MSE ~1.7. Source label/feature versions may differ; make the
        # acceptance window explicit rather than rounding away discrepancies.
        if not (.404 <= report["mean_balanced_accuracy"] <= .424 and
                1.6 <= report["mean_macro_mse"] <= 1.85):
            raise SystemExit("CIPI metrics diverge from published model")


if __name__ == "__main__":
    main()
