#!/usr/bin/env python3
"""Compatibility entry point for check_native_verovio_overlay.py.

Uses the canonical CLI (--out, --only, --case, --window-bars) and its
summary.json/audit.json evidence contracts.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_native_verovio_overlay as canonical


def main(argv=None):
    if argv is None:
        return canonical.main()
    previous = sys.argv
    try:
        sys.argv = [str(Path(__file__).resolve()), *argv]
        return canonical.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    raise SystemExit(main())
