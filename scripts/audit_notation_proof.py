#!/usr/bin/env python3
"""Reproducible Phase 1 semantic evidence report, independent of screen pixels.

Run:
    python scripts/audit_notation_proof.py --out /tmp/notation-proof-phase1.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.proof import (
    verify_generated_engraving, verify_original_musicxml,
)
from piano_teacher.score import import_piece


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "musical_fidelity"
SOURCES = (
    "xml_chord_ties.musicxml",
    "xml_grandstaff_voices.musicxml",
    "xml_keys_spelling.musicxml",
    "xml_quintuplets.musicxml",
)


def audit_source(path: Path) -> dict:
    piece, _ = import_piece(path)
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1,
                    0, piece.bar_boundaries[-1], piece.notes)
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
    )
    native = build_score_model(score, boundaries=piece.bar_boundaries)
    original = verify_original_musicxml(path.read_text(encoding="utf-8"), native)
    generated = verify_generated_engraving(score.musicxml, native)
    return {"name": path.name, "original_source": original,
            "verovio_native_contract": generated,
            "passed": original["passed"] and generated["passed"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    records = []
    for name in SOURCES:
        try:
            records.append(audit_source(CORPUS / name))
        except Exception as exc:
            records.append({"name": name, "passed": False,
                            "errors": [f"{type(exc).__name__}: {exc}"]})
    report = {
        "phase": 1, "passed": all(r["passed"] for r in records),
        "scope": "original MusicXML semantic facts and generated XML/native event inventory",
        "not_verified": [
            "native pixel/shape/placement fidelity",
            "beam and slur geometry",
            "full user library corpus",
            "MIDI transcription choices",
            "unsupported source annotations and grace ornaments",
        ],
        "source_attacks_checked": sum(
            r.get("original_source", {}).get("source_attacks", 0)
            for r in records),
        "native_symbols_checked": sum(
            r.get("verovio_native_contract", {}).get("native_symbols", 0)
            for r in records),
        "scores": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Phase 1: {sum(r['passed'] for r in records)}/{len(records)} scores; "
          f"{report['source_attacks_checked']} original attacks; "
          f"{report['native_symbols_checked']} native events")
    for record in records:
        if not record["passed"]:
            print(json.dumps(record, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
