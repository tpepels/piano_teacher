#!/usr/bin/env python3
"""Smoke-test the real MIDI/MusicXML -> Verovio -> SVG + timing-map path.

Usage: python scripts/check_engraving.py '/path/to/song.mid'
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from piano_teacher.score import import_piece, render_layout


def check(path: Path) -> dict:
    piece, notation = import_piece(path)
    if not piece.phrases:
        raise ValueError("There are no practice passages in this file")
    passage = piece.phrases[0]
    score = render_layout(notation, passage.first_bar, passage.last_bar, "both",
                          total_beats=passage.end - passage.start)
    return {"piece": piece.title, "bars": (passage.first_bar, passage.last_bar),
            "pages": len(score.pages), "anchors": len(score.layout["anchors"]),
            "positioned_notes": len(score.layout["notes"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Piano Teacher's real SVG engraving")
    parser.add_argument("music_file", type=Path, help="MIDI or MusicXML to engrave")
    args = parser.parse_args()
    try:
        result = check(args.music_file)
    except Exception as exc:
        print(f"ENGRAVING FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"ENGRAVING OK: {result['piece']} - bars {result['bars'][0]}-{result['bars'][1]}, "
          f"{result['pages']} page(s), {result['anchors']} anchors, "
          f"{result['positioned_notes']} timed notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
