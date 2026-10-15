#!/usr/bin/env python3
"""Run the normal launcher and capture all screens against a real local score."""
from pathlib import Path
import argparse
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.file.expanduser().resolve(strict=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    for key, subdir in [("XDG_DATA_HOME", "data"), ("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache")]:
        environment[key] = str(output / subdir)
    with (output / "launcher.log").open("w") as log:
        result = subprocess.run([str(ROOT / "run.sh"), "--script",
            str(ROOT / "tests/godot/ui_review.gd"), "--", str(output), str(source)],
            cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    transcript = (output / "launcher.log").read_text()
    print(transcript[-4000:])
    errors = any(word in transcript for word in ("SCRIPT ERROR", "ERROR:", "UI_REVIEW:["))
    raise SystemExit(result.returncode or int(errors))
