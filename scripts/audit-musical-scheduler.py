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
import ast
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
SOURCES = ("piano_teacher", "godot", "native", "tests", "scripts")
EXTENSIONS = frozenset({".py", ".gd", ".sh", ".cpp", ".hpp", ".h"})
BAD_IMPORT = re.compile(
    r"from\s+[^\n]*attempt_progression\s+import\s+[^\n]*\bSETTLEMENT_SECONDS\b"
)
OLD_ARITHMETIC = re.compile(
    r"\b(?:self\.plan\.bpm|self\._presentation_bpm|bpm)\s*/\s*60(?:\.0)?\b"
    r"|\b60(?:\.0)?\s*/\s*(?:self\.plan\.bpm|self\._presentation_bpm|bpm)\b"
)
# Godot is a projection client, not an independent timing calculator:
# it must convert quarter-beat deltas through TempoTimeline. Catch hidden
# direct "60/BPM" variants even when they use different variable names.
_GDSCRIPT_BEAT_UNIT = re.compile(
    r"(?<![\w.])(?:60(?:\.0)?|60000(?:\.0)?)(?![\w.])"
)
_GDSCRIPT_BPM_NAME = re.compile(r"\b[a-zA-Z_]*bpm\b",re.IGNORECASE)


def _gd_direct_bpm_conversions(source: str) -> list[int]:
    """Find numeric minute/BPM conversions on executable GDScript lines.

    UI sizes, font sizes, score geometry, named tempo constants and default
    BPM values are not conversions. Complex physical tempo-map calculations
    belong inside res://tempo_timeline.gd only.
    """
    errors = []
    for number, text in enumerate(source.splitlines(), 1):
        code = text.split("#",1)[0]
        if (_GDSCRIPT_BEAT_UNIT.search(code) and
                _GDSCRIPT_BPM_NAME.search(code) and
                ("*" in code or "/" in code)):
            errors.append(number)
    return errors


SCHEDULING_OWNERS = {
    "piano_teacher/server.py",
    "piano_teacher/visual_transport.py",
    "piano_teacher/application/attempt_progression.py",
    "piano_teacher/application/teaching_continuation.py",
    "piano_teacher/application/transport_commands.py",
    "piano_teacher/application/listen_session.py",
}


def _independent_bpm_conversions(source: str) -> list[int]:
    """Find literal-60 BPM conversions even inside multiline expressions.

    Only the scheduler may convert beats/seconds. Code testing an expected
    numerical result is outside this production-only AST check.
    """
    tree = ast.parse(source)
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(
                node.op,(ast.Mult,ast.Div)):
            continue
        if not any(isinstance(side,ast.Constant) and type(side.value) in (
                int,float) and side.value == 60
                   for side in (node.left,node.right)):
            continue
        highest = node
        while isinstance(parents.get(id(highest)),ast.BinOp):
            highest=parents[id(highest)]
        tokens = (
            part.id if isinstance(part,ast.Name) else part.attr
            for part in ast.walk(highest)
            if isinstance(part,(ast.Name,ast.Attribute))
        )
        if any("bpm" in name.lower() for name in tokens):
            lines.add(node.lineno)
    return sorted(lines)


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
            source = path.read_text(encoding="utf-8")
            for number, line in enumerate(source.splitlines(), 1):
                for name in REMOVED:
                    if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) +
                                 r"(?![A-Za-z0-9_])", line):
                        defects.append(f"{rel}:{number}: removed scheduling API {name}")
                if BAD_IMPORT.search(line):
                    defects.append(f"{rel}:{number}: settlement constant imported from former owner")
                if rel in SCHEDULING_OWNERS and OLD_ARITHMETIC.search(line):
                    defects.append(f"{rel}:{number}: independent beat/BPM scheduling arithmetic")
            if rel.startswith("piano_teacher/") and path.suffix == ".py" and (
                    rel != "piano_teacher/application/musical_scheduler.py"):
                for number in _independent_bpm_conversions(source):
                    defects.append(f"{rel}:{number}: direct BPM arithmetic outside scheduler")
            if rel.startswith("godot/") and path.suffix == ".gd" and (
                    rel != "godot/tempo_timeline.gd"):
                for number in _gd_direct_bpm_conversions(source):
                    defects.append(f"{rel}:{number}: direct Godot BPM conversion outside tempo timeline")
    return defects


if __name__ == "__main__":
    defects = audit()
    if defects:
        print("MUSICAL_SCHEDULER_LEGACY_REFS:", len(defects))
        print("\n".join(defects))
        raise SystemExit(1)
    print("MUSICAL_SCHEDULER_LEGACY_REFS: 0")
