"""Migration contracts: native-default launch, source ownership, moved Godot paths."""
from pathlib import Path
import ast
from importlib.util import resolve_name

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PKG = ROOT / "piano_teacher"

MOVED = {
    "score_timeline.gd": "notation/shared/timeline.gd",
    "score_beat_camera.gd": None,
    "score_native_notation.gd": "notation/native/view.gd",
    "score_notation_geometry.gd": "notation/native/geometry.gd",
    "score_verovio_glyphs.gd": "notation/native/glyphs.gd",
    "score_timeline_preview.gd": "notation/diagnostics/timeline_preview.gd",
    "score_strip.gd": None,
    "score_quality.gd": None,
    "score_exact_spacing.gd": None,
    "score_motion_curve.gd": None,
}


def test_production_renderer_ignores_retired_selection_switches(tmp_path):
    # Source ownership gates below remain static; renderer selection is
    # verified by instantiating the production app under the retired flags.
    from test_native_production import test_native_production_readiness_and_failure_gate

    test_native_production_readiness_and_failure_gate(tmp_path, "retired-switches")


def test_moved_godot_resources_and_uid_companions_are_canonical():
    for old, new in MOVED.items():
        assert not (GODOT / old).exists(), old
        if new is not None:
            assert (GODOT / new).is_file(), new


def test_no_stale_godot_script_paths():
    deprecated = tuple(f"res://{name}" for name in MOVED)
    for root in (GODOT, ROOT / "tests"):
        for path in root.rglob("*"):
            if path.suffix not in {".gd", ".tscn", ".tres", ".py"} or not path.is_file():
                continue
            if "addons" in path.parts or ".godot" in path.parts:
                continue
            text = path.read_text(errors="replace")
            bad = [name for name in deprecated if name in text]
            assert not bad, (path.relative_to(ROOT), bad)


def test_source_importer_and_model_do_not_load_legacy_renderer():
    importer = (PKG / "importing/musicxml.py").read_text()
    model = (PKG / "notation/model.py").read_text()
    for contents in (importer, model):
        assert "rendering.legacy" not in contents
        assert "from .score import" not in contents
        assert "_create_verovio_toolkit" not in contents
    assert "from ..notation.musicxml import parse_barline" in importer
    assert "from .musicxml import" in model or "from .musicxml import" in (
        PKG / "notation/model.py").read_text()


def test_native_assets_are_not_importing_old_page_renderer():
    for path in (PKG / "notation/assets").glob("*.py"):
        source = path.read_text()
        assert "from ..rendering.legacy" not in source, path
        assert "from .score import" not in source, path
        ast.parse(source, filename=str(path))


def test_notation_infrastructure_has_canonical_owners():
    owners = {
        "notation/model.py": {"build_score_model"},
        "notation/lesson.py": {"build_lesson_score"},
        "importing/musicxml.py": {"load_musicxml"},
        "rendering/legacy/spacing.py": {
            "space_for_reading", "space_for_continuous_reading"},
        "notation/assets/glyphs.py": {"native_glyphs", "preparation_symbols"},
        "notation/assets/beams.py": {"beam_fragments"},
        "notation/assets/chords.py": {"chord_templates"},
        "notation/assets/notes.py": {"note_templates"},
        "notation/assets/slurs.py": {"slur_fragments"},
        "notation/assets/ties.py": {"tie_templates"},
        "notation/assets/tuplets.py": {"tuplet_fragments"},
    }
    for name, required in owners.items():
        path = PKG / name
        contents = path.read_text()
        assert "import *" not in contents
        assert "sys.modules" not in contents
        tree = ast.parse(contents, filename=str(path))
        definitions = {node.name for node in tree.body
                       if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
        assert required <= definitions, (name, required - definitions)


def test_retained_runtime_adapters_use_explicit_exports():
    for name in ("score.py", "score_geometry.py", "raster.py"):
        path = PKG / name
        contents = path.read_text()
        assert "import *" not in contents
        assert "sys.modules" not in contents
        ast.parse(contents, filename=str(path))


def test_retired_notation_facades_have_no_remaining_importers():
    retired = {
        "score_model", "lesson_score", "xml_import", "reading_spacing", "notation_symbols",
        "verovio_beam_fragments", "verovio_chord_templates",
        "verovio_note_templates", "verovio_slur_fragments",
        "verovio_tie_templates", "verovio_tuplet_fragments",
    }
    remaining = sorted(name for name in retired if (PKG / f"{name}.py").exists())
    assert not remaining, remaining
    obsolete = {f"piano_teacher.{name}" for name in retired}
    for root in (PKG, ROOT / "tests", ROOT / "scripts"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                imports = set()
                if isinstance(node, ast.Import):
                    imports = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if node.level:
                        package = ".".join(path.parent.relative_to(ROOT).parts)
                        module = resolve_name("." * node.level + module, package)
                    imports = {module, *(f"{module}.{alias.name}"
                                         for alias in node.names)}
                assert not imports & obsolete, (path, node.lineno, imports & obsolete)


@pytest.mark.parametrize("filename,source", [
    ("probe.py", "from . import score_model"),
    ("subpackage/probe.py", "from .. import score_model"),
])
def test_retirement_gate_rejects_relative_facade_imports(
        tmp_path, monkeypatch, filename, source):
    package = tmp_path / "piano_teacher"
    importer = package / filename
    importer.parent.mkdir(parents=True)
    importer.write_text(source)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "PKG", package)
    with pytest.raises(AssertionError, match="piano_teacher.score_model"):
        test_retired_notation_facades_have_no_remaining_importers()
