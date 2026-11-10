"""Quarantine: known-red tests become strict xfails with a precise reason.

``tests/quarantine.txt`` holds one entry per line: ``<test id or file> | <reason>``
(``#`` comments and blank lines allowed). A file entry (``tests/test_x.py``)
quarantines every test in the file; a test id (``tests/test_x.py::test_y``,
parametrize ids included) quarantines exactly that test. Entries are strict
xfails, so a quarantined test that starts passing fails the run until its line
is removed. An entry that matches nothing in a file that was collected, or that
names a file that does not exist, is a stale line and aborts the run. Id-level staleness is only judged on a
run that selects whole files (no ``::`` argument, ``-k`` or ``-m``). A reason
starting with ``flaky:`` marks a timing-dependent test that may pass or fail;
it is a non-strict xfail so it neither fails the gate when it passes nor hides
a hard regression elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

DEFAULT_FILE = Path(__file__).with_name("quarantine.txt")


def parse(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        target, sep, reason = line.partition(" | ")
        target, reason = target.strip(), reason.strip()
        if not sep or not target or not reason:
            raise pytest.UsageError(f"quarantine line {number}: expected '<test id or file> | <reason>', got {raw!r}")
        if target in entries:
            raise pytest.UsageError(f"quarantine line {number}: duplicate entry {target!r}")
        entries[target] = reason
    return entries


def _file_of(target: str) -> str:
    return target.split("::", 1)[0]


def apply(items, entries: dict[str, str], root: Path, whole_files: bool = True) -> list[str]:
    """Mark matching items xfail(strict); return stale-entry messages."""
    collected_files = {item.nodeid.split("::", 1)[0] for item in items}
    ids = {item.nodeid for item in items}
    stale = []
    for target in entries:
        if not (root / _file_of(target)).is_file():
            stale.append(f"{target}: file does not exist")
        elif whole_files and _file_of(target) in collected_files and "::" in target and target not in ids:
            stale.append(f"{target}: no such test in a collected file")
    for item in items:
        file = item.nodeid.split("::", 1)[0]
        reason = entries.get(item.nodeid) or entries.get(file)
        if reason is not None:
            item.add_marker(pytest.mark.xfail(strict=not reason.startswith("flaky:"), reason=f"quarantined: {reason}"))
    return stale


def pytest_collection_modifyitems(config, items):
    path = Path(os.environ.get("PIANO_QUARANTINE_FILE", DEFAULT_FILE))
    if not path.is_file():
        return
    whole = not (config.option.keyword or config.option.markexpr or any("::" in a for a in config.args))
    stale = apply(items, parse(path.read_text(encoding="utf-8")), Path(config.rootpath), whole)
    if stale:
        raise pytest.UsageError("stale quarantine entries in %s:\n  %s" % (path, "\n  ".join(stale)))
