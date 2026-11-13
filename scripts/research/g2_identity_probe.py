"""G2 audit probe (uncommitted): stage identity, reload stability, strategy isolation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from piano_teacher.server import PracticeEngine  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts" / "research"))
from g2_feedback_probe import failed_take, place  # noqa: E402

MIDI = next((ROOT / "midi").glob("J_S_Bach*"))


def keys(engine):
    return [s.key for s in engine.plan.lesson_steps]


def main():
    data = Path(sys.argv[1])
    out = {}
    for strategy in ("coda-fukuda-midi", "fukuda-midi"):
        d = data / strategy
        a = PracticeEngine(d, enable_midi=False)
        a.set_preferences(exercise_strategy=strategy)
        a.load(str(MIDI))
        a.auto = True
        index = next(i for i, ex in enumerate(a.plan.exercises) if ex.kind == "learn")
        place(a, index, "right")
        # Earn some mastery/BPM on the first stage before the failure.
        a.plan.mastered["probe-marker"] = 1
        result, _ = failed_take(a, "wrong", 2, 2)
        a._decide_reengraving(result)
        a._commit_pending()
        after_keys, after_identity, after_bpm = keys(a), a.plan.identity, a.plan.bpm
        a.close()
        b = PracticeEngine(d, enable_midi=False)
        b.load(str(MIDI))
        row = {
            "reload_same_steps": keys(b) == after_keys,
            "reload_same_identity": b.plan.identity == after_identity,
            "reload_bpm": (after_bpm, b.plan.bpm),
            "step_count": len(after_keys),
            "key_prefix": after_keys[0].split(":")[:3],
        }
        mastered_before = dict(b.plan.mastered)
        other = "coda-midi" if strategy != "coda-midi" else "fukuda-midi"
        b.set_preferences(exercise_strategy=other)
        row["other_prefix"] = keys(b)[0].split(":")[:3]
        row["other_shares_keys"] = bool(set(keys(b)) & set(after_keys))
        row["other_mastered_from_first"] = sorted(set(b.plan.mastered) & set(mastered_before))[:3]
        b.set_preferences(exercise_strategy=strategy)
        row["back_same_steps"] = keys(b) == after_keys
        row["back_identity"] = b.plan.identity == after_identity
        b.close()
        out[strategy] = row
        print(strategy, json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
