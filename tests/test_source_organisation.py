"""Migration contracts: native-default launch, source ownership, moved Godot paths."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PKG = ROOT / "piano_teacher"

MOVED = {
    "score_timeline.gd": "notation/shared/timeline.gd",
    "score_beat_camera.gd": "notation/shared/beat_camera.gd",
    "score_native_notation.gd": "notation/native/view.gd",
    "score_notation_geometry.gd": "notation/native/geometry.gd",
    "score_verovio_glyphs.gd": "notation/native/glyphs.gd",
    "score_timeline_preview.gd": "notation/diagnostics/timeline_preview.gd",
    "score_strip.gd": "notation/legacy/strip.gd",
    "score_quality.gd": "notation/legacy/quality.gd",
    "score_exact_spacing.gd": "notation/legacy/exact_spacing.gd",
    "score_motion_curve.gd": "notation/legacy/motion_curve.gd",
}


def test_native_renderer_is_default_and_old_renderer_is_explicit():
    main = (GODOT / "main.gd").read_text()
    assert 'PIANO_TEACHER_RENDERER").to_lower() != "legacy"' in main
    assert '"--legacy-notation"' in main
    assert 'PIANO_TEACHER_NATIVE_NOTATION").to_lower() not in' in main
    assert 'score_view.visible = true' in main
    assert 'timeline_preview.visible = false' in main


def test_moved_godot_resources_and_uid_companions_are_canonical():
    for old, new in MOVED.items():
        assert not (GODOT / old).exists(), old
        assert (GODOT / new).is_file(), new
    for resource in ("strip", "quality"):
        assert (GODOT / f"notation/legacy/{resource}.gd.uid").is_file()


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


def test_old_public_imports_are_thin_explicit_facades():
    for name in ("score.py", "score_model.py", "lesson_score.py",
                 "xml_import.py", "reading_spacing.py", "raster.py"):
        path = PKG / name
        contents = path.read_text()
        assert "import *" not in contents
        assert "sys.modules" not in contents
        ast.parse(contents, filename=str(path))
