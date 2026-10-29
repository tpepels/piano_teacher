"""Controlled rest evidence owns intervention, contour claims and placement."""
from pathlib import Path
import subprocess
import sys

import pytest
from test_verification_pixel_ownership import notation_dependencies

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ("rest_contours", "rest_placement_pixels", "rest_intervention")


@pytest.mark.parametrize("owner", OWNERS)
def test_rest_owners_do_not_call_back_into_phase3_or_other_detector_coordinators(owner):
    graph = notation_dependencies()
    name = "piano_teacher.notation." + owner
    assert name in graph, "Missing independent rest owner: " + name
    pending, visited = [name], set()
    while pending:
        current = pending.pop()
        assert not current.startswith(("piano_teacher.notation.phase3_pixels",
            "piano_teacher.notation.feature_pixels", "piano_teacher.notation.connector_pixels",
            "piano_teacher.notation.symbol_pixel_proof", "piano_teacher.notation.extra_symbol_pixels",
            "piano_teacher.notation.head_registration", "piano_teacher.notation.assets",
            "piano_teacher.rendering", "piano_teacher.application", "piano_teacher.score")), current
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, ()))


def test_rest_intervention_runs_without_loading_pitch_scroll_or_asset_builders():
    assert (ROOT / "piano_teacher/notation/rest_intervention.py").is_file()
    code = """
import importlib.abc
import sys
class RestOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('piano_teacher.notation.phase3_pixels',
             'piano_teacher.notation.head_registration', 'piano_teacher.notation.assets',
             'piano_teacher.notation.feature_pixels', 'piano_teacher.rendering',
             'piano_teacher.application', 'piano_teacher.score')):
            raise AssertionError('Rest intervention imported ' + fullname)
sys.meta_path.insert(0, RestOnly())
from pathlib import Path
from piano_teacher.notation.rest_intervention import verify_all_rest_pixels
folder = Path('tests/fixtures/rest_orientation_native')
xml = (folder/'score.musicxml').read_text()
first = verify_all_rest_pixels(xml, folder)
second = verify_all_rest_pixels(xml, folder)
assert first == second and first is not second
assert first['complete'] and first['image_rest_glyphs_verified'] == 1, first
assert first['measured'][0]['observed_rest'] == 'whole'
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_phase3_public_rest_detector_is_the_independent_intervention_entry_point():
    assert (ROOT / "piano_teacher/notation/rest_intervention.py").is_file()
    from piano_teacher.notation import phase3_pixels, rest_intervention
    assert phase3_pixels.verify_all_rest_pixels is rest_intervention.verify_all_rest_pixels


def test_authentic_rest_mask_reuse_stays_bounded_and_keeps_raster_shapes():
    assert (ROOT / "piano_teacher/notation/rest_contours.py").is_file()
    from piano_teacher.notation.rest_contours import render_rest_outline
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1" preserveAspectRatio="none"><rect width="1" height="1" fill="white"/></svg>'
    render_rest_outline.cache_clear()
    for width in range(1, 130):
        mask = render_rest_outline(svg, width, 1)
        assert mask.shape == (1, width) and mask.all()
        assert render_rest_outline.cache_info().currsize <= 128
    previous_hits = render_rest_outline.cache_info().hits
    render_rest_outline(svg, 129, 1)
    assert render_rest_outline.cache_info().hits == previous_hits + 1
