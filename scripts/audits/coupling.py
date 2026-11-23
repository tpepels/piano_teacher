#!/usr/bin/env python3
"""Report application-layer coupling for the R1-R8 decoupling plan.

Not a test: prints constructor fan-in above the limit and which modules
reach each domain's internal state holders directly.
Usage: python scripts/audits/coupling.py [--limit 10]
"""
from __future__ import annotations
import ast, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "piano_teacher" / "application"
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 10
HOLDERS = ["visual_transport", "playback_session", "playback", "source_identity",
           "lesson_cursor", "teaching_decisions", "guided_session", "attempt",
           "attempt_settlement", "score_artifact_registry"]

# Modules inside each holder's own domain may use its internals.
DOMAIN_MODULES = {
    "source_identity": {"lesson", "teaching_workflows"},
    "lesson_cursor": {"lesson", "teaching_workflows"},
    "guided_session": {"lesson", "teaching_workflows"},
    "teaching_decisions": {"lesson"},
    "score_artifact_registry": {"score", "score_read_services"},
}
files = sorted(APP.rglob("*.py")) + [ROOT / "piano_teacher" / "server.py"]
fan = {}
reach = defaultdict(set)
for f in files:
    src = f.read_text()
    for cls in (n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)):
        for fn in cls.body:
            if isinstance(fn, ast.FunctionDef) and fn.name in ("__init__", "bind_transport"):
                a = fn.args
                fan[cls.name] = max(fan.get(cls.name, 0), len(a.args) - 1 + len(a.kwonlyargs))
    for h in HOLDERS:
        if re.search(rf"self\.{h}\.", src) and f.stem not in DOMAIN_MODULES.get(h, ()):
            reach[h].add(f.relative_to(APP.parent).with_suffix("").as_posix())

over = sorted(((n, c) for n, c in fan.items() if c > LIMIT), key=lambda x: -x[1])
print(f"constructor fan-in > {LIMIT}: {len(over)} classes (max {max(fan.values())})")
for name, count in over:
    print(f"  {count:3} {name}")
print("modules reaching internal state holders:")
for h in HOLDERS:
    print(f"  {len(reach[h]):3} {h}")
