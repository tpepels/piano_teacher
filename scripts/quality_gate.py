"""Check tracked source for new lint findings against a fixed Git snapshot."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tarfile
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "38c22a51aec90782c3cba152e1c371bbd81dbd3d"
RUFF_RULES = "E4,E7,E9,F,B,C4,C90,I,UP,SIM,S102,S307,S506,S602,S608"
GD_DIAGNOSTIC = re.compile(r"^(.+?):(\d+): Error: (.+) \(([^()]+)\)$")
SUFFIXES = {".py", ".gd", ".sh", ".cjs", ".js", ".mjs"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    @property
    def key(self):
        return self.path, self.rule, self.message


def run(args, cwd, allowed=(0,)):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode not in allowed:
        raise RuntimeError(
            f"{args[0]} exited {result.returncode}:\n{result.stdout}{result.stderr}"
        )
    return result


def tracked_files():
    output = run(["git", "ls-files", "-z"], ROOT).stdout
    return sorted(
        path
        for path in output.split("\0")
        if path and Path(path).suffix in SUFFIXES and (ROOT / path).is_file()
    )


def ruff(root, path):
    result = run(
        [
            "ruff", "check", "--isolated", "--no-cache", "--ignore-noqa",
            "--target-version", "py310", "--select", RUFF_RULES,
            "--output-format", "json", path,
        ],
        root,
        (0, 1),
    )
    return [
        Finding(path, item["location"]["row"], item["code"] or "syntax", item["message"])
        for item in json.loads(result.stdout)
    ]


def shellcheck(root, path):
    result = run(["shellcheck", "--format=json", path], root, (0, 1))
    return [
        Finding(path, item["line"], f"SC{item['code']}", item["message"])
        for item in json.loads(result.stdout)
    ]


def gdscript(root, path):
    result = run(["gdlint", path], root, (0, 1))
    output = result.stdout + result.stderr
    findings = []
    for line in output.splitlines():
        match = GD_DIAGNOSTIC.match(line)
        if match:
            _, number, message, rule = match.groups()
            findings.append(Finding(path, int(number), f"gd/{rule}", message))
    if result.returncode and not findings:
        # The third-party grammar may lag Godot. Record recognized parser
        # diagnostics, but never treat an unexpected tool crash as clean.
        if "Unexpected token" not in output and "Unexpected input" not in output:
            raise RuntimeError(f"gdlint failed for {path}:\n{output}")
        findings.append(Finding(path, 1, "gd/parser", output.strip()))
    return findings


def inspect(root, path):
    suffix = Path(path).suffix
    if suffix == ".py":
        return ruff(root, path)
    if suffix == ".gd":
        return gdscript(root, path)
    if suffix == ".sh":
        return shellcheck(root, path)
    return []


def regressions(previous, current):
    """Match diagnostic multiplicities; line-number shifts do not add debt."""
    allowance = Counter(item.key for item in previous)
    excess = []
    for item in current:
        if allowance[item.key]:
            allowance[item.key] -= 1
        else:
            excess.append(item)
    return excess


def inspect_pair(baseline, path):
    current = inspect(ROOT, path)
    old = baseline / path
    if not old.is_file():
        return [], current
    if old.read_bytes() == (ROOT / path).read_bytes():
        return current, current
    return inspect(baseline, path), current


def check_syntax(paths):
    """Syntax and workflow checks are strict, even for existing files."""
    for path in paths:
        suffix = Path(path).suffix
        if suffix == ".py":
            compile((ROOT / path).read_bytes(), path, "exec")
        elif suffix == ".sh":
            run(["bash", "-n", path], ROOT)
        elif suffix in {".js", ".cjs", ".mjs"}:
            run(["node", "--check", path], ROOT)
    run(["actionlint", "-color=false"], ROOT)


def emit(item):
    message = item.message.replace("\r", "").replace("\n", " ")
    if len(message) > 1000:
        message = message[:1000] + "..."
    print(f"{item.path}:{item.line}: {item.rule}: {message}")


def collect(paths):
    with tempfile.TemporaryDirectory(prefix="piano-quality-") as folder:
        baseline = Path(folder) / "baseline"
        baseline.mkdir()
        archive = Path(folder) / "baseline.tar"
        run(["git", "archive", "-o", str(archive), BASELINE], ROOT)
        with tarfile.open(archive) as tar:
            tar.extractall(baseline, filter="data")
        with ThreadPoolExecutor(max_workers=8) as executor:
            pairs = list(executor.map(lambda path: inspect_pair(baseline, path), paths))
    previous = [item for old, _ in pairs for item in old]
    current = [item for _, new in pairs for item in new]
    return previous, current


def check(strict):
    paths = tracked_files()
    check_syntax(paths)
    previous, current = collect(paths)
    new = regressions(previous, current)
    failures = list(current if strict else new)
    for item in current:
        if item.rule in {"syntax", "invalid-syntax"} and item not in failures:
            failures.append(item)
        if item.rule == "gd/parser":
            print("GDScript parser diagnostic (native Godot checks remain required):")
            emit(item)
    for item in failures:
        emit(item)
    counts = Counter(item.rule for item in current)
    print("Current lint findings by rule:")
    for rule, count in sorted(counts.items()):
        print(f"  {rule}: {count}")
    print(
        f"Checked {len(paths)} tracked source files; {len(current)} findings, "
        f"{len(new)} new, {len(failures)} blocking."
    )
    return int(bool(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Fail on existing debt too")
    args = parser.parse_args()
    return check(args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
