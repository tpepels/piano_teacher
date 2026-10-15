#!/usr/bin/env python3
"""Run one real learner journey through guided ideas, recovery, mastery and modes.

This opts into the complete instructional Godot journey so the same imported
source and real MIDI callback events continue into Listen and Perform after an
earned stage transition. Software audio checks do not prove speaker audibility.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.smoke_instructional_godot import run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=Path("/tmp/piano-teaching-p5"))
    options = parser.parse_args()
    try:
        run(options.output_dir,finish_modes=True)
    except Exception as error:
        traceback.print_exc()
        print(f"STUDENT JOURNEY FAILED: {error}",file=sys.stderr)
        raise SystemExit(1)
