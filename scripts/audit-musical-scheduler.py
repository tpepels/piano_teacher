#!/usr/bin/env python3
"""Repository-wide removal gate for obsolete musical scheduling APIs.

Scan ALL first-party Python and Godot sources, including tests and scripts.
This is deliberately a source-level integration contract: a removed scheduling
facade must not survive in an unselected test or rarely run application route.
The only allowed implementation of beat-to-second scheduling is the
musical_scheduler module; geometry-only source code is exempt.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
# Keep the spelling of banned names out of the source itself so that this
# guard can be included in a full-tree scan without a special case for names.
REMOVED = tuple("".join(parts) for parts in (
    ("repeat_", "deadline"),
    ("scheduled_", "offscreen_start"),
    ("planned_retry_", "reverse_seconds"),
    ("lead_", "in_beats"),
    ("_short_rest_", "deadline"),
    ("_automatic_stream_", "deadline"),
    ("_continuation_", "deadline"),
    ("SHORT_REST_", "LATENCY_SECONDS"),
))
SOURCES = ("piano_teacher", "godot", "tests", "scripts")
EXTENSIONS = frozenset({".py", ".gd", ".sh", ".cpp", ".hpp", ".h"})
BAD_IMPORT = re.compile(
    r"from\s+[^\n]*attempt_progression\s+import\s+[^\n]*\bSETTLEMENT_SECONDS\b"
)
OLD_ARITHMETIC = re.compile(
    r"\b(?:self\.plan\.bpm|self\._presentation_bpm|bpm)\s*/\s*60(?:\.0)?\b"
    r"|\b60(?:\.0)?\s*/\s*(?:self\.plan\.bpm|self\._presentation_bpm|bpm)\b"
)
SCHEDULING_OWNERS = {
    "piano_teacher/server.py",
    "piano_teacher/visual_transport.py",
    "piano_teacher/application/attempt_progression.py",
    "piano_teacher/application/teaching_continuation.py",
    "piano_teacher/application/transport_commands.py",
    "piano_teacher/application/listen_session.py",
}


def audit() -> list[str]:
    defects = []
    for directory in SOURCES:
        for path in sorted((ROOT / directory).rglob("*")):
            if not path.is_file() or path.suffix not in EXTENSIONS:
                continue
            rel = path.relative_to(ROOT).as_posix()
            # Vendored editor addon is not owned by Piano Teacher.
            if rel.startswith("godot/addons/"):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for name in REMOVED:
                    if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) +
                                 r"(?![A-Za-z0-9_])", line):
                        defects.append(f"{rel}:{number}: removed scheduling API {name}")
                if BAD_IMPORT.search(line):
                    defects.append(f"{rel}:{number}: settlement constant imported from former owner")
                if rel in SCHEDULING_OWNERS and OLD_ARITHMETIC.search(line):
                    defects.append(f"{rel}:{number}: independent beat/BPM scheduling arithmetic")
    return defects


if __name__ == "__main__":
    defects = audit()
    if defects:
        print("MUSICAL_SCHEDULER_LEGACY_REFS:", len(defects))
        print("\n".join(defects))
        raise SystemExit(1)
    print("MUSICAL_SCHEDULER_LEGACY_REFS: 0")
