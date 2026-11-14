"""Deterministic four-part release suite, partitioned BEFORE pytest imports.

The plan is based on existing Python test module paths and cheap source
estimates. pytest_ignore_collect excludes modules belonging to other shards
before importing them; a syntax/import error in one module cannot prevent
collection in the other three. Entire modules stay together so module-scoped
fixtures/parametrizations never split across parts. Four parts cover all
standard pytest test_*.py and *_test.py modules under tests/ exactly once.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import pytest

SHARD_COUNT = 4
TEST_FILES = ("test_*.py", "*_test.py")
TEST_FUNCTION = re.compile(r"^\s*(?:async\s+)?def\s+test_[a-zA-Z_0-9]+\s*\(", re.M)


def allocation(module_weights: dict[str, int], count: int = SHARD_COUNT) -> dict[str, int]:
    """Deterministic longest-first greedy bin packing, 1-based shard numbers."""
    if count < 1:
        raise ValueError("count must be positive")
    loads = [0] * count
    result = {}
    for name, weight in sorted(module_weights.items(), key=lambda row: (-row[1], row[0])):
        if weight <= 0:
            raise ValueError(f"nonpositive test weight: {name}")
        index = min(range(count), key=lambda idx: (loads[idx], idx))
        result[name] = index + 1
        loads[index] += weight
    return result


def source_weight(path: Path) -> int:
    """Cheap balanced estimate without importing, parsing, or executing tests.

    Large/polymorphic suites and slow/corpus tests weigh more. A malformed
    test module is still assigned exactly once; only that shard discovers
    its actual Python parse/collection failure.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    tests = len(TEST_FUNCTION.findall(source))
    lines = source.count("\n") + 1
    parametrizations = source.count(".mark.parametrize(")
    slow = "mark.slow" in source or "pytestmark =" in source and "slow" in source
    return max(1, tests + lines // 75 + parametrizations * 2 + (12 if slow else 0))


@lru_cache(maxsize=8)
def file_plan(root: str) -> tuple[dict[str, int], dict[str, int]]:
    root_path = Path(root).resolve()
    directory = root_path / "tests"
    weights = {}
    for pattern in TEST_FILES:
        for path in directory.rglob(pattern):
            if path.is_file():
                weights[path.relative_to(root_path).as_posix()] = source_weight(path)
    return allocation(weights), weights


def module_of(item) -> str:
    return Path(str(item.path)).resolve().relative_to(
        Path(str(item.config.rootpath)).resolve()).as_posix()


def pytest_addoption(parser):
    group = parser.getgroup("four-part full CI")
    group.addoption("--full-ci-shard", action="store", type=int,
                    choices=tuple(range(1, SHARD_COUNT + 1)), default=None,
                    help="run only this full-suite shard (1, 2, 3 or 4)")


def pytest_ignore_collect(collection_path: Path, config):
    shard = config.getoption("full_ci_shard")
    if shard is None or not collection_path.is_file():
        return None
    relative = collection_path.resolve().relative_to(Path(str(config.rootpath)).resolve()).as_posix()
    assigned, _ = file_plan(str(config.rootpath))
    if relative in assigned:
        return assigned[relative] != shard
    return None


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items, config):
    shard = config.getoption("full_ci_shard")
    if shard is None:
        return
    assigned, _ = file_plan(str(config.rootpath))
    # Fallback for custom collectors that bypass the pre-import ignore hook.
    # These must not make a shard accidentally run cases owned by another.
    kept = [item for item in items if assigned.get(module_of(item)) == shard]
    deselected = [item for item in items if assigned.get(module_of(item)) != shard]
    if deselected:
        items[:] = kept
        config.hook.pytest_deselected(items=deselected)
    if not items:
        raise pytest.UsageError(f"full CI shard {shard} collected no tests")
    print(f"CI_FULL_SHARD_ACTIVE: {shard}/{SHARD_COUNT} "
          f"({len(items)} cases, {len(set(map(module_of, items)))} modules)", flush=True)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assigned, weights = file_plan(str(root))
    print(f"CI_FULL_PLAN: {len(assigned)} test modules across {SHARD_COUNT} disjoint shards")
    for number in range(1, SHARD_COUNT + 1):
        modules = sorted(name for name, shard in assigned.items() if shard == number)
        print(f"CI_FULL_SHARD_{number}: {len(modules)} modules, "
              f"{sum(weights[name] for name in modules)} estimated weight")
        for module in modules:
            print(f"  {module}")
    print("CI_FULL_PLAN_NOTE: weights estimate relative work; actual case counts "
          "are printed when each shard runs")


if __name__ == "__main__":
    main()
