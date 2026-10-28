"""Feature families own their measurements without callbacks into the coordinator."""
from pathlib import Path
import subprocess
import sys

import pytest

from test_verification_pixel_ownership import notation_dependencies

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ("feature_contract", "feature_source", "glyph_evidence", "stem_pixels",
          "adornment_pixels", "structure_pixels", "ledger_pixels")


@pytest.mark.parametrize("owner", OWNERS)
def test_feature_family_dependencies_do_not_reach_the_coordinator_or_production(owner):
    graph = notation_dependencies()
    name = "piano_teacher.notation." + owner
    assert name in graph, "Missing independent feature owner: " + name
    pending, visited = [name], set()
    while pending:
        current = pending.pop()
        assert not current.startswith(("piano_teacher.notation.feature_pixels",
                                       "piano_teacher.notation.assets",
                                       "piano_teacher.notation.lesson",
                                       "piano_teacher.notation.model",
                                       "piano_teacher.application", "piano_teacher.rendering",
                                       "piano_teacher.score", "piano_teacher.server")), current
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, ()))


@pytest.mark.parametrize("owner", ["structure_pixels", "ledger_pixels"])
def test_feature_family_runs_on_retained_pngs_with_coordinator_import_blocked(owner):
    assert (ROOT / "piano_teacher/notation" / (owner + ".py")).exists(), owner
    code = """
import importlib.abc
import sys
class IndependentFeatures(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('piano_teacher.notation.feature_pixels',
                                'piano_teacher.notation.assets', 'piano_teacher.rendering',
                                'piano_teacher.application', 'piano_teacher.score')):
            raise AssertionError('Feature family imported ' + fullname)
sys.meta_path.insert(0, IndependentFeatures())
from pathlib import Path
if %r == 'structure_pixels':
    from piano_teacher.notation.structure_pixels import verify_structure_pixels
    from piano_teacher.notation.visual_coverage import visual_elements
    folder = Path('tests/fixtures/native_structure')
    xml = (folder/'score.musicxml').read_text()
    elements = visual_elements(None, xml, {}, {}, hand='both')
    result = verify_structure_pixels(xml, folder, elements, hand='both')
    assert result and all(row['status'] == 'verified' for row in result), result
else:
    from piano_teacher.notation.ledger_pixels import verify_ledger_pixels
    folder = Path('tests/fixtures/native_ledger_chord')
    result = verify_ledger_pixels((folder/'score.musicxml').read_text(), folder, hand='right')
    assert result['complete'], result
    assert result['coverage']['verified'] == result['coverage']['expected'] == 4
""" % owner
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_note_feature_claims_are_local_to_each_call_and_do_not_escape_the_report():
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder = ROOT / "tests/fixtures/feature_pixels/chords"
    xml = (folder/"source.musicxml").read_text()
    before = verify_note_feature_pixels(xml, folder, hand="right")
    other = ROOT / "tests/fixtures/feature_pixels/rhythms"
    verify_note_feature_pixels((other/"source.musicxml").read_text(), other, hand="left")
    after = verify_note_feature_pixels(xml, folder, hand="right")
    assert before == after
    assert before is not after and before["measured"] is not after["measured"]
    assert before["by_construct"]["stem"]["verified"] == 24
    for row in after["measured"]:
        for feature in row["features"].values():
            assert "_support" not in feature and "_group_id" not in feature


def test_public_structure_and_ledger_entry_points_are_their_owners_functions():
    assert all((ROOT / "piano_teacher/notation" / (name + ".py")).exists()
               for name in ("structure_pixels", "ledger_pixels"))
    from piano_teacher.notation import feature_pixels, structure_pixels, ledger_pixels
    assert feature_pixels.verify_structure_pixels is structure_pixels.verify_structure_pixels
    assert feature_pixels.verify_ledger_pixels is ledger_pixels.verify_ledger_pixels
