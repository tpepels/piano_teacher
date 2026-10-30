"""Check the *original* RubricNet MusicXML descriptor code against its oracle.

This runs only on a locally checked-out, pinned upstream repository with its
original optional dependencies installed. It imports the upstream extractor,
not Piano Teacher's heuristic score features. It never changes student state.

The official `predict.py::check_features_extractor` publishes twelve expected
values for `inven01.musicxml`; these are reproduced in this contract.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from piano_teacher.research.rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT

REFERENCE_DESCRIPTORS = {
    "rh_pitch_set_lz": 78,
    "lh_pitch_set_lz": 76,
    "rh_pitch_range": 24.0,
    "lh_pitch_range": 34.0,
    "lh_average_pitch": 57,
    "rh_average_pitch": 72,
    "lh_average_ioi_seconds": 0.40148387096774196,
    "rh_average_ioi_seconds": 0.3745966386554622,
    "rh_displacement_rate": 0.7658227848101266,
    "lh_displacement_rate": 0.5902777777777778,
    "lh_pitch_entropy": 4.080580792251002,
    "rh_pitch_entropy": 3.7591406644141703,
}

# Run in a fresh process; upstream module initialization may load dependencies
# that should never become application-global in Piano Teacher.
_REFERENCE_CODE = r'''
import json
import sys
from music21.tempo import MetronomeMark
from extractor.DifficultyFeatures.code.difficulty_calculators import INSTRUMENT_DIFFICULTY_CALCULATORS
from extractor.DifficultyFeatures.code.raw_data_extractors import (
    CIPIFeatureExtractor, convert_offsets
)
filename = sys.argv[1]
warnings = set()
raw = CIPIFeatureExtractor().extract_raw_data_map(
    [filename], warnings, metronome_mark=MetronomeMark(100),
    ignore_warnings=False
)
convert_offsets(raw)
entry = INSTRUMENT_DIFFICULTY_CALCULATORS['cipi'].estimate_difficulty_map(
    raw, warnings
)
names = json.loads(sys.argv[2])
print("UPSTREAM_REFERENCE_DESCRIPTORS=" + json.dumps(
    {name: entry[name] for name in names}, sort_keys=True))
'''

def reference_descriptors(upstream: Path, score: Path,
                          timeout: float = 35) -> dict[str, float]:
    root = upstream.resolve()
    # Prevent accidentally invoking arbitrary unpinned upstream source.
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=5).stdout.strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError(f"Expected pinned RubricNet commit {UPSTREAM_COMMIT}, got {commit}")
    env = dict(os.environ)
    # This addresses unqualified 'common_utils' and 'piano_fingering_argnn'
    # imports in the upstream code without modifying the original checkout.
    env["PYTHONPATH"] = os.pathsep.join((
        str(root), str(root/"extractor/DifficultyFeatures/code"),
        env.get("PYTHONPATH", ""),
    ))
    run = subprocess.run([
        sys.executable, "-c", _REFERENCE_CODE, str(score.resolve()),
        json.dumps(list(BASIC_FEATURES)),
    ], check=True, capture_output=True, text=True, cwd=root, env=env,
        timeout=timeout)
    marker = "UPSTREAM_REFERENCE_DESCRIPTORS="
    matches = [line[len(marker):] for line in run.stdout.splitlines()
               if line.startswith(marker)]
    if len(matches) != 1:
        raise ValueError(f"Missing upstream descriptor response: {run.stdout[-2000:]}")
    return json.loads(matches[0])

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--score", type=Path, default=None)
    parser.add_argument("--check-oracle", action="store_true")
    args = parser.parse_args()
    score = args.score or (args.upstream/"inven01.musicxml")
    observed = reference_descriptors(args.upstream, score)
    if args.check_oracle:
        for name, expected in REFERENCE_DESCRIPTORS.items():
            if name not in observed or abs(observed[name]-expected) > 1e-9:
                raise AssertionError(
                    f"Upstream RubricNet source descriptor {name}: "
                    f"expected {expected!r}, got {observed.get(name)!r}")
    print(json.dumps(observed, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
