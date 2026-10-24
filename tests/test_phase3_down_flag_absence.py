"""Quarter absence follows the external flag side, independently of stem direction."""
from copy import deepcopy
from math import ceil

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import _feature_glyphs, verify_note_feature_pixels
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.reference_font import reference_glyphs
from piano_teacher.notation.symbol_pixel_proof import _outline
from piano_teacher.notation.visual_coverage import visual_elements


INK = (229, 242, 234)


def quarter(tmp_path, direction="down"):
    xml = f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><time><beats>1</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes><note id="quarter">
    <pitch><step>D</step><octave>5</octave></pitch><duration>1</duration>
    <voice>1</voice><type>quarter</type><stem>{direction}</stem></note>
    </measure></part></score-partwise>'''
    picture = Image.new("RGB", (400, 560), "#102923")
    draw = ImageDraw.Draw(picture)
    for bottom in (260, 480):
        for line in range(5):
            draw.line((0, bottom+(line-4)*16, 399, bottom+(line-4)*16), fill=(73, 83, 77))
    glyph = reference_glyphs()["head_black"]
    b = glyph["bounds"]
    width, height = round(b[2]*16/250), round(b[3]*16/250)
    left, top = round(168-b[2]*16/500), round(212+b[1]*16/250)
    head = _outline(glyph["svg"], width, height)
    pixels = np.array(picture)
    pixels[top:top+height, left:left+width][head] = INK
    xs = np.nonzero(head)[1]
    x = left+int(xs.min() if direction == "down" else xs.max())
    tip = 276 if direction == "down" else 148
    pixels[min(212, tip):max(212, tip)+1, x] = INK
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    return xml, pixels, x, tip


def flag_pixels(direction, count, x, origin_y):
    # Stamp the independent font at its SMuFL origin. Actual shaft recovery,
    # not the test, handles any continuation past that origin in short flags.
    glyph = _feature_glyphs()[f"flag_{direction}_{count}"]
    b = glyph["bounds"]
    width, height = round(b[2]*16/250), round(b[3]*16/250)
    yy, xx = np.nonzero(_outline(glyph["svg"], width, height))
    return yy+round(origin_y+b[1]*16/250), xx+round(x+b[0]*16/250)


def rhythm(xml, folder, features):
    ledger = visual_elements(None, xml, verify_all_notehead_pixels(xml, folder, hand="right"),
                             {}, hand="right", feature_report=features)
    return next(row for row in ledger if row["construct"] == "note_rhythm")


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("count", range(1, 6))
def test_partial_flag_on_external_font_side_blocks_quarter_absence(tmp_path, direction, count):
    xml, pixels, x, tip = quarter(tmp_path, direction)
    yy, xx = flag_pixels(direction, count, x, tip)
    # A distal fragment more than 1.9 staff spaces from the tip is outside
    # a small root crop, but inside the unchanged 2.5-space attachment ROI.
    distance = tip-yy if direction == "down" else yy-tip
    retained = (31 <= distance) & (distance < 36) & (xx >= x+3)
    assert retained.any()
    pixels[yy[retained], xx[retained]] = INK
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    report = verify_note_feature_pixels(xml, tmp_path, hand="right")
    features = report["measured"][0]["features"]
    assert features["stem"]["status"] == "verified", features
    absence = features["flag_absence"]
    assert max(absence["evidence"]["family_scores"].values()) < .72
    assert absence["status"] == "unverified", absence
    assert absence["evidence"]["bright_pixels"] > 0
    assert rhythm(xml, tmp_path, report)["status"] != "verified"


@pytest.mark.parametrize("direction", ["up", "down"])
@pytest.mark.parametrize("count", range(1, 6))
def test_every_intact_external_flag_still_rejects_a_quarter(tmp_path, direction, count):
    xml, pixels, x, tip = quarter(tmp_path, direction)
    yy, xx = flag_pixels(direction, count, x, tip)
    pixels[yy, xx] = INK
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    report = verify_note_feature_pixels(xml, tmp_path, hand="right")
    features = report["measured"][0]["features"]
    assert features["stem"]["status"] == "verified", features
    assert features["flag_absence"]["status"] == "mismatch", features
    assert max(features["flag_absence"]["evidence"]["family_scores"].values()) >= .72
    assert rhythm(xml, tmp_path, report)["status"] != "verified"


def test_left_neighbor_does_not_substitute_for_rightward_down_flag_ink(tmp_path):
    xml, pixels, x, tip = quarter(tmp_path)
    pixels[tip-35:tip-33, x-8:x-1] = INK
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    report = verify_note_feature_pixels(xml, tmp_path, hand="right")
    features = report["measured"][0]["features"]
    assert features["stem"]["status"] == "verified"
    assert features["flag_absence"]["status"] == "verified", features
    assert rhythm(xml, tmp_path, report)["status"] == "verified"


@pytest.mark.parametrize("region", ["obsolete-left", "shortened-depth"])
def test_consumer_rejects_empty_region_outside_the_full_rightward_attachment(tmp_path, region):
    xml, _, x, tip = quarter(tmp_path)
    report = deepcopy(verify_note_feature_pixels(xml, tmp_path, hand="right"))
    evidence = report["measured"][0]["features"]["flag_absence"]["evidence"]
    if region == "obsolete-left":
        evidence["bbox"] = [132, 236, 157, 279]
    else:
        evidence["bbox"] = [160, tip-8, ceil(x+1.6*16), tip+3]
    box = evidence["bbox"]
    evidence["sampled_pixels"] = (box[2]-box[0])*(box[3]-box[1])
    assert rhythm(xml, tmp_path, report)["status"] != "verified"
