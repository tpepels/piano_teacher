#!/usr/bin/env python3
"""Compare generated lessons using the same imported source and settings.

Usage:
  python scripts/compare_exercise_strategies.py song.mid
  python scripts/compare_exercise_strategies.py song.musicxml --json
  python scripts/compare_exercise_strategies.py song.mid --strategies legacy,fukuda,coda-part,fukuda+coda-part
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan


DEFAULT_STRATEGIES = "legacy,fukuda,coda-part,feature-gated,fukuda+coda-part"


def compare(path: Path, strategies: tuple[str, ...]) -> dict:
    piece, _ = import_piece(path)
    results = {}
    for spec in strategies:
        plan = LearningPlan(piece, exercise_strategy=spec)
        steps = []
        for step in plan.lesson_steps:
            exercise = plan.exercises[step.exercise_index]
            variant = next(v for v in plan._stage_variants(exercise, step.hand)
                           if v.level == step.level)
            steps.append({
                "kind": step.kind, "hand": step.hand, "level": step.level,
                "bars": [step.first_bar, step.last_bar],
                "key": step.key,
                "note_count": len(variant.notes),
                "attacks": len({round(n.start, 6) for n in variant.notes}),
                "source_ids": [n.source_id for n in variant.notes],
                "notes": [{"beat": n.start, "duration": n.end - n.start,
                           "pitch": n.pitch, "hand": n.hand}
                          for n in variant.notes],
            })
        results[spec] = {
            "steps": steps,
            "step_count": len(steps),
            "learn_step_count": sum(s["kind"] == "learn" for s in steps),
        }
    return {
        "piece": piece.title, "bpm": piece.bpm,
        "source_note_count": len(piece.notes),
        "strategies": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("piece", type=Path, help="MIDI or MusicXML score")
    parser.add_argument("--strategies", default=DEFAULT_STRATEGIES,
                        help="Comma-separated strategy names and + compositions")
    parser.add_argument("--json", action="store_true", help="Full source-aligned JSON report")
    parser.add_argument("--limit", type=int, default=35, help="Max stages printed per strategy")
    args = parser.parse_args()
    specs = tuple(s.strip() for s in args.strategies.split(","))
    if not specs or any(not s for s in specs):
        parser.error("--strategies must have nonempty entries")
    report = compare(args.piece, specs)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f'{report["piece"]}: {report["source_note_count"]} notes at {report["bpm"]} BPM')
    for name, data in report["strategies"].items():
        print(f'\n[{name}] {data["step_count"]} total steps, {data["learn_step_count"]} learning steps')
        for step in data["steps"][:max(0, args.limit)]:
            print(f'  {step["kind"]:7} bars {step["bars"][0]}-{step["bars"][1]} '
                  f'{step["hand"]:5} {step["level"]:25} '
                  f'{step["note_count"]:3} notes / {step["attacks"]:2} attacks')
        if len(data["steps"]) > max(0, args.limit):
            print(f'  ... {len(data["steps"]) - max(0, args.limit)} further steps')


if __name__ == "__main__":
    main()
