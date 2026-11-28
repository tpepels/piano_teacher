"""Fault injection for the visual acceptance detector (not a fake renderer test)."""

import io
import json
import struct
from copy import deepcopy

import pytest
from PIL import Image, ImageDraw
from visual_continuity import analyze, compare


def frame(dx=0, *, notes=True, dy=0, fill=(15,45,35), cue=False, extra=False):
    image = Image.new("RGB",(640,400),fill)
    draw = ImageDraw.Draw(image)
    for y in (120,132,144,156,168,226,238,250,262,274):
        draw.line((30,y+dy,615,y+dy),fill=(118,138,130),width=1)
    if notes:
        for x,y in ((200,146),(250,160),(400,245),(460,227)):
            x += dx
            y += dy
            draw.ellipse((x-6,y-4,x+6,y+4),fill=(225,245,235))
            draw.line((x+6,y,x+6,y-28),fill=(225,245,235),width=2)
    if cue:
        draw.ellipse((40,100,90,150),fill=(60,220,165))
    if extra:
        draw.rectangle((290,190,320,210),fill=(225,245,235))
    return image


def metadata():
    old = {"score":[0,0,1,1],"playhead":.23,"count_in":None,
           "layers":[{"id":1,"world":0.,"density":.25}],"world":0.,
           "staff_hand":"both","check_score":True}
    new = deepcopy(old)
    new["layers"][0]["world"] = .05
    new["world"] = .05
    return old,new


def test_normal_scroll_and_count_in_are_allowed():
    old,new = metadata()
    assert compare(frame(),frame(-8),old,new)[0] == []
    new["count_in"] = [.06,.25,.08,.13]
    assert compare(frame(),frame(-8,cue=True),old,new)[0] == []


@pytest.mark.parametrize(("kwargs","reason"),[
    ({"notes":False},"visible_ink_disappeared"),
    ({"dy":18},"staff_disappeared_or_shifted"),
    ({"fill":(240,240,240)},"large_background_or_screen_flash"),
    ({"extra":True},"unexpected_interior_ink"),
])
def test_single_frame_visual_defects_are_detected(kwargs,reason):
    old,new = metadata()
    assert reason in compare(frame(),frame(-8,**kwargs),old,new)[0]


def test_jump_is_not_excused_by_expected_scroll():
    old,new = metadata()
    assert "visible_ink_disappeared" in compare(frame(),frame(-50),old,new)[0]


def test_long_hitch_keeps_staff_and_background_checks():
    old,new = metadata()
    new["world"] = 10.
    new["layers"][0]["world"] = 10.
    reasons,metrics,_ = compare(frame(),frame(notes=False),old,new)
    assert not reasons
    assert metrics["overlap_unavailable"]
    assert "large_background_or_screen_flash" in compare(
        frame(),Image.new("RGB",(640,400),"white"),old,new)[0]


def test_score_only_flash_is_detected():
    old,new = metadata()
    old["score"] = new["score"] = [0,.25,1,.5]
    before = frame()
    after = before.copy()
    ImageDraw.Draw(after).rectangle((0,100,639,299),fill=(220,220,220))
    assert "large_score_flash" in compare(before,after,old,new)[0]


def test_capture_detects_single_frame_flash_and_saves_surrounding_frames(tmp_path):
    capture = tmp_path/"capture"
    capture.mkdir()
    old,_ = metadata()
    old.update(screen="practice",piece="fixture",ready=True,mode="practice",
               phase="playing",step="tempo",bpm=90)
    with (capture/"frames.bin").open("wb") as images, (capture/"frames.jsonl").open("w") as records:
        for index in range(9):
            meta = deepcopy(old)
            meta.update(frame=index,engine_frame=100+index,time_ms=index*33)
            meta["world"] = meta["layers"][0]["world"] = index*.05
            image = (Image.new("RGB",(640,400),"white") if index == 4
                     else frame(-8*index))
            encoded = io.BytesIO()
            image.save(encoded,format="PNG")
            data = encoded.getvalue()
            images.write(struct.pack("<I",len(data))+data)
            records.write(json.dumps(meta)+"\n")
    (capture/"complete.json").write_text(json.dumps({"frames":9,"success":True}))
    output = tmp_path/"report"
    assert not analyze(capture,output)
    report = json.loads((output/"report.json").read_text())
    assert any(item.get("frame") == 4 and "large_background_or_screen_flash" in item["reasons"]
               for item in report["failures"])
    witness = output/"failure-000004"
    assert (witness/"frame-000001.png").is_file()
    assert (witness/"frame-000004.json").is_file()
    assert (witness/"frame-000007.png").is_file()
    # A seemingly clean recording without a complete end marker must fail.
    (capture/"complete.json").write_text(json.dumps({"frames":8,"success":True}))
    assert not analyze(capture,tmp_path/"truncated")
    incomplete = json.loads((tmp_path/"truncated/report.json").read_text())
    assert any("invalid_capture" in item["reasons"] for item in incomplete["failures"])



def test_motion_compensation_cannot_hide_a_scroll_sprint():
    old,new = metadata()
    old.update(time_ms=1000,bpm=80,mode="learn")
    new.update(time_ms=1035,bpm=80,mode="learn",world=.15)
    new["layers"][0]["world"] = .15
    reasons,metrics,_ = compare(frame(),frame(-24),old,new)
    assert "excessive_scroll_velocity" in reasons
    assert metrics["scroll_bpm"] > 250


def test_ordinary_motion_with_timestamps_passes():
    old,new = metadata()
    old.update(time_ms=1000,bpm=90,mode="practice")
    new.update(time_ms=1033.333,bpm=90,mode="practice")
    assert compare(frame(),frame(-8),old,new)[0] == []


def test_new_admission_allows_only_added_ink_in_its_own_future_slot():
    old,new = metadata()
    old["layers"][0]["strips"] = []
    new["layers"][0]["strips"] = [{"id":"new","left":.44,"right":.51,
        "gutter":.04,"visible":True,"authorized":True,"admitted_inside":True,"future":True}]
    assert compare(frame(),frame(-8,extra=True),old,new)[0] == []
    assert "visible_ink_disappeared" in compare(
        frame(),frame(-8,notes=False,extra=True),old,new)[0]
    new["layers"][0]["strips"][0]["authorized"] = False
    assert "unexpected_interior_ink" in compare(frame(),frame(-8,extra=True),old,new)[0]


def test_visible_strip_retirement_is_detected_even_with_small_ink_loss():
    old,new = metadata()
    old["layers"][0]["strips"] = [{"id":"visible","left":.5,"right":.7,
        "gutter":.04,"visible":True,"authorized":True,"admitted_inside":True,"future":True}]
    new["layers"][0]["strips"] = []
    assert "visible_strip_retired_before_exit" in compare(frame(),frame(-8),old,new)[0]
    old["layers"][0]["strips"][0].update(left=.01,right=.041)
    assert "visible_strip_retired_before_exit" not in compare(frame(),frame(-8),old,new)[0]



def test_complete_layer_loss_and_hidden_existing_strip_fail():
    old,new = metadata()
    old["layers"][0]["strips"] = [{"id":"visible","left":.5,"right":.7,
        "gutter":.04,"visible":True,"authorized":True,"admitted_inside":True,"future":True}]
    new["strip_witness_version"] = 1
    new["layers"] = []
    assert "visible_strip_retired_before_exit" in compare(frame(),frame(-8),old,new)[0]
    new["layers"] = deepcopy(old["layers"])
    new["layers"][0]["world"] = .05
    new["layers"][0]["strips"][0]["visible"] = False
    assert "visible_strip_retired_before_exit" in compare(frame(),frame(-8),old,new)[0]
