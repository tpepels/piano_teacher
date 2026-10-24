#!/usr/bin/env python3
"""Compatibility entry point for the canonical native Verovio audit.

The seven-case manifest and source_exercise remain available to corpus and
source-engraving consumers. Executing this file forwards all arguments and
the exit status to scripts/check_native_verovio_overlay.py.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Phrase
from piano_teacher.score import import_piece, render_layout


ROOT = Path(__file__).resolve().parents[1]
MIDI_DIR = ROOT / "midi"
# Explicit manifest: a rename or deletion must fail, not silently remove a test.
CASES = (
    ("Ala_–_Joep_Beving.midi", "left"),
    ("Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi", "right"),
    ("Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", "right"),
    ("Danny_Boy(Bill_Evans_Ver_).midi", "both"),
    ("Merry-Go-Round-of-Life.midi", "both"),
    ("Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", "both"),
    ("Waltz_for_Debby.midi", "both"),
)


def _name(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", Path(filename).stem).strip("-").lower()


def source_exercise(filename: str, hand: str, bars: int = 2):
    """Use original source measures at the application's 40% practice tempo."""
    piece, _ = import_piece(MIDI_DIR / filename)
    assert len(piece.bar_boundaries) >= bars + 1, (
        f"{filename}: missing requested {bars}-bar source grid"
    )
    end = piece.bar_boundaries[bars]
    notes = tuple(n for n in piece.notes if 0 <= n.start < end)
    assert notes, f"{filename}: no notes in the first {bars} measures"
    phrase = Phrase(1, 1, bars, 0, end, notes)
    exercise = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
    )
    # Matches e.g. Ala 44/110, Autumn Leaves 76/190, Chopin 24/60.
    bpm = max(1, round(piece.bpm * .4))
    # Match PracticeEngine.engraving(): only compact exercises use one
    # Verovio system. Longer passages retain their multipage source layout.
    compact_exercise = bars <= 12 and end <= 48
    engraving = render_layout(exercise, 1, bars, hand,
                              total_beats=end, bpm=bpm,
                              continuous=compact_exercise)
    if not compact_exercise:
        assert not engraving.layout["continuous_score"], (
            "Long MIDI source unexpectedly used a compact layout"
        )
    require_lesson_alignment(phrase, engraving.layout, hand)
    assert len(engraving.pages) == int(engraving.layout["pages"])
    if bars >= 13 and filename.startswith("Chopin"):
        safe_headers = engraving.layout["strip_trim_safe_starts"]
        assert 6.5 in safe_headers and 0.5 not in safe_headers, (
            "A genuine 1/8 -> 12/8 change must stay engraved, while later "
            "printed-system clefs must not reappear in the continuous strip"
        )
    assert len(engraving.layout["notes"]) == len(exercise.note_bindings), (
        f"{filename}: Verovio dropped or duplicated a source-bound note"
    )
    return piece, phrase, exercise, engraving, bpm


def main(argv=None) -> int:
    print("Forwarding to canonical native audit: check_native_verovio_overlay.py",
          file=sys.stderr, flush=True)
    arguments = sys.argv[1:] if argv is None else argv
    return subprocess.run([
        sys.executable, str(ROOT / "scripts/check_native_verovio_overlay.py"),
        *arguments,
    ]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
