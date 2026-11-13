"""G2 audit probe (uncommitted): generate every selectable curriculum for the corpus.

For each MIDI in midi/ and each selectable exercise strategy, load the piece
through the real PracticeEngine API (settings -> load) in a throwaway data
directory, then inspect the generated LearningPlan. Writes JSON to argv[1].
Never touches the owner's library or progress database.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from piano_teacher.exercise_strategies import available_strategies  # noqa: E402
from piano_teacher.learning import LearningPlan  # noqa: E402
from piano_teacher.lesson_stage_semantics import difference  # noqa: E402
from piano_teacher.server import PracticeEngine  # noqa: E402


def audit_plan(plan):
    piece = plan.piece
    source = {n.source_id: n for n in piece.notes}
    kinds = Counter(ex.kind for ex in plan.exercises)
    hands = Counter(h for ex in plan.exercises for h in plan.lesson_definition.stage_sequences
                    if False)
    techniques = Counter()
    problems = []
    non_meaningful = 0
    zero = 0
    stages_total = 0
    learn_with_transform = 0
    learn_hand_lessons = 0
    slow_effective = []
    for ex in plan.exercises:
        from piano_teacher.lesson_generators import lesson_hands
        for hand in lesson_hands(ex):
            stages = plan.lesson_definition.stages(ex, hand)
            original = stages[-1]
            if ex.kind == "learn":
                learn_hand_lessons += 1
                if len(stages) > 1:
                    learn_with_transform += 1
            for st in stages:
                stages_total += 1
                v = st.variant
                if not v.notes:
                    zero += 1
                    problems.append(f"zero-notes {ex.key}/{hand}/{v.level}")
                for n in v.notes:
                    s = source.get(n.source_id)
                    if s is None or s.pitch != n.pitch or s.hand != n.hand:
                        problems.append(f"outside-source {ex.key}/{hand}/{v.level}/{n.source_id}")
                        break
                if st is not original:
                    try:
                        d = difference(st, original)
                        if not d.meaningful:
                            non_meaningful += 1
                            problems.append(f"renamed-copy {ex.key}/{hand}/{v.level}")
                    except ValueError as exc:
                        problems.append(f"difference-error {ex.key}/{hand}/{v.level}: {exc}")
                techniques[f"{st.origin or '-'}:{st.technique or v.level}"] += 1
                factor = getattr(st.tempo_policy, "factor", None)
                if factor:
                    slow_effective.append(round(plan.start_bpm / factor, 1))
    steps = plan.lesson_steps
    return {
        "exercises": len(plan.exercises),
        "kinds": dict(kinds),
        "lesson_steps": len(steps),
        "stages_total": stages_total,
        "learn_hand_lessons": learn_hand_lessons,
        "learn_with_transform": learn_hand_lessons and learn_with_transform,
        "techniques": dict(techniques),
        "zero_note_stages": zero,
        "renamed_copies": non_meaningful,
        "problems": problems[:10],
        "problem_count": len(problems),
        "start_bpm": plan.start_bpm, "target_bpm": plan.target_bpm,
        "min_slow_effective_bpm": min(slow_effective) if slow_effective else None,
        "step_keys": [s.key for s in steps],
    }


def main():
    out = Path(sys.argv[1])
    work = Path(sys.argv[2])
    only = sys.argv[3:] or None
    strategies = [s["id"] for s in available_strategies()]
    rows = []
    for midi in sorted((ROOT / "midi").glob("*.mid*")):
        if only and not any(o in midi.name for o in only):
            continue
        for strategy in strategies:
            row = {"piece": midi.name, "strategy": strategy}
            data = work / f"{abs(hash((midi.name, strategy)))}"
            engine = None
            try:
                engine = PracticeEngine(data, enable_midi=False)
                engine.set_preferences(exercise_strategy=strategy)
                began = time.perf_counter()
                engine.load(str(midi))
                row["load_seconds"] = round(time.perf_counter() - began, 2)
                piece = engine.plan.piece
                began = time.perf_counter()
                again = LearningPlan(
                    piece, exercise_strategy=strategy,
                    fukuda_mistakes=frozenset(), feedback={})
                row["generate_seconds"] = round(time.perf_counter() - began, 2)
                row["generator"] = engine.plan.lesson_generator.name
                row.update(audit_plan(engine.plan))
                # Same inputs as a reload: stable keys?
                row["stable_reload"] = [s.key for s in again.lesson_steps] == row["step_keys"]
                # Library-free direct construction (tests' default, mistakes=None)
                direct = LearningPlan(piece, exercise_strategy=strategy)
                row["direct_stages_total"] = audit_plan(direct)["stages_total"]
                row["direct_techniques"] = audit_plan(direct)["techniques"]
                row["notes"] = len(piece.notes)
                row["bars"] = len(piece.bar_boundaries) - 1
                del row["step_keys"]
            except Exception as exc:  # noqa: BLE001 - audit records failures
                row["error"] = f"{type(exc).__name__}: {exc}"
                row["trace"] = traceback.format_exc()[-1500:]
            finally:
                if engine is not None:
                    try:
                        engine.close()
                    except Exception:  # noqa: BLE001
                        pass
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in (
                "piece", "strategy", "load_seconds", "generate_seconds", "exercises",
                "kinds", "stages_total", "direct_stages_total", "problem_count", "error")}),
                flush=True)
            out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
