"""Four-way full-CI partition stays complete, disjoint and collection-safe."""
from types import SimpleNamespace

import pytest

from scripts.ci_full_shards import (
    SHARD_COUNT, allocation, source_weight, module_of, file_plan,
    pytest_ignore_collect, pytest_collection_modifyitems,
)


class Item:
    def __init__(self, root, module):
        self.config = SimpleNamespace(rootpath=root)
        self.path = root / module


def test_four_parts_cover_every_discovered_test_file_once(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    for number in range(1, 61):
        (tests / f"test_{number:03}.py").write_text(
            "\n".join(f"def test_case_{i}(): assert True" for i in range(1, number % 7 + 2)))
    assigned, weights = file_plan(str(tmp_path))
    assert len(assigned) == len(weights) == 60
    shards = [{path for path, shard in assigned.items() if shard == i}
              for i in range(1, SHARD_COUNT + 1)]
    assert set.union(*shards) == set(weights)
    assert sum(map(len, shards)) == len(weights)
    assert all(shards)
    loads = [sum(weights[path] for path in subset) for subset in shards]
    assert max(loads) <= 2 * min(loads)


def test_invalid_file_is_assigned_without_importing_or_parsing(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    broken = tests / "test_broken.py"
    broken.write_text("def test_bad(: this is not valid python at all\n")
    weights = file_plan(str(tmp_path))[1]
    assert "tests/test_broken.py" in weights
    assert source_weight(broken) > 0


def test_collection_hook_skips_other_shards_before_import(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(8):
        (tests / f"test_case_{i}.py").write_text("def test_x(): assert True\n")
    assigned, _ = file_plan(str(tmp_path))

    class Config:
        rootpath = tmp_path
        def getoption(self, name):
            return {"full_ci_shard": 1}[name]

    for filename, shard in assigned.items():
        path = tmp_path / filename
        assert pytest_ignore_collect(path, Config()) is (shard != 1)


def test_post_collection_selection_preserves_module_assignments(tmp_path, capsys):
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(8):
        (tests / f"test_case_{i}.py").write_text("def test_x(): assert True\n")
    items = [Item(tmp_path, f"tests/test_case_{i}.py") for i in range(8)
             for _ in range(3)]
    original = list(items)
    dropped = []

    class Config:
        rootpath = tmp_path
        def getoption(self, key):
            return {"full_ci_shard": 2}[key]
        hook = SimpleNamespace(pytest_deselected=lambda items: dropped.extend(items))

    pytest_collection_modifyitems(items, Config())
    assert len(items) + len(dropped) == len(original)
    assert set(items).isdisjoint(dropped)
    assert set(items).union(dropped) == set(original)
    assert len({module_of(item) for item in items}) == 2
    assert "CI_FULL_SHARD_ACTIVE: 2/4" in capsys.readouterr().out


def test_allocation_rejects_invalid_weights():
    with pytest.raises(ValueError, match="nonpositive"):
        allocation({"tests/test_bad.py": 0})
    with pytest.raises(ValueError, match="positive"):
        allocation({"tests/test_good.py": 1}, 0)
