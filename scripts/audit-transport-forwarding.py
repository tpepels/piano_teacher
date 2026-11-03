#!/usr/bin/env python3
"""Audit PracticeEngine transport aliases before deleting legacy forwarding.

Run on a checkout. This reports code using direct engine field attributes,
including tests not selected by bounded CI. It is intentionally read-only.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "run_at", "play_from_beat", "pending_rewind", "paused", "paused_at",
    "next_at", "visual_offset_beats", "_preview_loop_pending",
    "_visual_rewind_from", "_visual_rewind_to", "_visual_rewind_at",
    "_visual_rewind_seconds", "_retry_previous_pass",
    "practice_preparation", "_preparation_pending", "_preparation_at",
    "visual_gap_beats",
)
# Report only likely engine owners. A final AST review is required before
# mutating a path: many other components legitimately have 'paused' fields.
DIRECT = re.compile(r"\b(?:app|engine|e|server|teacher|practice_engine|self)\.(" +
                    "|".join(re.escape(v) for v in FIELDS) + r")\b")
if __name__ == "__main__":
    files = []
    for root in (ROOT / "piano_teacher", ROOT / "tests", ROOT / "scripts"):
        for file in sorted(root.rglob("*.py")):
            if file.resolve() == Path(__file__).resolve():
                continue
            content = file.read_text(encoding="utf-8")
            hits = DIRECT.findall(content)
            if hits:
                files.append((file.relative_to(ROOT).as_posix(), len(hits),
                              ",".join(sorted(set(hits)))))
    print("TRANSPORT_ALIAS_CALLERS:", len(files))
    for path, n, fields in files:
        print(f"TRANSPORT_ALIAS_REF: {path} | {n} | {fields}")
