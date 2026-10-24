"""Phase 3 independent raster oracle must detect real pixel mutations."""
from io import BytesIO
import json
from pathlib import Path

import cairosvg
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.assets.glyphs import native_glyphs
from piano_teacher.notation.pixel_proof import RasterStaff, expected_y, detect_staff_lines
from piano_teacher.notation.reference_font import reference_glyphs
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
    assert not result["passed"]
    assert next(row for row in result["measured"] if row["source_id"]=="c")["status"]=="unverified"
    assert all(row["status"]!="verified" for row in result["measured"])


@pytest.mark.parametrize("erase",[False,True])
def test_actual_ledger_chord_keeps_hollow_head_identity_and_rejects_erasure(tmp_path,erase):
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
    assert result["complete"] and len(result["measured"])==2
    assert all(row["status"]=="verified" and row["glyph"]=="head_half" and row["match"]>=.79
               for row in result["measured"])
    if erase:
        picture=Image.open(tmp_path/"native-0.00000.png").convert("RGB")
        rail=detect_staff_lines(picture)["right"]
        bounds=reference_glyphs()["head_half"]["bounds"]
        width,height=(round(bounds[i]*rail.gap/250) for i in (2,3))
        x,y=(lower["joint_assignment"][k] for k in ("x","y"))
        ImageDraw.Draw(picture).rectangle((x,y,x+width-1,y+height-1),fill=picture.getpixel((10,10)))
        picture.save(tmp_path/"native-0.00000.png")
        changed=verify_all_notehead_pixels(xml,tmp_path,hand="right")
        assert next(row for row in changed["measured"] if row["source_id"]=="b5")["status"]!="verified"
        assert next(row for row in changed["measured"] if row["source_id"]=="b6")["status"]=="verified"
        assert not changed["complete"]


def _dense_chord_frame(tmp_path, *, omit=None, move=None, gap=20, kind="quarter",
                       move_steps=1, upper_step="D"):
    """Explicit MusicXML and glyph pixels; no native model or reported geometry."""
    xml=f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="c"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>{kind}</type></note>
    <note id="d"><chord/><pitch><step>{upper_step}</step><octave>5</octave></pitch><duration>1</duration><type>{kind}</type></note>
    </measure></part></score-partwise>'''
    image=Image.new("RGBA",(1536,520),(16,41,35,255))
    draw=ImageDraw.Draw(image)
    for base in (120,320):
        for i in range(5):
            draw.line((0,base+i*gap,1535,base+i*gap),fill=(73,83,77))
    staff=RasterStaff("right",tuple(120+i*gap for i in range(5)),gap)
    spec=native_glyphs()["head_half" if kind=="half" else "head_black"]
    b=spec["bounds"]
    w,h=round(b[2]*gap/250),round(b[3]*gap/250)
    mask=Image.open(BytesIO(cairosvg.svg2png(bytestring=spec["svg"].encode(),
        output_width=w,output_height=h))).convert("RGBA")
    for step,dx in (("C",0),(upper_step,round(w*.96) if upper_step=="D" else 0)):
        if step==omit:
            continue
        y=expected_y(staff,(step,0,5),("G",2,0))
        if step==move:
            y+=move_steps*gap/2
        image.alpha_composite(mask,(round(1536*.42)-w//2+dx,round(y+b[1]*gap/250)))
    image.convert("RGB").save(tmp_path/"native-0.00000.png")
    return xml


@pytest.mark.parametrize("gap",[8,20])
@pytest.mark.parametrize("kind",["quarter","half"])
def test_distinguishable_adjacent_heads_receive_joint_pixel_credit(tmp_path,gap,kind):
    xml=_dense_chord_frame(tmp_path,gap=gap,kind=kind)
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert result["complete"],result["measured"]
    assert result["coverage"]["verified"]==2


@pytest.mark.parametrize("omit",["C","D"])
@pytest.mark.parametrize("gap",[8,20])
@pytest.mark.parametrize("kind",["quarter","half"])
def test_missing_adjacent_head_cannot_borrow_its_neighbor(tmp_path,omit,gap,kind):
    xml=_dense_chord_frame(tmp_path,omit=omit,gap=gap,kind=kind)
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert not result["complete"]
    assert not result["passed"]
    assert result["coverage"]["verified"]==0
    missing=next(row for row in result["measured"] if row["spelling"]==(omit,0,5))
    assert missing["status"]=="unverified"


def test_overlapping_registration_envelopes_cannot_hide_a_preexisting_missing_head_failure(tmp_path):
    xml=_dense_chord_frame(tmp_path,upper_step="F",omit="C")
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert not result["passed"]
    missing=next(row for row in result["measured"] if row["source_id"]=="c")
    assert missing["match"]==0
    assert missing["status"]=="unverified"
    assert result["failures"]


@pytest.mark.parametrize("move",["C","D"])
@pytest.mark.parametrize("gap",[8,20])
@pytest.mark.parametrize("direction",[-1,1])
@pytest.mark.parametrize("kind",["quarter","half"])
def test_joint_assignment_rejects_one_step_adjacent_head_mutation(tmp_path,move,gap,direction,kind):
    xml=_dense_chord_frame(tmp_path,move=move,gap=gap,move_steps=direction,kind=kind)
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert not result["complete"]
    assert result["coverage"]["verified"]==0


@pytest.mark.parametrize("gap",[8,20])
def test_one_midpoint_head_cannot_satisfy_two_source_pitches_with_passing_local_matches(tmp_path,gap):
    xml=_dense_chord_frame(tmp_path,omit="D",move="C",move_steps=-.5,gap=gap)
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert all(row["match"]>=.79 for row in result["measured"])
    assert result["coverage"]["verified"]==0
    assert result["coverage"]["ambiguous"]==2
    assert not result["complete"]


@pytest.mark.parametrize("kind",["quarter","half"])
@pytest.mark.parametrize("gap",[8,20])
def test_shared_unison_next_to_a_distinct_head_stays_ambiguous(tmp_path,kind,gap):
    from copy import deepcopy
    from xml.etree import ElementTree as ET

    root=ET.fromstring(_dense_chord_frame(tmp_path,kind=kind,gap=gap))
    measure=root.find("part/measure")
    duplicate=deepcopy(measure.find("note"))
    duplicate.set("id","c-second-voice")
    ET.SubElement(duplicate,"voice").text="2"
    ET.SubElement(ET.SubElement(measure,"backup"),"duration").text="1"
    measure.append(duplicate)
    result=verify_all_notehead_pixels(ET.tostring(root,encoding="unicode"),tmp_path)
    unisons=[row for row in result["measured"] if row["spelling"]==("C",0,5)]
    assert len(unisons)==2
    assert all(row["status"]=="ambiguous" for row in unisons)
    assert result["coverage"]["expected"]==3
    assert result["coverage"]["verified"]==0
    assert not result["complete"]


@pytest.mark.parametrize("step",["C","E","G"])
def test_retained_dense_chord_cannot_borrow_an_erased_heads_neighbors(tmp_path,step):
    import numpy as np
    import shutil
    from piano_teacher.notation.pixel_proof import detect_staff_lines
    from piano_teacher.notation.symbol_pixel_proof import bright

    fixture=Path(__file__).parent/"fixtures"
    image=Image.open(fixture/"native_dense_whole_chord.png").convert("RGB")
    staff=detect_staff_lines(image)["right"]
    target=expected_y(staff,(step,0,4),("G",2,0))
    # Erase the selected head's central ink band only. Neighbor head centres
    # lie one gap away, outside this mutation. Dim rails/playhead are kept.
    pixels=np.asarray(image).copy()
    erase=np.zeros(pixels.shape[:2],dtype=bool)
    x=round(image.width*.42)
    erase[round(target-.35*staff.gap):round(target+.35*staff.gap),
          x-round(2*staff.gap):x+round(2*staff.gap)]=True
    pixels[erase & bright(image)]=(16,41,35)
    Image.fromarray(pixels).save(tmp_path/"native-0.00000.png")
    shutil.copy(fixture/"native_dense_half_chord.png",tmp_path/"native-4.00000.png")
    xml=(fixture/"musical_fidelity/xml_chord_ties.musicxml").read_text()
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert not any(row['status']=='verified' for row in result['measured'] if row['beat']==0)
    assert all(row['status']=='verified' for row in result['measured'] if row['beat']==4)
    assert not result["complete"]
    assert not result["passed"]
    erased=next(row for row in result["measured"] if row["beat"]==0 and row["spelling"]==(step,0,4))
    assert erased["status"]=="unverified"


def test_retained_authored_whole_chord_is_jointly_verified_from_original_musicxml(tmp_path):
    import shutil

    # Unmodified protocol-2 capture from phase3-report-10-both,
    # xml_chord_ties/measures-001-002/native-{0,4}.00000.png. The unchanged
    # original XML supplies all expectations; no generated model is read.
    shutil.copy(Path(__file__).parent/"fixtures/native_dense_whole_chord.png",
                tmp_path/"native-0.00000.png")
    shutil.copy(Path(__file__).parent/"fixtures/native_dense_half_chord.png",
                tmp_path/"native-4.00000.png")
    xml=(Path(__file__).parent/"fixtures/musical_fidelity/xml_chord_ties.musicxml").read_text()
    result=verify_all_notehead_pixels(xml,tmp_path)
    assert result['passed'] and result['complete']
    assert result['coverage']['verified']==6
    assert all(row['status']=='verified' for row in result['measured'])
    assert all(row['match']>=.79 for row in result['measured'])
