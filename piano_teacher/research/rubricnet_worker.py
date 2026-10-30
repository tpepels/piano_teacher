"""Run exact, vendored RubricNet feature extraction in an isolated process.

Imported ONLY via `RubricNetExtractor` when the trained strategy is selected.
The entire original extractor code remains unmodified and is run offline.
"""
from __future__ import annotations

import json
from math import isfinite
import sys

from .rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: rubicnet_worker.py SOURCE.musicxml")

    from music21.tempo import MetronomeMark
    from extractor.DifficultyFeatures.code import difficulty_calculators
    from extractor.DifficultyFeatures.code.difficulty_calculators import (
        INSTRUMENT_DIFFICULTY_CALCULATORS,
    )
    from extractor.DifficultyFeatures.code.raw_data_extractors import (
        CIPIFeatureExtractor, convert_offsets,
    )

    # The published calculator also computes a *non-model* diagnostic,
    # displacement_stuff, whose implementation indexes pitch_sets[1] even
    # for a perfectly valid one-note hand. For that undefined case alone,
    # return neutral diagnostic 0. The trained input feature
    # 'lh_displacement_rate' / 'rh_displacement_rate' is computed by a
    # distinct unchanged function. We keep all vendored source byte-identical.
    original_displacement_stuff = difficulty_calculators.displacement_stuff
    def sparse_hand_safe(pitch_sets):
        if len(pitch_sets) < 2:
            return 0
        return original_displacement_stuff(pitch_sets)
    difficulty_calculators.displacement_stuff = sparse_hand_safe

    warnings = set()
    raw = CIPIFeatureExtractor().extract_raw_data_map(
        [sys.argv[1]], warnings,
        metronome_mark=MetronomeMark(100), ignore_warnings=False)
    convert_offsets(raw)
    values = INSTRUMENT_DIFFICULTY_CALCULATORS["cipi"].estimate_difficulty_map(
        raw, warnings)
    output = {
        "commit": UPSTREAM_COMMIT,
        "features": {name: float(values[name]) for name in BASIC_FEATURES},
    }
    if any(not isfinite(value) for value in output["features"].values()):
        raise ValueError(
            "RubricNet's source descriptors are undefined for this MusicXML. "
            "The published model requires two adequately pitched piano parts; "
            "sparse or rest-only hands are unsupported (no heuristic fallback).")
    print("RUBRICNET_FEATURES=" + json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
