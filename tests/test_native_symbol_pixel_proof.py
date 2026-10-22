"""Mutation-test actual glyph pixel classification and beam/tie connectivity."""
import io
from PIL import Image, ImageDraw
import cairosvg
import pytest

from piano_teacher.notation.assets.glyphs import native_glyphs
from piano_teacher.notation.symbol_pixel_proof import (
    classify_symbol, REST_TYPES, ACCIDENTAL_GLYPH, bridge_ink,
)
FONT = native_glyphs()
GAP = 22


def _stamp(name, *, x=645, y=187, centered=True):
    base=Image.new("RGBA",(1536,520),(16,41,35,255))
    spec=FONT[name]
    bounds=spec["bounds"]
    width=max(1,round(bounds[2]*GAP/250))
    height=max(1,round(bounds[3]*GAP/250))
    svg=cairosvg.svg2png(bytestring=spec["svg"].encode(),
                         output_width=width,output_height=height)
    glyph=Image.open(io.BytesIO(svg)).convert("RGBA")
    left=round(x-(bounds[2]*GAP/250/2 if centered else -bounds[0]*GAP/250))
    top=round(y+bounds[1]*GAP/250)
    base.alpha_composite(glyph,(left,top))
    return base.convert("RGB")


@pytest.mark.parametrize("name",["rest_quarter","rest_eighth","rest_half","rest_whole"])
def test_written_rest_shape_is_identified_from_actual_pixels(name):
    image=_stamp(name)
    ranked=classify_symbol(image,FONT,tuple("rest_"+t for t in REST_TYPES),
                           645,187,GAP,centered=True,dxs=range(-3,4),
                           dys=range(-30,31,2))
    assert ranked[0][0]==name, ranked
    assert ranked[0][1] >= .72
    assert ranked[0][1]-ranked[1][1] >= .05


@pytest.mark.parametrize("name",["acc_sharp","acc_flat","acc_natural"])
def test_accidental_silhouette_is_identified_from_actual_pixels(name):
    image=_stamp(name,x=620,y=220)
    ranked=classify_symbol(image,FONT,tuple(ACCIDENTAL_GLYPH.values()),
                           620,220,GAP,centered=True,dxs=range(-9,10),
                           dys=range(-10,11,2))
    assert ranked[0][0]==name, ranked
    assert ranked[0][1] >= .72


def test_wrong_rest_silhouette_is_rejected():
    image=_stamp("rest_eighth")
    ranked=classify_symbol(image,FONT,("rest_quarter","rest_eighth"),
                           645,187,GAP,centered=True,dxs=range(-3,4),
                           dys=range(-30,31,2))
    assert ranked[0][0]=="rest_eighth"
    assert ranked[0][0]!="rest_quarter"


def test_erased_rest_cannot_be_identified():
    image=Image.new("RGB",(1536,520),(16,41,35))
    ranked=classify_symbol(image,FONT,("rest_quarter","rest_eighth"),
                           645,187,GAP,centered=True,dxs=range(-3,4),
                           dys=range(-30,31,2))
    assert ranked[0][1] == 0


def test_beam_tie_bridge_reacts_to_erased_real_image_ink():
    im=Image.new("RGB",(1536,520),(16,41,35))
    pen=ImageDraw.Draw(im)
    pen.rectangle((649,222,660,224),fill=(231,240,232))
    assert bridge_ink(im,range(216,232))==9
    pen.rectangle((649,222,660,224),fill=(16,41,35))
    assert bridge_ink(im,range(216,232))==0
