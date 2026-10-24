"""Cached pixels must be invalidated by all rendering inputs and engine changes."""
import json

import pytest

from scripts import check_native_verovio_overlay as capture


def test_fresh_capture_never_certifies_leftover_pixels_or_reference_pages(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import subprocess
    folder=tmp_path/'capture'
    folder.mkdir()
    for name in ('native-9.99999.png','rest-without-0-9.99999.png',
                 'verovio-9.svg','capture-manifest.json','native-overlay-report.json'):
        (folder/name).write_text('previous run')
    def actual_process(*args,**kwargs):
        assert not (folder/'native-9.99999.png').exists()
        assert not (folder/'verovio-9.svg').exists()
        (folder/'native-0.00000.png').write_bytes(b'current frame')
        (folder/'native-overlay-report.json').write_text('{"frames":[]}')
        return subprocess.CompletedProcess(args[0],0,'NATIVE_VEROVIO_OVERLAY_FAILURES:0','')
    monkeypatch.setattr(capture.subprocess,'run',actual_process)
    monkeypatch.setattr(capture.subprocess,'check_output',lambda *_,**__:'current-engine')
    def end_after_capture(*_):raise RuntimeError('capture checked')
    monkeypatch.setattr(capture,'readability_errors',end_after_capture)
    payload=dict(model={},xml='<score-partwise/>',sample_beats=[0.],assets={})
    with pytest.raises(RuntimeError,match='capture checked'):
        capture.run(folder,'godot',prepared=(payload,SimpleNamespace(pages=[])))
    manifest=json.loads((folder/'capture-manifest.json').read_text())
    assert [row['file'] for row in manifest['screenshots']]==['native-0.00000.png']


def test_capture_reuse_rejects_unrecorded_native_images(tmp_path):
    import hashlib
    (tmp_path/'native-9.99999.png').write_bytes(b'not in this capture')
    (tmp_path/'native-0.00000.png').write_bytes(b'current frame')
    manifest=dict(renderer_dependencies_sha256='deps',godot='current',screenshots=[
        dict(file='native-0.00000.png',sha256=hashlib.sha256(b'current frame').hexdigest())])
    (tmp_path/'capture-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(AssertionError,match='inventory'):
        capture.validate_capture_manifest(tmp_path,dependency_hash='deps',godot_version='current')


def test_actual_capture_cannot_record_a_changed_renderer_as_its_producer(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import subprocess
    dependency = tmp_path/"view.gd"
    dependency.write_text("before capture")
    monkeypatch.setattr(capture,"capture_dependency_hash",lambda: dependency.read_text())
    def actual_process(*args, **kwargs):
        dependency.write_text("changed during capture")
        return subprocess.CompletedProcess(args[0],0,"NATIVE_VEROVIO_OVERLAY_FAILURES:0","")
    monkeypatch.setattr(capture.subprocess,"run",actual_process)
    payload=dict(model={},xml="<score-partwise/>",sample_beats=[0.],assets={})
    folder=tmp_path/"capture"
    with pytest.raises(AssertionError,match="dependencies changed during"):
        capture.run(folder,"godot",prepared=(payload,SimpleNamespace(pages=[])))
    assert not (folder/"capture-manifest.json").exists()


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


@pytest.mark.parametrize('extension',['.otf','.png','.svg'])
def test_rendered_font_and_texture_resources_invalidate_retained_pixels(tmp_path,extension):
    (tmp_path/'godot/assets').mkdir(parents=True)
    (tmp_path/'tests/godot').mkdir(parents=True)
    (tmp_path/'tests/godot/native_verovio_overlay.gd').write_text('extends SceneTree\n')
    resource=tmp_path/'godot/assets'/('notation'+extension)
    resource.write_bytes(b'original rendering resource')
    before=capture.capture_dependency_hash(tmp_path)
    resource.write_bytes(b'changed rendering resource')
    assert capture.capture_dependency_hash(tmp_path)!=before


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
