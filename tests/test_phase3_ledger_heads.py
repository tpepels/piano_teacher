"""Authentic ledger rules may cross hollow heads without filling their holes."""
from pathlib import Path
from shutil import copyfile

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.reference_font import reference_glyphs
from piano_teacher.notation.pixel_ink import rasterize_outline
from piano_teacher.notation.feature_pixels import verify_note_feature_pixels

FIXTURE = Path(__file__).parent/"fixtures/native_ledger_chord"


def test_detached_ledger_mark_cannot_mask_a_filled_head_as_half_at_8_5_gap(tmp_path):
    xml = '''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="h"><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>
    <type>half</type></note></measure></part></score-partwise>'''
    picture = Image.new("RGB", (400, 240), "#102923")
    draw = ImageDraw.Draw(picture)
    for bottom in (100, 194):
        for line in range(5):
            y = round(bottom+(line-4)*8.5)
            draw.line((0, y, 399, y), fill=(73, 83, 77))
    assert detect_staff_lines(picture)["right"].gap == 8.5
    # An authentic FILLED C4 head at the fixed playhead. The XML requires a
    # hollow half head, so an unrelated mark must never change its identity.
    glyph = reference_glyphs()["head_black"]
    b = glyph["bounds"]
    width, height = round(b[2]*8.5/250), round(b[3]*8.5/250)
    left, top = round(168-b[2]*8.5/500), round(108.5+b[1]*8.5/250)
    pixels = np.asarray(picture).copy()
    pixels[top:top+height, left:left+width][rasterize_outline(glyph["svg"], width, height)] = (229, 242, 234)
    path = tmp_path/"native-0.00000.png"
    Image.fromarray(pixels).save(path)
    control = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    assert control["measured"][0]["source_id"] == "h"
    assert control["measured"][0]["status"] != "verified"
    # The head ends at x=172. This two-row line begins at x=179, leaving
    # six blank columns. It neither covers nor touches the candidate head.
    pixels[107:109, 179:193] = (229, 242, 234)
    Image.fromarray(pixels).save(path)
    changed = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    row, = changed["measured"]
    assert row["source_id"] == "h" and row["glyph"] == "head_half"
    assert row["status"] != "verified", row
    assert not changed["complete"]


def test_spanning_ledger_cannot_mask_a_filled_head_as_half_at_8_5_gap(tmp_path):
    xml = '''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="h"><pitch><step>C</step><octave>4</octave></pitch><duration>2</duration>
    <type>half</type></note></measure></part></score-partwise>'''
    picture = Image.new("RGB", (400, 240), "#102923")
    draw = ImageDraw.Draw(picture)
    for bottom in (100, 194):
        for line in range(5):
            y = round(bottom+(line-4)*8.5)
            draw.line((0, y, 399, y), fill=(73, 83, 77))
    assert detect_staff_lines(picture)["right"].gap == 8.5
    glyph = reference_glyphs()["head_black"]
    b = glyph["bounds"]
    width, height = round(b[2]*8.5/250), round(b[3]*8.5/250)
    left, top = round(168-b[2]*8.5/500), round(108.5+b[1]*8.5/250)
    pixels = np.asarray(picture).copy()
    pixels[top:top+height, left:left+width][rasterize_outline(glyph["svg"], width, height)] = (229, 242, 234)
    # A genuine thin C4 ledger spans the entire candidate head. Correct
    # ownership permits occlusion handling, but cannot change a filled head
    # into the source-required hollow family at this supported small scale.
    pixels[107:109, 158:178] = (229, 242, 234)
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    black = verify_all_notehead_pixels(xml.replace("<type>half</type>", "<type>quarter</type>"),
                                      tmp_path, hand="right")
    assert black["complete"], black
    changed = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    row, = changed["measured"]
    assert row["source_id"] == "h" and row["glyph"] == "head_half"
    assert row["status"] != "verified", row
    assert not changed["complete"]


def test_real_native_half_note_seconds_keep_independent_head_identity():
    result = verify_all_notehead_pixels((FIXTURE/"score.musicxml").read_text(), FIXTURE, hand="right")
    assert result["complete"], result
    assert result["image_pitch_verified"] == result["written_active_noteheads"] == 8


def test_stem_attaches_both_sides_of_genuine_displaced_chord_heads():
    report = verify_note_feature_pixels((FIXTURE/"score.musicxml").read_text(),FIXTURE,hand="right")
    stems = [r["features"]["stem"] for r in report["measured"]]
    assert len(stems) == 8 and all(r["status"] == "verified" for r in stems), stems


@pytest.mark.parametrize("mutation", ["erased", "filled", "wrong-pitch"])
def test_ledger_context_cannot_replace_or_misidentify_a_hollow_head(tmp_path, mutation):
    xml = (FIXTURE/"score.musicxml").read_text()
    baseline = verify_all_notehead_pixels(xml, FIXTURE, hand="right")
    row = next(r for r in baseline["measured"] if r["beat"] == 2 and tuple(r["spelling"]) == ("C",0,4))
    with Image.open(FIXTURE/"native-2.00000.png") as image:
        picture = image.convert("RGB")
    pixels = np.asarray(picture).copy()
    rail = detect_staff_lines(picture)["right"]
    spec = reference_glyphs()["head_half"]
    width,height = (round(spec["bounds"][i]*rail.gap/250) for i in (2,3))
    x,y = (row["joint_assignment"][k] for k in ("x","y"))
    if mutation in ("erased", "wrong-pitch"):
        # Preserve the genuine ledger line itself: a line/stem alone must
        # never supply the missing head's required independent contour.
        for yy in range(y,y+height):
            if abs(yy-row["target_y"]) > 1.5:
                pixels[yy,x:x+width] = pixels[10,10]
    if mutation != "erased":
        glyph = reference_glyphs()["head_black" if mutation == "filled" else "head_half"]
        b = glyph["bounds"]
        w,h = round(b[2]*rail.gap/250),round(b[3]*rail.gap/250)
        xx = round(x+width/2-w/2)
        yy = round(row["target_y"]+b[1]*rail.gap/250-(rail.gap/2 if mutation == "wrong-pitch" else 0))
        pixels[yy:yy+h,xx:xx+w][rasterize_outline(glyph["svg"],w,h)] = (231,244,236)
    Image.fromarray(pixels).save(tmp_path/"native-2.00000.png")
    for clock in (0.,1.5):
        copyfile(FIXTURE/f"native-{clock:.5f}.png",tmp_path/f"native-{clock:.5f}.png")
    result = verify_all_notehead_pixels(xml,tmp_path,hand="right")
    assert not result["complete"], f"Counterfeit {mutation} hollow head was certified"
