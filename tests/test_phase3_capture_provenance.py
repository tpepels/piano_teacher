"""Cached pixels must be invalidated by all rendering inputs and engine changes."""
import json

import pytest

from scripts import check_native_verovio_overlay as capture


def test_theme_is_part_of_renderer_dependency_hash(tmp_path):
    (tmp_path/"godot/notation/native").mkdir(parents=True)
    (tmp_path/"tests/godot").mkdir(parents=True)
    (tmp_path/"godot/notation/native/view.gd").write_text("extends Control\n")
    (tmp_path/"tests/godot/native_verovio_overlay.gd").write_text("extends SceneTree\n")
    theme=tmp_path/"godot/practice_theme.gd"
    theme.write_text('const SCORE_INK = Color("#EAF4ED")\n')
    before=capture.capture_dependency_hash(tmp_path)
    theme.write_text('const SCORE_INK = Color("#10251F")\n')
    assert before!=capture.capture_dependency_hash(tmp_path)


def test_capture_reuse_checks_recorded_godot_version(tmp_path):
    manifest={"renderer_dependencies_sha256":"deps","godot":"old-engine","screenshots":[]}
    (tmp_path/"capture-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(AssertionError,match="Godot"):
        capture.validate_capture_manifest(tmp_path,dependency_hash="deps",godot_version="current-engine")


def test_capture_reuse_rejects_incomplete_dependency_manifest(tmp_path):
    (tmp_path/"capture-manifest.json").write_text(json.dumps({"godot":"current","screenshots":[]}))
    with pytest.raises(AssertionError,match="dependencies"):
        capture.validate_capture_manifest(tmp_path,dependency_hash="deps",godot_version="current")


def test_reference_font_does_not_depend_on_mutable_toolkit_resource_defaults(monkeypatch):
    import verovio
    from piano_teacher.notation.reference_font import reference_glyphs
    def unavailable_toolkit():
        raise AssertionError("A mutable engraving toolkit must not choose oracle resources")
    reference_glyphs.cache_clear()
    monkeypatch.setattr(verovio,"toolkit",unavailable_toolkit)
    glyphs=reference_glyphs()
    assert glyphs["rest_quarter"]["font"]=="Leipzig"
    assert glyphs["rest_quarter"]["code"]=="E4E5"
    reference_glyphs.cache_clear()
