"""Visual source obligations and acceptance stay independent of pixel producers."""
from pathlib import Path
import subprocess
import sys

import pytest

from test_verification_pixel_ownership import notation_dependencies

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ("visual_contract", "visual_inventory", "visual_binding", "visual_presence",
          "visual_notes", "visual_rests", "visual_curves", "visual_groups",
          "visual_ledgers", "visual_tuplets")


@pytest.mark.parametrize("owner", OWNERS)
def test_visual_acceptance_dependencies_do_not_reach_the_coordinator_or_measurement(owner):
    graph = notation_dependencies()
    name = "piano_teacher.notation." + owner
    assert name in graph, "Missing visual ledger owner: " + name
    prohibited = ("piano_teacher.notation.visual_coverage", "piano_teacher.notation.assets",
                  "piano_teacher.notation.feature_pixels", "piano_teacher.notation.phase3_pixels",
                  "piano_teacher.notation.connector_pixels", "piano_teacher.notation.symbol_pixel_proof",
                  "piano_teacher.notation.extra_symbol_pixels", "piano_teacher.notation.head_registration",
                  "piano_teacher.notation.raster_matching", "piano_teacher.notation.pixel_proof",
                  "piano_teacher.notation.feature_contract", "piano_teacher.application",
                  "piano_teacher.rendering", "piano_teacher.score", "piano_teacher.server",
                  "piano_teacher.notation.model", "piano_teacher.notation.lesson")
    pending, visited = [name], set()
    while pending:
        current = pending.pop()
        assert not current.startswith(prohibited), current
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, ()))


def test_source_inventory_is_callable_without_any_ledger_coordinator_or_image_dependencies():
    assert (ROOT / "piano_teacher/notation/visual_inventory.py").is_file()
    code = """
import importlib.abc
import sys
class InventoryOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PIL', 'numpy', 'cairosvg', 'verovio'} or fullname.startswith(
            ('piano_teacher.notation.visual_coverage', 'piano_teacher.notation.assets',
             'piano_teacher.notation.feature_pixels', 'piano_teacher.notation.phase3_pixels')):
            raise AssertionError('Source inventory imported ' + fullname)
sys.meta_path.insert(0, InventoryOnly())
from pathlib import Path
from piano_teacher.notation.visual_inventory import source_inventory
xml = Path('tests/fixtures/feature_pixels/rhythms/source.musicxml').read_text()
rows = source_inventory(xml, 'right')
assert rows and any(row['construct'] == 'flag' for row in rows)
assert all('status' not in row for row in rows)
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_ledger_and_every_acceptance_owner_load_with_only_stdlib_dependencies():
    assert all((ROOT / "piano_teacher/notation" / (name + ".py")).is_file() for name in OWNERS)
    code = """
import importlib.abc
import sys
class LedgerOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PIL', 'numpy', 'cairosvg', 'verovio'} or fullname.startswith(
            ('piano_teacher.notation.assets', 'piano_teacher.notation.feature_pixels',
             'piano_teacher.notation.phase3_pixels', 'piano_teacher.notation.model',
             'piano_teacher.notation.lesson', 'piano_teacher.application')):
            raise AssertionError('Visual acceptance imported ' + fullname)
sys.meta_path.insert(0, LedgerOnly())
import importlib
for name in %r:
    importlib.import_module('piano_teacher.notation.' + name)
from pathlib import Path
from piano_teacher.notation.visual_coverage import visual_elements, source_inventory, coverage_counts
xml = Path('tests/fixtures/feature_pixels/rhythms/source.musicxml').read_text()
rows = visual_elements(xml, xml, {'passed': True}, {'passed': True}, hand='right')
assert coverage_counts(rows)['verified'] == 0
assert len(rows) == len(source_inventory(xml, 'right'))
assert all(row['status'] != 'verified' for row in rows)
""" % (OWNERS,)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_inventory_entry_point_is_the_independent_owner_function():
    assert (ROOT / "piano_teacher/notation/visual_inventory.py").is_file()
    from piano_teacher.notation import visual_coverage, visual_inventory
    assert visual_coverage.source_inventory is visual_inventory.source_inventory


def test_visual_ledger_dependency_graph_is_acyclic_including_lazy_imports():
    from graphlib import TopologicalSorter
    graph = notation_dependencies()
    pending = ["piano_teacher.notation.visual_coverage"]
    reachable = {}
    while pending:
        current = pending.pop()
        if current not in reachable:
            reachable[current] = graph.get(current, set())
            pending.extend(reachable[current])
    tuple(TopologicalSorter(reachable).static_order())


def test_fractional_correspondence_consumes_each_occurrence_once_per_call():
    from copy import deepcopy
    from fractions import Fraction
    from piano_teacher.notation.visual_binding import match_generated_events

    note = dict(kind="note", beat=1/3, _clock=Fraction(1, 3), staff="right",
                spelling=["C", 0, 4], timing_supported=True, xml_id=None, voice="1")
    expected = {"first": dict(note), "second": dict(note)}
    generated = {"g": dict(note, beat=0., _clock=Fraction(0))}
    before = deepcopy((expected, generated))
    for _ in range(2):
        matched, used = match_generated_events(expected, generated, Fraction(1, 3))
        assert set(matched) == {"first"} and used == {"g"}
        assert matched["first"] is generated["g"]
    assert (expected, generated) == before
