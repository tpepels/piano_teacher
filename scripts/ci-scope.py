#!/usr/bin/env python3
"""Inventory current pytest modules and enforce an explicitly reviewed scope.

This is a coverage gate, NOT a heuristic test deleter. An agent must trace each
remaining module to production code and record a current ownership contract.
Every new, renamed, or removed module invalidates the registry until reviewed.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
REGISTRY = TESTS / "ci-scope.json"
PATTERNS = ("test_*.py", "*_test.py")
FLAGS = re.compile(
    r"\b(legacy|deprecated|removed|old[_ -]?server|compatibility|"
    r"localhost|\bhttp\b|\budp\b|\bqt\b|old[_ -]?transport)\b",
    re.IGNORECASE,
)
ALLOWED_OWNERS = (
    "piano_teacher/", "godot/", "scripts/", "docs/",
    ".github/workflows/",
)
ALLOWED_TOP_LEVEL_OWNERS = {"pyproject.toml", "ROADMAP.md", "README.md"}


def modules() -> list[Path]:
    found = {p for pattern in PATTERNS for p in TESTS.rglob(pattern) if p.is_file()}
    return sorted(found, key=lambda path: path.relative_to(ROOT).as_posix())


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_definitions(path: Path) -> tuple[int, str | None]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeError) as exc:
        return 0, str(exc)
    # Pytest test cases, including class-based and async test methods.
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    ), None


def inventory() -> int:
    files = modules()
    definitions = 0
    suspicious = 0
    problems = 0
    print("CI_SCOPE_INVENTORY: %d test modules" % len(files))
    print("MODULE\tTEST_DEFINITIONS\tREVIEW_FLAGS")
    for path in files:
        count, error = test_definitions(path)
        definitions += count
        source = path.read_text(encoding="utf-8", errors="replace")
        flags = sorted(set(m.group(0).lower() for m in FLAGS.finditer(source)))
        if flags:
            suspicious += 1
        if error:
            problems += 1
        label = ",".join(flags) if flags else "-"
        print(f"{rel(path)}\t{count}\t{label}")
        if error:
            print(f"  PARSE_ERROR: {error}")
    print(f"CI_SCOPE_INVENTORY_TOTAL: {definitions} test definitions; "
          f"{suspicious} flagged modules (flags require human review); "
          f"{problems} parse errors")
    return 1 if problems else 0


def verify(require_no_quarantine: bool = False) -> int:
    problems = []
    paths = {rel(path): path for path in modules()}
    if not REGISTRY.is_file():
        print(f"CI_SCOPE_INCOMPLETE: missing {rel(REGISTRY)}", file=sys.stderr)
        print("Run python scripts/ci-scope.py --inventory and review every "
              "current test before creating a registry.", file=sys.stderr)
        return 1
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        print(f"CI_SCOPE_INCOMPLETE: invalid registry: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("modules"), dict):
        print("CI_SCOPE_INCOMPLETE: expected schema=1 and a modules object", file=sys.stderr)
        return 1
    entries = data["modules"]
    missing = sorted(paths.keys() - entries.keys())
    stale = sorted(entries.keys() - paths.keys())
    if missing:
        problems.append(f"unreviewed test modules ({len(missing)}): " + ", ".join(missing))
    if stale:
        problems.append(f"registry lists deleted/renamed modules ({len(stale)}): " + ", ".join(stale))
    for name in sorted(paths.keys() & entries.keys()):
        row = entries[name]
        if not isinstance(row, dict):
            problems.append(f"{name}: expected owner/contract object")
            continue
        owner, contract = row.get("owner"), row.get("contract")
        if not isinstance(owner, str) or not (
            owner.startswith(ALLOWED_OWNERS) or owner in ALLOWED_TOP_LEVEL_OWNERS
        ) or "/archive/" in owner or owner.startswith("tests/"):
            problems.append(f"{name}: owner must name a current product/tool source")
        elif not (ROOT / owner).is_file():
            problems.append(f"{name}: owner does not exist: {owner}")
        if not isinstance(contract, str) or len(contract.strip()) < 12:
            problems.append(f"{name}: missing concrete current behavior contract")
        count, error = test_definitions(paths[name])
        if error is not None:
            problems.append(f"{name}: cannot parse test module: {error}")
        elif count == 0:
            problems.append(f"{name}: contains no test definitions")
    if require_no_quarantine:
        quarantine = TESTS / "quarantine.txt"
        if quarantine.exists():
            active = [line.strip() for line in quarantine.read_text().splitlines()
                      if line.strip() and not line.lstrip().startswith("#")]
            if active:
                problems.append("remaining quarantined tests (" + str(len(active)) +
                                "): " + ", ".join(active))
    if problems:
        for problem in problems:
            print("CI_SCOPE_INCOMPLETE: " + problem, file=sys.stderr)
        return 1
    print(f"CI_SCOPE_COMPLETE: {len(paths)} current test modules reviewed, "
          f"no missing or obsolete registry entries; "
          f"quarantine={'empty' if require_no_quarantine else 'checked separately'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--inventory", action="store_true",
                        help="list all test modules, definitions, and possible legacy clues")
    action.add_argument("--check", action="store_true",
                        help="require complete registry of current test modules")
    action.add_argument("--check-unquarantined", action="store_true",
                        help="require the registry and zero quarantined tests")
    args = parser.parse_args()
    return inventory() if args.inventory else verify(args.check_unquarantined)


if __name__ == "__main__":
    raise SystemExit(main())
