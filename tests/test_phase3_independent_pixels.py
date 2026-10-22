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
                  omit: tuple[str, int] | None = None):
    score=read_written_score(SOURCE.read_text())
    font=native_glyphs()
    (tmp_path/"fixture.json").write_text(json.dumps({
        "assets":{"native_glyphs":font}
    }))
    width,height=1536,520
    staves={
        "right":RasterStaff("right",(120,140,160,180,200),20),
        "left":RasterStaff("left",(320,340,360,380,400),20),
    }
    clefs={"right":("G",2,0),"left":("F",4,0)}
    glyph=font["head_black"]
    bounds=glyph["bounds"]
    w=round(bounds[2]*20/250);h=round(bounds[3]*20/250)
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
                yy-=10  # one complete diatonic staff step
            x=round(width*.42)-w//2
            y=round(yy+bounds[1]*20/250)
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
