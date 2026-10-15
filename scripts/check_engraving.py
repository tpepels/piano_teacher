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
from piano_teacher.raster import rasterize_score
from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment


def check(path: Path, output: Path | None = None) -> dict:
    piece, _ = import_piece(path)
    if not piece.phrases:
        raise ValueError("There are no practice passages in this file")
    passage = piece.phrases[0]
    notation = build_lesson_score(passage, boundaries=piece.bar_boundaries,
                                 time_signatures=piece.time_signatures,
                                 key_signatures=piece.key_signatures,
                                 clef_changes=piece.clef_changes)
    score = render_layout(notation, passage.first_bar, passage.last_bar, "both",
                          total_beats=passage.end - passage.start)
    require_lesson_alignment(passage, score.layout, "both")
    png = rasterize_score(score.pages[0])
    if output is not None:
        output.write_bytes(png)
    return {"piece": piece.title, "bars": (passage.first_bar, passage.last_bar),
            "pages": len(score.pages), "anchors": len(score.layout["anchors"]),
            "positioned_notes": len(score.layout["notes"])}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Piano Teacher's real SVG engraving")
    parser.add_argument("music_file", type=Path, help="MIDI or MusicXML to engrave")
    parser.add_argument("--output", type=Path, help="Save rendered PNG for inspection")
    args = parser.parse_args()
    try:
        result = check(args.music_file, args.output)
    except Exception as exc:
        print(f"ENGRAVING FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"ENGRAVING OK: {result['piece']} - bars {result['bars'][0]}-{result['bars'][1]}, "
          f"{result['pages']} page(s), {result['anchors']} anchors, "
          f"{result['positioned_notes']} timed notes")
    if args.output:
        print(f"Saved PNG: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
