"""End-to-end mutations in the actual Godot framebuffer, run explicitly in CI."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels
from scripts.check_native_verovio_overlay import AuditCase, ROOT, fixture


pytestmark=pytest.mark.skipif(os.environ.get("PIANO_REAL_PIXEL_TESTS")!="1",
                            reason="explicit real framebuffer job uses xvfb/software OpenGL")


@pytest.fixture(scope="module")
def real_captures(tmp_path_factory):
    root=tmp_path_factory.mktemp("real-rest-protocol")
    case=AuditCase("rest-protocol","tests/fixtures/native_pixel_rest_probe.musicxml",1,1)
    prepared,_=fixture(case)
    prepared.update(phase3_full=True,sample_beats=[0.0,2.0])
    xml=prepared.pop("xml")
    godot=shutil.which("godot") or shutil.which("godot4")
    assert godot,"CI must install actual Godot"
    outputs={}
    for mutation in ("baseline","wrong","missing"):
        data=deepcopy(prepared)
        glyphs=data["assets"]["native_glyphs"]
        if mutation=="wrong":
            glyphs["rest_quarter"]["svg"]=glyphs["rest_eighth"]["svg"]
            glyphs["rest_quarter"]["bounds"]=glyphs["rest_eighth"]["bounds"]
        elif mutation=="missing":
            glyphs["rest_quarter"]["svg"]=glyphs["rest_quarter"]["svg"].replace(
                "<svg ",'<svg opacity="0" ',1)
        folder=root/mutation
        folder.mkdir()
        path=folder/"fixture.json"
        path.write_text(json.dumps(data))
        result=subprocess.run([godot,"--path",str(ROOT/"godot"),"--rendering-method",
            "gl_compatibility","--script",str(ROOT/"tests/godot/native_verovio_overlay.gd"),
            "--",str(path),str(folder)],capture_output=True,text=True,timeout=90,
            env={**os.environ,"LIBGL_ALWAYS_SOFTWARE":"1"})
        (folder/"godot.log").write_text(result.stdout+result.stderr)
        assert result.returncode==0,result.stdout+result.stderr
        outputs[mutation]=verify_all_rest_pixels(xml,folder)
    return outputs


def test_actual_unchanged_and_restored_framebuffers_are_stable(real_captures):
    result=real_captures["baseline"]
    assert result["passed"],result["failures"]
    quarter=next(r for r in result["measured"] if r["required_rest"]=="quarter")
    assert quarter["status"]=="verified"


@pytest.mark.parametrize("mutation",["wrong","missing"])
def test_real_wrong_or_hidden_atlas_glyph_is_detected_without_trusting_atlas(real_captures,mutation):
    result=real_captures[mutation]
    assert not result["passed"],result
    quarter=next(r for r in result["measured"] if r["required_rest"]=="quarter")
    assert quarter["status"]!="verified"
