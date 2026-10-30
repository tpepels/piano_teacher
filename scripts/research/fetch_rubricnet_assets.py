#!/usr/bin/env python3
"""Fetch the pinned official camera-ready RubricNet artifacts only.

This explicitly invoked research helper performs no imports from upstream,
loads no pickles and verifies every Git-blob SHA before writing anything.
Only fixed allowlisted paths under the pinned source commit are fetched.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

from piano_teacher.research.rubricnet_assets import (
    OFFICIAL_ARTIFACTS, UPSTREAM_COMMIT,
)

RAW_BASE = ("https://raw.githubusercontent.com/PRamoneda/rubricnet/"
            + UPSTREAM_COMMIT + "/")

def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    ).hexdigest()

def download(directory: Path) -> None:
    checked = {}
    for name, expected in OFFICIAL_ARTIFACTS.items():
        with urlopen(RAW_BASE + name, timeout=12) as response:
            content = response.read(200_000)
        if git_blob_sha(content) != expected:
            raise ValueError(f"Official RubricNet asset mismatch: {name}")
        checked[name] = content
    # Atomic, fail-closed: no verified files are written until all ten pass.
    for name, content in checked.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    print(f"Verified {len(checked)} RubricNet assets from {UPSTREAM_COMMIT}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    download(args.destination)
