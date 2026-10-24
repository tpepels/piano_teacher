"""Dotted seconds need separate authentic dots clear of every chord head."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from copy import deepcopy

from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.visual_coverage import visual_elements
from scripts.check_native_verovio_overlay import AuditCase, fixture

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def captured(tmp_path_factory):
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot or not os.environ.get("DISPLAY"):
        pytest.skip("Actual native dot pixels require Godot and a display")
    out=tmp_path_factory.mktemp("native-chord-dots")
    data,_=fixture(AuditCase("dotted-seconds","Danny_Boy(Bill_Evans_Ver_).midi",17,17,"right"))
    xml=data.pop("xml")
    data["sample_beats"]=[0.]
    data["phase3_full"]=True
    path=out/"fixture.json"
    path.write_text(json.dumps(data))
    result=subprocess.run([godot,"--path",str(ROOT/"godot"),"--rendering-method","gl_compatibility",
        "--windowed","--resolution","16x16","--position","-16384,-16384","--disable-vsync",
        "--script",str(ROOT/"tests/godot/native_verovio_overlay.gd"),"--",str(path),str(out)],
        capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    return xml,out


def test_every_dotted_chord_tone_has_its_own_isolated_dot(captured):
    xml,out=captured
    report=verify_note_feature_pixels(xml,out,hand="right")
    dots=[r["features"]["dot"] for r in report["measured"] if r["beat"]==0.]
    assert len(dots)==4 and all(r["status"]=="verified" for r in dots),dots
    boxes=[tuple(r["evidence"]["dots"][0]["bbox"]) for r in dots]
    assert len(set(boxes))==4
    assert all(r["features"]["flag_absence"]["status"]=="verified"
               for r in report["measured"] if r["beat"]==0.),report
    ledger=visual_elements(None,xml,verify_all_notehead_pixels(xml,out,hand="right"),{},
                           hand="right",feature_report=report)
    rhythms=[r for r in ledger if r["construct"]=="note_rhythm" and r["source"]["beat"]==0.]
    assert len(rhythms)==4 and all(r["status"]=="verified" for r in rhythms),rhythms


def test_erasing_one_chord_dot_cannot_borrow_a_neighbor(captured,tmp_path):
    xml,out=captured
    report=verify_note_feature_pixels(xml,out,hand="right")
    c=next(r for r in report["measured"] if r["beat"]==0. and tuple(r["spelling"])==("C",0,4))
    assert c["features"]["dot"]["status"]=="verified",c
    picture=Image.open(out/"native-0.00000.png").convert("RGB")
    box=c["features"]["dot"]["evidence"]["dots"][0]["bbox"]
    ImageDraw.Draw(picture).rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=picture.getpixel((10,10)))
    picture.save(tmp_path/"native-0.00000.png")
    changed=verify_note_feature_pixels(xml,tmp_path,hand="right")
    chord=[r for r in changed["measured"] if r["beat"]==0.]
    assert sum(r["features"]["dot"]["status"]=="verified" for r in chord)==3


@pytest.mark.parametrize("mutation",["foreign-owner","changed-dot","missing-dot-proof"])
def test_legitimate_dot_exclusion_requires_the_bound_independent_contour(captured,mutation):
    xml,out=captured
    report=deepcopy(verify_note_feature_pixels(xml,out,hand="right"))
    chord=[r for r in report["measured"] if r["beat"]==0.]
    associated=chord[0]["features"]["flag_absence"]["evidence"]["associated_dots"]
    assert associated
    if mutation=="foreign-owner":
        associated[0]["source_id"]="a different source note"
    else:
        owner=next(r for r in chord if r["source_id"]==associated[0]["source_id"])
        if mutation=="changed-dot":
            owner["features"]["dot"]["evidence"]["dots"][0]["bbox"][0]+=1
        else:
            owner["features"]["dot"]["status"]="unverified"
    ledger=visual_elements(None,xml,verify_all_notehead_pixels(xml,out,hand="right"),{},
                           hand="right",feature_report=report)
    rhythm=next(r for r in ledger if r["construct"]=="note_rhythm" and r["source"]["beat"]==0.)
    assert rhythm["status"]!="verified"
