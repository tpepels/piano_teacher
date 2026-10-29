"""Original SVG structure sits below asset builders and independent verifiers."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_source_svg_is_dependency_free_from_first_party_application_and_renderer_code():
    path = ROOT / "piano_teacher/source_svg.py"
    assert path.is_file(), "Missing neutral source SVG owner"
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("piano_teacher"), node.lineno
        elif isinstance(node, ast.Import):
            assert all(not a.name.startswith("piano_teacher") for a in node.names), node.lineno
    code = """
import importlib.abc
import sys
class SourceOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy', 'PIL', 'cairosvg', 'verovio'} or fullname.startswith(
            ('piano_teacher.notation', 'piano_teacher.rendering', 'piano_teacher.application',
             'piano_teacher.score', 'piano_teacher.server')):
            raise AssertionError('Neutral SVG structure imported ' + fullname)
sys.meta_path.insert(0, SourceOnly())
from piano_teacher.source_svg import parse_svg_geometry, isolate
from xml.etree import ElementTree as ET
xml = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><g class="system" id="s" transform="translate(10,5)"><g class="note" id="n" transform="translate(20,30)"><g class="notehead"><use x="10" transform="scale(2)"/></g></g></g></svg>'
assert parse_svg_geometry(xml).elements['n'] == (.25, .35, 's')
root = ET.fromstring(xml)
before = ET.tostring(root)
fragment = isolate(root, next(e for e in root.iter() if e.get('id') == 'n'))
assert 'translate(10,5)' in fragment and 'translate(20,30)' in fragment
assert ET.tostring(root) == before
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_generic_svg_implementation_has_one_neutral_owner_and_no_asset_facades():
    for name in ("svg.py", "svg_geometry.py"):
        assert not (ROOT / "piano_teacher/notation/assets" / name).exists(), name
    obsolete = {"piano_teacher.notation.assets.svg", "piano_teacher.notation.assets.svg_geometry"}
    for path in (ROOT / "piano_teacher").rglob("*.py"):
        package = ".".join(path.parent.relative_to(ROOT).parts)
        for node in ast.walk(ast.parse(path.read_text())):
            imports = set()
            if isinstance(node, ast.ImportFrom):
                base = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module or ""
                imports = {base, *(base + "." + a.name for a in node.names)}
            elif isinstance(node, ast.Import):
                imports = {a.name for a in node.names}
            assert not imports & obsolete, (path, node.lineno, imports & obsolete)


def test_connector_measurements_run_without_importing_production_asset_builders():
    code = """
import importlib.abc
import sys
class IndependentConnector(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('piano_teacher.notation.assets', 'piano_teacher.rendering',
                                'piano_teacher.application', 'piano_teacher.score')):
            raise AssertionError('Independent connector imported ' + fullname)
sys.meta_path.insert(0, IndependentConnector())
from pathlib import Path
from piano_teacher.notation.connector_pixels import verify_beam_pixels
folder = Path('tests/fixtures/connector_pixels/beams')
report = verify_beam_pixels((folder/'score.musicxml').read_text(), folder, hand='right')
assert report['coverage']['expected'] == report['coverage']['verified'] == 2
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_score_geometry_retains_public_geometry_and_legacy_layout_contracts():
    assert (ROOT / "piano_teacher/source_svg.py").is_file()
    from piano_teacher import score_geometry, source_svg
    from piano_teacher.rendering.legacy.geometry import layout_from_pages, locate_beat
    assert score_geometry.parse_svg_geometry is source_svg.parse_svg_geometry
    assert score_geometry.PageGeometry is source_svg.PageGeometry
    assert score_geometry.layout_from_pages is layout_from_pages
    assert score_geometry.locate_beat is locate_beat
