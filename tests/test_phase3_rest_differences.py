"""Controlled image subtraction must not manufacture proof of a rest."""
import json
from io import BytesIO

import cairosvg
import pytest
from PIL import Image, ImageDraw

from piano_teacher.notation.assets.glyphs import native_glyphs
from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels


def _captures(folder, *, kind="quarter", shift=0, mutation=None):
    xml = f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes><note id="source-rest">
    <rest/><duration>4</duration><voice>1</voice><type>{kind}</type></note>
    </measure></part></score-partwise>'''
    glyphs = native_glyphs()
    (folder / "fixture.json").write_text(json.dumps({"assets":{"native_glyphs":glyphs}}))
    bg = Image.new("RGB", (1536,520), (16,41,35))
    pen = ImageDraw.Draw(bg)
    for y in (120,140,160,180,200,320,340,360,380,400):
        pen.line((0,y,1535,y), fill=(73,83,77))
    # Dense neighboring ink remains identical in both images.
    pen.ellipse((670,155,692,167),fill=(220,230,215))
    glyph = glyphs["rest_" + ("eighth" if mutation=="wrong" else kind)]
    b = glyph["bounds"]
    w,h = round(b[2]*20/250), round(b[3]*20/250)
    mask=Image.open(BytesIO(cairosvg.svg2png(bytestring=glyph["svg"].encode(),
                                          output_width=w,output_height=h))).convert("RGBA")
    original = bg.copy().convert("RGBA")
    x,y = round(1536*.42)-w//2,round(160+b[1]*20/250+shift)
    if mutation not in ("missing","dark-addition"):
        original.alpha_composite(mask,(x,y))
    original=original.convert("RGB")
    original.save(folder/"native-0.00000.png")
    original.save(folder/"repeat-0.00000.png")
    restored=original.copy()
    if mutation=="restore-drift":
        ImageDraw.Draw(restored).rectangle((1000,100,1010,110),fill="white")
    restored.save(folder/"restored-0.00000.png")
    suppressed=bg.copy()
    if mutation=="dark-addition":
        suppressed.paste((0,0,0),(x,y,x+w,y+h),mask.getchannel("A"))
    if mutation=="contaminated":
        ImageDraw.Draw(suppressed).rectangle((1000,100,1010,110),fill="white")
    suppressed.save(folder/"without.png")
    (folder/"native-overlay-report.json").write_text(json.dumps({
        "rest_difference_protocol":2,
        "rest_difference_frames":[{"clock":0,"repeat_file":"repeat-0.00000.png",
                                   "restored_file":"restored-0.00000.png"}],
        "rest_difference_controls":[{"id":"native-rest","clock":0,"staff":"right",
                                     "voice":"1","file":"without.png"}]}))
    return xml


@pytest.mark.parametrize("shift", [0,-45,45])
def test_legitimate_displaced_rest_contour_survives_dense_unchanged_ink(tmp_path, shift):
    report=verify_all_rest_pixels(_captures(tmp_path,shift=shift),tmp_path)
    assert report["passed"],report["failures"]
    assert report["image_rest_glyphs_verified"]==1
    assert report["measured"][0]["source_id"]=="source-rest"


@pytest.mark.parametrize("mutation", ["wrong","missing","contaminated","restore-drift"])
def test_wrong_missing_or_uncontrolled_image_cannot_verify_rest(tmp_path,mutation):
    report=verify_all_rest_pixels(_captures(tmp_path,mutation=mutation),tmp_path)
    assert not report["passed"]
    assert report["image_rest_glyphs_verified"]==0


def test_block_rest_family_is_ambiguous_and_never_counted_as_identity_verified(tmp_path):
    report=verify_all_rest_pixels(_captures(tmp_path,kind="half"),tmp_path)
    assert report["image_rest_glyphs_verified"]==0
    assert report["coverage"]["ambiguous"]==1
    assert report["measured"][0]["status"]=="ambiguous"


def test_renderer_atlas_corruption_does_not_change_independent_font_expectation(tmp_path):
    xml=_captures(tmp_path,mutation="wrong")
    path=tmp_path/"fixture.json"
    data=json.loads(path.read_text())
    data["assets"]["native_glyphs"]["rest_quarter"]=data["assets"]["native_glyphs"]["rest_eighth"]
    path.write_text(json.dumps(data))
    report=verify_all_rest_pixels(xml,tmp_path)
    assert not report["passed"]
    assert report["measured"][0]["status"]=="mismatch"
    assert report["measured"][0]["observed_rest"]=="eighth"


@pytest.mark.parametrize("kind",["whole","half","quarter","eighth","16th","32nd","64th","128th"])
def test_authentic_rest_families_have_explicit_verified_or_ambiguous_status(tmp_path,kind):
    report=verify_all_rest_pixels(_captures(tmp_path,kind=kind),tmp_path)
    assert report["passed"],report["failures"]
    status="ambiguous" if kind in ("whole","half") else "verified"
    assert report["measured"][0]["status"]==status


@pytest.mark.parametrize("kind",["whole","half","quarter","16th","32nd","64th","128th"])
def test_substituting_eighth_rest_never_verifies_another_family(tmp_path,kind):
    report=verify_all_rest_pixels(_captures(tmp_path,kind=kind,mutation="wrong"),tmp_path)
    assert not report["passed"]
    assert report["image_rest_glyphs_verified"]==0
    assert "raster" not in str(report["failures"])


def test_old_cropped_subtraction_protocol_is_explicitly_unverified(tmp_path):
    xml=_captures(tmp_path)
    path=tmp_path/"native-overlay-report.json"
    data=json.loads(path.read_text())
    data.pop("rest_difference_protocol")
    path.write_text(json.dumps(data))
    report=verify_all_rest_pixels(xml,tmp_path)
    assert not report["passed"]
    assert report["coverage"]["unverified"]==1


def test_adding_a_dark_glyph_to_the_control_is_not_removal_of_an_original_rest(tmp_path):
    report=verify_all_rest_pixels(_captures(tmp_path,mutation="dark-addition"),tmp_path)
    assert not report["passed"]
    assert not report["complete"]
    assert report["image_rest_glyphs_verified"]==0
