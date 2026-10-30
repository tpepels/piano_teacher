"""Offline, subprocess-isolated *original* RubricNet MusicXML descriptors.

The vendored MIT-licensed upstream extractor is byte-for-byte preserved. Heavy
optional imports stay in the worker process. No download or model loading
takes place in this module or the ordinary MIDI/audio engine.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from dataclasses import dataclass

from .rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT


class RubricNetUnavailable(RuntimeError):
    """Exact descriptor extraction failed; never substitute heuristic values."""


VENDOR_ROOT = Path(__file__).resolve().parent / "_upstream_rubricnet"


@dataclass(frozen=True)
class RubricNetExtractor:
    python_executable: str = ""
    timeout_seconds: float = 35.0

    def extract(self, source_musicxml: str) -> dict[str, float]:
        if not source_musicxml or not source_musicxml.lstrip().startswith("<"):
            raise RubricNetUnavailable(
                "Trained RubricNet requires the original MusicXML score")
        python = (self.python_executable
                  or os.getenv("PIANO_TEACHER_RUBRICNET_PYTHON", "")
                  or sys.executable)
        if not VENDOR_ROOT.joinpath("extractor", "DifficultyFeatures",
                                     "code", "raw_data_extractors.py").is_file():
            raise RubricNetUnavailable("Pinned RubricNet extractor source is missing")
        # The worker receives a fresh MusicXML file, never a shell command.
        with tempfile.TemporaryDirectory(prefix="piano-rubricnet-") as folder:
            score = Path(folder)/"source.musicxml"
            score.write_text(source_musicxml, encoding="utf-8")
            command = [python, "-m", "piano_teacher.research.rubricnet_worker",
                       str(score)]
            env = os.environ.copy()
            package_root = str(Path(__file__).resolve().parents[2])
            code_root = str(VENDOR_ROOT/"extractor"/"DifficultyFeatures"/"code")
            env["PYTHONPATH"] = os.pathsep.join((
                str(VENDOR_ROOT), code_root, package_root,
                env.get("PYTHONPATH", "")))
            env["MPLBACKEND"] = "Agg"
            try:
                result = subprocess.run(
                    command, cwd=folder, env=env, timeout=self.timeout_seconds,
                    capture_output=True, text=True, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RubricNetUnavailable(
                    "RubricNet offline worker could not run: " + str(exc)) from exc
        if result.returncode:
            diagnostic = (result.stderr or result.stdout)[-1200:]
            raise RubricNetUnavailable(
                "RubricNet source feature worker failed. Install the optional "
                "research dependencies with scripts/setup-rubricnet.sh; "
                f"exit={result.returncode}; {diagnostic}")
        marker = "RUBRICNET_FEATURES="
        matches = [line[len(marker):] for line in result.stdout.splitlines()
                   if line.startswith(marker)]
        if len(matches) != 1:
            raise RubricNetUnavailable("RubricNet worker returned no valid descriptors")
        try:
            data = json.loads(matches[0])
            if (data.get("commit") != UPSTREAM_COMMIT
                    or set(data["features"]) != set(BASIC_FEATURES)):
                raise ValueError("Unexpected descriptor names or source revision")
            return {name: float(data["features"][name]) for name in BASIC_FEATURES}
        except (ValueError, TypeError, KeyError) as exc:
            raise RubricNetUnavailable("Invalid worker feature result") from exc
