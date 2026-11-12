#!/usr/bin/env python3
"""Compare actual first-stage MIDI data for legacy, Coda and Coda+Fukuda.

Usage:
    .venv/bin/python scripts/inspect-lesson-wiring.py ~/Music/path/to/piece.mid

This is an audit, not a lesson generator: no progress, settings or source file
is changed. A same-sounding stage is reported as such rather than relabeled.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Support direct invocation from a clean checkout without a pip -e install.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_stage_semantics import describe, difference
from piano_teacher.music import load_midi


def _identities(notes) -> tuple:
    return tuple(sorted((n.source_id, n.pitch,
                         round(n.start, 8), round(n.end, 8))
                        for n in notes))


def _report(plan: LearningPlan) -> dict:
    stage = plan.active_stage
    reference = plan.stages[-1]
    source = _identities(reference.variant.notes)
    selected = _identities(stage.variant.notes)
    tempo = stage.tempo_map(plan.bpm)
    detail = (describe(stage, reference)
              if plan.generator_registration is not None
              and plan.generator_registration.midi_only
              else {"family": "Legacy", "label": stage.variant.level,
                    "change": "source lesson", "meaningful": selected != source})
    all_stage_changes = []
    for current in plan.stages:
        if (plan.generator_registration is not None
                and plan.generator_registration.midi_only):
            d = difference(current, reference)
            all_stage_changes.append({
                "level": current.variant.level, "removed": d.removed,
                "retimed": d.retimed, "effective_tempo": bool(d.tempo_changed)})
        else:
            all_stage_changes.append({"level": current.variant.level})
    return {
        "strategy": plan.profile,
        "first_measures": [plan.active_phrase.first_bar, plan.active_phrase.last_bar],
        "stage": detail,
        "stage_count": len(plan.stages),
        "first_stage_level": stage.variant.level,
        "source_notes": len(source), "selected_notes": len(selected),
        "first_selected_beat": (min(n.start for n in stage.variant.notes)
                                - stage.variant.phrase.start),
        "selected_note_fingerprint": hashlib.sha256(
            repr(selected).encode()).hexdigest()[:16],
        "selected_bpm": plan.bpm,
        "effective_bpm": tempo.bpm_at(0) if tempo else plan.bpm,
        "stages": all_stage_changes,
        "_actual_notes": selected,
    }


def audit(filename: Path) -> dict:
    piece = load_midi(filename)
    reports = [_report(LearningPlan(piece, exercise_strategy=strategy))
               for strategy in ("source-progression", "coda-fukuda-midi")]
    legacy_notes = reports[0]["_actual_notes"]
    for report in reports:
        report["same_first_stage_as_legacy"] = (
            report["_actual_notes"] == legacy_notes)
        report["shared_source_ids_with_legacy"] = len(
            {n[0] for n in report["_actual_notes"]}
            & {n[0] for n in legacy_notes})
        report.pop("_actual_notes")
    return {"source": piece.title, "original_bpm": piece.bpm,
            "original_notes": len(piece.notes),
            "original_measures": len(piece.bar_boundaries)-1,
            "first_stages": reports}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: inspect-lesson-wiring.py PATH_TO_MIDI", file=sys.stderr)
        return 2
    filename = Path(sys.argv[1]).expanduser()
    if not filename.is_file() or filename.suffix.lower() not in (".mid", ".midi"):
        print("Expected one existing .mid/.midi file", file=sys.stderr)
        return 2
    print(json.dumps(audit(filename), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
