"""G2 audit probe (uncommitted): inject failed original-score takes.

Loads real corpus MIDI through PracticeEngine in a throwaway data directory,
places the plan on an original-level stage, seals a failed Assessment with a
chosen error family, then runs the production take-end decision
(_decide_reengraving) and settlement (_commit_pending). Records whether the
decision agreed with what settlement did and how the stages changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from piano_teacher.lesson_generators import lesson_hands  # noqa: E402
from piano_teacher.practice import Assessment, NoteAssessment  # noqa: E402
from piano_teacher.server import PracticeEngine  # noqa: E402


def techniques(plan, ex, hand):
    return [s.technique or s.variant.level for s in plan.lesson_definition.stages(ex, hand)]


def place(engine, index, hand):
    p = engine.plan
    p.select(index)
    if hand in p.hands:
        p.set_hand(hand)
    p.variant_index = len(p.variants) - 1
    assert p.active_variant.level == "original"


def failed_take(engine, status, count, offset=0):
    p = engine.plan
    notes = p.active_phrase.notes
    if p.hand != "both":
        notes = tuple(n for n in notes if n.hand == p.hand)
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    bad = {n.source_id for n in ordered[offset:offset + count]}
    result = Assessment(tuple(NoteAssessment(n, status if n.source_id in bad else "correct")
                              for n in notes), 0)
    engine.midi.port = object()
    engine.start()
    engine.measurement.seal(engine.recorder.presses, state="completed",
                            reason="full_passage", result=result,
                            eligible=p.bpm >= p.target_bpm)
    engine.pending_result = result
    engine._pending_assessed_bpm = p.bpm
    return result, bad


def scenario(midi, strategy, status, *, where, data, count=2, offset=2, repeat=1):
    engine = PracticeEngine(data, enable_midi=False)
    row = {"piece": midi.name[:28], "strategy": strategy, "status": status, "where": where}
    try:
        engine.set_preferences(exercise_strategy=strategy)
        engine.load(str(midi))
        engine.auto = True
        p = engine.plan
        if where == "perform":
            index = max(i for i, ex in enumerate(p.exercises) if ex.kind == "perform")
            hand = "both"
            offset = len(p.exercises[index].phrase.notes) // 2  # mid-piece mistakes
        else:
            index = next(i for i, ex in enumerate(p.exercises) if ex.kind == "learn"
                         and "right" in lesson_hands(ex))
            hand = "right"
        ex_before = p.exercises[index]
        row["passage"] = ex_before.key
        row["before"] = techniques(p, ex_before, hand)
        row["exercises_before"] = len(p.exercises)
        row["accepts_feedback"] = p.accepts_performance_feedback
        for attempt in range(repeat):
            if attempt == 0:
                place(engine, index, hand)
            if engine.plan.active_variant.level != "original":
                row[f"take{attempt+1}"] = "skipped: plan moved to a scaffold stage"
                break
            identity = engine.plan.identity
            revision = engine.score_revision
            result, bad = failed_take(engine, status, count, offset)
            engine._decide_reengraving(result)
            decided = engine._decided_reengraving[1]
            message = engine._commit_pending()
            moved = engine.plan.identity != identity
            row[f"take{attempt+1}"] = {
                "decided_reengrave": decided,
                "actually_moved": moved,
                "agree": decided == moved,
                "revision_delta": engine.score_revision - revision,
                "remediation": getattr(engine._remediation_pending, "action", None),
                "now_at": f"{engine.plan.exercise.key}/{engine.plan.hand}/"
                          f"{engine.plan.active_stage.technique or engine.plan.active_variant.level}",
                "message": message[:80] if isinstance(message, str) else str(message)[:80],
                "evidence": len(engine.fukuda_mistakes.evidence(engine.fingerprint)),
            }
        p = engine.plan
        same = next((ex for ex in p.exercises if ex.key == ex_before.key), None)
        row["after"] = techniques(p, same, hand) if same is not None and hand in lesson_hands(same) else None
        row["exercises_after"] = len(p.exercises)
        row["new_keys"] = sorted({ex.key for ex in p.exercises} -
                                 {k for k in [ex_before.key]} -
                                 set(row.get("_old_keys", [])))[:4]
    except Exception as exc:  # noqa: BLE001
        import traceback
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["trace"] = traceback.format_exc()[-1200:]
    finally:
        try:
            engine.close()
        except Exception:  # noqa: BLE001
            pass
    return row


def main():
    out = Path(sys.argv[1])
    work = Path(sys.argv[2])
    pieces = [p for p in sorted((ROOT / "midi").glob("*.mid*"))
              if any(k in p.name for k in ("Bach", "Mozart", "Entertainer", "Gymnop"))]
    rows = []
    n = 0
    for midi in pieces:
        for strategy in ("coda-fukuda-midi", "fukuda-midi", "coda-midi"):
            for status, where in (("wrong", "learn"), ("late", "learn"),
                                  ("short", "learn"), ("wrong", "perform")):
                n += 1
                row = scenario(midi, strategy, status, where=where, data=work / str(n),
                               repeat=2)
                rows.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "trace"}), flush=True)
                out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
