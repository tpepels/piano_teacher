"""Phase 3 independent raster oracle must detect real pixel mutations."""
from io import BytesIO
import json
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw

from piano_teacher.notation.assets.glyphs import native_glyphs
from piano_teacher.notation.pixel_proof import RasterStaff, expected_y
from piano_teacher.notation.proof import read_written_score
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels

SOURCE = Path(__file__).parent / "fixtures/native_pixel_pitch_probe.musicxml"


def _score_frames(tmp_path: Path, *, move: tuple[str, int] | None = None,
                  omit: tuple[str, int] | None = None, gap=20):
    score=read_written_score(SOURCE.read_text())
    font=native_glyphs()
    (tmp_path/"fixture.json").write_text(json.dumps({
        "assets":{"native_glyphs":font}
    }))
    width,height=1536,520
    staves={
        "right":RasterStaff("right",tuple(120+i*gap for i in range(5)),gap),
        "left":RasterStaff("left",tuple(320+i*gap for i in range(5)),gap),
    }
    clefs={"right":("G",2,0),"left":("F",4,0)}
    glyph=font["head_black"]
    bounds=glyph["bounds"]
    w=round(bounds[2]*gap/250);h=round(bounds[3]*gap/250)
    mask=Image.open(BytesIO(cairosvg.svg2png(
        bytestring=glyph["svg"].encode(),output_width=w,
        output_height=h))).convert("RGBA")
    by_beat={}
    for sym in score.symbols:
        if sym["kind"]!="note":
            continue
        by_beat.setdefault(float(sym["beat"]),[]).append(sym)
    for beat,notes in sorted(by_beat.items()):
        picture=Image.new("RGBA",(width,height),(16,41,35,255))
        draw=ImageDraw.Draw(picture)
        for staff in staves.values():
            for y in staff.lines:
                draw.line((0,int(y),width-1,int(y)),
                          fill=(73,83,77),width=1)
        for sym in notes:
            hand=sym["staff"]
            if omit==(hand,int(beat)):
                continue
            yy=expected_y(staves[hand],sym["spelling"],clefs[hand])
            if move==(hand,int(beat)):
                yy-=gap/2  # one complete diatonic staff step
            x=round(width*.42)-w//2
            y=round(yy+bounds[1]*gap/250)
            picture.alpha_composite(mask,(x,y))
        picture.convert("RGB").save(tmp_path/f"native-{beat:.5f}.png")


def test_source_written_positions_match_independent_png_symbols(tmp_path):
    _score_frames(tmp_path)
    report=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path)
    assert report["passed"],report["failures"]
    assert report["written_active_noteheads"]==16
    assert report["image_pitch_verified"]==16


def test_one_staff_step_mutation_fails_raster_source_validation(tmp_path):
    _score_frames(tmp_path,move=("right",0))
    report=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path)
    assert not report["passed"]
    assert report["image_pitch_verified"]<16
    assert any("right" in error for error in report["failures"])


def test_one_staff_step_mutation_at_minimum_staff_scale_cannot_hide_in_registration(tmp_path):
    _score_frames(tmp_path,move=("right",0),gap=8)
    report=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path)
    assert not report["passed"]
    assert any(r["status"]=="unverified" for r in report["measured"])


def test_erased_head_fails_raster_source_validation(tmp_path):
    _score_frames(tmp_path,omit=("left",3))
    report=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path)
    assert not report["passed"]
    assert report["image_pitch_verified"]<16


def test_hand_mode_checks_only_active_hand(tmp_path):
    _score_frames(tmp_path)
    right=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path,hand="right")
    left=verify_all_notehead_pixels(SOURCE.read_text(),tmp_path,hand="left")
    assert right["passed"] and left["passed"]
    assert right["image_pitch_verified"]==8
    assert left["image_pitch_verified"]==8



def test_independent_clef_reference_covers_common_alternate_clefs():
    staff=RasterStaff("right",(120,140,160,180,200),20)
    # Treble G4 and bass F3 sit on their respective declared lines.
    assert expected_y(staff,("G",0,4),("G",2,0))==180
    assert expected_y(staff,("F",0,3),("F",4,0))==140
    # Alto C4 (C-clef line 3) and soprano C4 (line 1).
    assert expected_y(staff,("C",0,4),("C",3,0))==160
    assert expected_y(staff,("C",0,4),("C",1,0))==200
    # A treble 8vb note sounds an octave below the reference glyph.
    assert expected_y(staff,("G",0,3),("G",2,-1))==180
    # Ledger step G3 in ordinary treble must be below the five-line rail.
    assert expected_y(staff,("G",0,3),("G",2,0))==250


def test_seconds_can_displace_an_entire_chord_stem_group(tmp_path):
    xml='''<score-partwise><part-list><score-part id="LH"><part-name>Left</part-name>
    </score-part></part-list><part id="LH"><measure number="1"><attributes>
    <divisions>1</divisions><clef><sign>F</sign><line>4</line></clef></attributes>
    <note id="g"><pitch><step>G</step><octave>3</octave></pitch><duration>2</duration><type>half</type></note>
    <note id="a"><chord/><pitch><step>A</step><octave>3</octave></pitch><duration>2</duration><type>half</type></note>
    <note id="d"><chord/><pitch><step>D</step><octave>4</octave></pitch><duration>2</duration><type>half</type></note>
    </measure></part></score-partwise>'''
    picture=Image.new("RGBA",(1536,520),(16,41,35,255))
    pen=ImageDraw.Draw(picture)
    for yy in (120,140,160,180,200,320,340,360,380,400):
        pen.line((0,yy,1535,yy),fill=(73,83,77))
    staff=RasterStaff("left",(320,340,360,380,400),20)
    spec=native_glyphs()["head_half"]
    b=spec["bounds"]
    w,h=round(b[2]*20/250),round(b[3]*20/250)
    mask=Image.open(BytesIO(cairosvg.svg2png(bytestring=spec["svg"].encode(),
                                          output_width=w,output_height=h))).convert("RGBA")
    for step,octave,dx in (("G",3,0),("A",3,24),("D",4,24)):
        y=expected_y(staff,(step,0,octave),("F",4,0))
        picture.alpha_composite(mask,(round(1536*.42)-w//2+dx,round(y+b[1]*20/250)))
    picture.convert("RGB").save(tmp_path/"native-0.00000.png")
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert result["passed"],result["failures"]
    assert next(r for r in result["measured"] if r["spelling"]==("D",0,4))["status"]=="verified"
    assert not any(r["status"]=="mismatch" for r in result["measured"])


def test_unison_voices_cannot_both_be_certified_from_one_shared_head(tmp_path):
    _score_frames(tmp_path)
    xml=SOURCE.read_text()
    from xml.etree import ElementTree as ET
    from copy import deepcopy
    root=ET.fromstring(xml)
    measure=root.find("part/measure")
    first=measure.find("note")
    duplicate=deepcopy(first)
    duplicate.set("id","unison-second-voice")
    duplicate.find("voice").text="2"
    backup=ET.SubElement(measure,"backup")
    ET.SubElement(backup,"duration").text=str(sum(int(n.findtext("duration")) for n in measure.findall("note")))
    measure.append(duplicate)
    report=verify_all_notehead_pixels(ET.tostring(root,encoding="unicode"),tmp_path)
    assert not report["complete"]
    unisons=[r for r in report["measured"] if r["beat"]==0 and r["staff"]=="right"]
    assert len(unisons)==2
    assert all(r["status"]=="ambiguous" for r in unisons)


def test_wrong_staff_step_in_adjacent_chord_cannot_be_certified(tmp_path):
    xml='''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name></score-part>
    </part-list><part id="RH"><measure number="1"><attributes><divisions>1</divisions>
    <clef><sign>G</sign><line>2</line></clef></attributes><note id="c"><pitch><step>C</step><octave>5</octave></pitch>
    <duration>1</duration><type>quarter</type></note><note id="d"><chord/><pitch><step>D</step><octave>5</octave></pitch>
    <duration>1</duration><type>quarter</type></note></measure></part></score-partwise>'''
    picture=Image.new("RGBA",(1536,520),(16,41,35,255))
    pen=ImageDraw.Draw(picture)
    for yy in (120,140,160,180,200,320,340,360,380,400):
        pen.line((0,yy,1535,yy),fill=(73,83,77))
    spec=native_glyphs()["head_black"];b=spec["bounds"]
    w,h=round(b[2]*20/250),round(b[3]*20/250)
    mask=Image.open(BytesIO(cairosvg.svg2png(bytestring=spec["svg"].encode(),
                                          output_width=w,output_height=h))).convert("RGBA")
    staff=RasterStaff("right",(120,140,160,180,200),20)
    for step,dx,dy in (("C",0,10),("D",20,0)):
        yy=expected_y(staff,(step,0,5),("G",2,0))+dy
        picture.alpha_composite(mask,(round(1536*.42)-w//2+dx,round(yy+b[1]*20/250)))
    picture.convert("RGB").save(tmp_path/"native-0.00000.png")
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert not result["complete"]
    assert all(row["status"]=="ambiguous" for row in result["measured"])


def test_actual_correct_ledger_chord_is_unverified_instead_of_a_claimed_wrong_pitch(tmp_path):
    import shutil
    # Actual protocol-2 Godot capture: Chopin measures 33-36, beat zero.
    # Correct B5/B6 half heads overlap the octave chord's ledger/stem ink.
    shutil.copy(Path(__file__).parent/"fixtures/native_ledger_overlap.png",tmp_path/"native-0.00000.png")
    xml='''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name></score-part></part-list>
    <part id="RH"><measure number="1"><attributes><divisions>1</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="b5"><pitch><step>B</step><octave>5</octave></pitch><duration>2</duration><type>half</type></note>
    <note id="b6"><chord/><pitch><step>B</step><octave>6</octave></pitch><duration>2</duration><type>half</type></note>
    </measure></part></score-partwise>'''
    result=verify_all_notehead_pixels(xml,tmp_path,hand="right")
    lower=next(row for row in result["measured"] if row["source_id"]=="b5")
    assert lower["match"]<.79
    assert lower["status"]=="unverified"
    assert not result["complete"]
