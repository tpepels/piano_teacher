"""Run exact, vendored RubricNet feature extraction in an isolated process.

Imported ONLY via `RubricNetExtractor` when the trained strategy is selected.
The entire original extractor code remains unmodified and is run offline.
"""
from __future__ import annotations

import json
import sys

from .rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: rubicnet_worker.py SOURCE.musicxml")

    from music21.tempo import MetronomeMark
    from extractor.DifficultyFeatures.code.difficulty_calculators import (
        INSTRUMENT_DIFFICULTY_CALCULATORS,
    )
    from extractor.DifficultyFeatures.code.raw_data_extractors import (
        CIPIFeatureExtractor, convert_offsets,
    )

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
    print("RUBRICNET_FEATURES=" + json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
