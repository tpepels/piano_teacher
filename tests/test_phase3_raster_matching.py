"""Vectorized matching must preserve the scalar oracle and its thresholds."""
import numpy as np
import pytest

from piano_teacher.notation import raster_matching
from piano_teacher.notation.reference_font import reference_glyphs
from piano_teacher.notation.symbol_pixel_proof import _match_glyph


@pytest.mark.parametrize("glyph",["head_black","head_half","rest_quarter"])
@pytest.mark.parametrize("x,y",[(50,60),(0,0),(99,119)])
def test_vectorized_glyph_match_equals_original_scalar_pixel_comparison(glyph,x,y):
    pixels=np.random.default_rng(19).random((120,100))>.35
    spec=reference_glyphs()[glyph]
    options=dict(centered=True,dxs=range(-4,5),dys=range(-3,4))
    expected=_match_glyph(pixels,spec,12,x,y,**options)
    assert raster_matching.match_glyph(pixels,spec,12,x,y,**options)==pytest.approx(expected)
