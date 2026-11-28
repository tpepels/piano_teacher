"""Fault injection for the visual acceptance detector (not a fake renderer test)."""

from copy import deepcopy

import pytest
from PIL import Image, ImageDraw

from visual_continuity import compare


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
