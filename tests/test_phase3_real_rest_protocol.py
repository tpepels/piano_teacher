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
    half=next(r for r in result["measured"] if r["required_rest"]=="half")
    assert half["status"]=="verified"
    assert half["observed_rest"]=="half"
    assert quarter["placement_evidence"]["status"] == "verified"
    assert half["placement_evidence"]["status"] == "verified"


@pytest.mark.parametrize("mutation",["wrong","missing"])
def test_real_wrong_or_hidden_atlas_glyph_is_detected_without_trusting_atlas(real_captures,mutation):
    result=real_captures[mutation]
    assert not result["passed"],result
    quarter=next(r for r in result["measured"] if r["required_rest"]=="quarter")
    assert quarter["status"]!="verified"


def test_real_dotted_rest_contours_are_independently_identified(tmp_path):
    source = tmp_path / "dotted.musicxml"
    source.write_text('''<score-partwise><part-list><score-part id="RH">
    <part-name>Right Hand</part-name></score-part></part-list><part id="RH">
    <measure number="1"><attributes><divisions>2</divisions>
    <time><beats>6</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note><rest/><duration>12</duration><voice>1</voice><type>whole</type><dot/></note></measure>
    <measure number="2"><note><rest/><duration>6</duration><voice>1</voice><type>half</type><dot/></note>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>6</duration><voice>1</voice><type>half</type><dot/></note></measure>
    <measure number="3"><note><rest/><duration>3</duration><voice>1</voice><type>quarter</type><dot/></note>
    <note><pitch><step>D</step><octave>4</octave></pitch><duration>3</duration><voice>1</voice><type>quarter</type><dot/></note>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>6</duration><voice>1</voice><type>half</type><dot/></note>
    </measure></part></score-partwise>''')
    prepared, _ = fixture(AuditCase("dotted-rests", str(source), 1, 3, "right"))
    prepared.update(phase3_full=True, sample_beats=[0.0, 6.0, 12.0])
    xml = prepared.pop("xml")
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(prepared))
    godot = shutil.which("godot") or shutil.which("godot4")
    assert godot, "Actual Godot required"
    proc = subprocess.run([godot, "--path", str(ROOT/"godot"), "--rendering-method",
        "gl_compatibility", "--script", str(ROOT/"tests/godot/native_verovio_overlay.gd"),
        "--", str(path), str(tmp_path)], capture_output=True, text=True, timeout=90,
        env={**os.environ, "LIBGL_ALWAYS_SOFTWARE":"1"})
    assert proc.returncode == 0, proc.stdout+proc.stderr
    result = verify_all_rest_pixels(xml, tmp_path, hand="right")
    assert result["complete"], result
    assert len(result["measured"]) == 3
    assert {r["observed_rest"] for r in result["measured"]} == {"whole", "half", "quarter"}
    assert all(r["dot_evidence"]["observed_count"] == 1 for r in result["measured"])
    assert result["placement_complete"], result
