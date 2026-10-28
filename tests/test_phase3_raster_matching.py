"""Vectorized matching must preserve the scalar oracle and its thresholds."""
import math
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


def _head_pixels(heads, *, gap=20):
    """Place authentic outline ink at explicit test positions, without a renderer."""
    from piano_teacher.notation.pixel_ink import rasterize_outline

    pixels=np.zeros((180,200),dtype=bool)
    for name,x,y in heads:
        spec=reference_glyphs()[name]
        b=spec["bounds"]
        w,h=round(b[2]*gap/250),round(b[3]*gap/250)
        pixels[y:y+h,x:x+w] |= rasterize_outline(spec["svg"],w,h)
    return pixels


def _request(name, y, *, dxs=range(-32,33), gap=20):
    return dict(glyph=reference_glyphs()[name],origin_y=y,dxs=dxs,gap=gap)


def test_joint_assignment_certifies_distinct_heads_with_disjoint_ink():
    pixels=_head_pixels([("head_black",86,48),("head_black",112,58)])
    result=raster_matching.match_glyphs_joint(pixels,[
        _request("head_black",60),_request("head_black",70)],100,dys=range(-4,5))
    assert result is not None
    assert all(row["score"]>=.79 for row in result)
    assert result[0]["support"].isdisjoint(result[1]["support"])


def test_joint_assignment_cannot_count_one_head_twice_even_when_both_local_matches_pass():
    pixels=_head_pixels([("head_black",86,48)])
    requests=[_request("head_black",59),_request("head_black",61)]
    assert all(raster_matching.match_glyph(pixels,r["glyph"],20,100,r["origin_y"],
        centered=True,dxs=r["dxs"],dys=range(-4,5))>=.79 for r in requests)
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=range(-4,5)) is None


def test_unrelated_head_surplus_cannot_pay_touching_heads_pixel_capacity():
    # Two touching source requests compete for one small physical head. An
    # unrelated large head contributes enough total ink to pass a global
    # pixel-count check, but none of that ink belongs to the small requests.
    pixels = (_head_pixels([("head_black", 60, 48)], gap=12) |
              _head_pixels([("head_black", 120, 40)], gap=40))
    b = reference_glyphs()["head_black"]["bounds"]
    small_y = 48-b[1]*12/250
    large_y = 40-b[1]*40/250
    large_dx = round(120-(100-b[2]*40/500))
    requests = [
        dict(_request("head_black", small_y, gap=12, dxs=range(-34, -29)), dys=range(-1, 2)),
        dict(_request("head_black", small_y+.5, gap=12, dxs=range(-34, -29)), dys=range(-1, 2)),
        dict(_request("head_black", large_y, gap=40, dxs=(large_dx,)), dys=(0,)),
    ]
    candidates = [raster_matching._joint_candidates(pixels, request, 100, (0,), .79)
                  for request in requests]
    # The large head is assigned first (one candidate). Insufficient capacity
    # in the touching subset must still reject the complete assignment.
    assert len(candidates[2]) == 1 < min(map(len, candidates[:2]))
    best = [rows[0] for rows in candidates]
    assert all(row["score"] >= .79 for row in best)
    required = [math.ceil(.79*row["denominator"]/2) for row in best]
    assert len(set().union(*(row["support"] for row in best))) >= sum(required)
    assert len(best[0]["support"] | best[1]["support"]) < sum(required[:2])
    assert raster_matching.match_glyphs_joint(pixels, requests, 100, dys=(0,)) is None


@pytest.mark.parametrize("erased",[0,1])
def test_joint_assignment_rejects_a_missing_adjacent_head(erased):
    heads=[("head_black",86,48),("head_black",112,58)]
    pixels=_head_pixels([head for i,head in enumerate(heads) if i!=erased])
    assert raster_matching.match_glyphs_joint(pixels,[
        _request("head_black",60),_request("head_black",70)],100,dys=range(-4,5)) is None


def test_joint_assignment_backtracks_from_a_better_but_conflicting_local_candidate():
    pixels=_head_pixels([("head_black",60,48),("head_black",112,48)])
    result=raster_matching.match_glyphs_joint(pixels,[
        _request("head_black",60,dxs=range(-32,33)),
        _request("head_black",61,dxs=range(-32,-9))],100,dys=range(-4,5))
    assert result is not None
    assert result[0]["x"]>100 and result[1]["x"]<80
    assert result[0]["support"].isdisjoint(result[1]["support"])


def test_joint_assignment_fails_closed_when_search_budget_is_exhausted():
    pixels=_head_pixels([("head_black",60,48),("head_black",112,48)])
    requests=[_request("head_black",60),_request("head_black",61)]
    assert raster_matching.match_glyphs_joint(pixels,requests,100,
        dys=range(-4,5),max_search_nodes=1) is None


def test_joint_assignment_has_an_explicit_head_count_bound():
    pixels=_head_pixels([("head_black",86,10+20*i) for i in range(7)])
    requests=[_request("head_black",22+20*i,dxs=(0,)) for i in range(7)]
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=(0,)) is None
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=(0,),max_heads=7) is not None


def test_joint_assignment_preserves_each_staffs_own_registration_range():
    pixels=_head_pixels([("head_black",86,55),("head_black",112,78)])
    requests=[dict(_request("head_black",60),dys=(0,)),
              _request("head_black",90)]
    # A larger global range cannot expand the first staff's source lane.
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=range(-4,5)) is None


def test_search_components_include_full_registration_envelopes():
    requests=[_request("head_black",60),_request("head_half",90),
              _request("head_whole",150)]
    assert raster_matching.glyph_search_components(requests,dys=range(-4,5))==[[0,1],[2]]


def test_joint_assignment_requires_the_unchanged_shape_score_after_shared_ink_is_discarded():
    pixels=_head_pixels([("head_black",86,48),("head_black",86,52)])
    requests=[_request("head_black",60),_request("head_black",64)]
    assert all(raster_matching.match_glyph(pixels,r["glyph"],20,100,r["origin_y"],
        centered=True,dxs=r["dxs"],dys=range(-4,5))>=.79 for r in requests)
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=range(-4,5)) is None


@pytest.mark.parametrize('erased', [None, 0, 2, 4])
def test_five_head_capacity_keeps_legitimate_ink_and_rejects_head_erasures(erased):
    positions=[('head_black',86,18),('head_black',112,28),
               ('head_black',86,68),('head_black',112,78),
               ('head_black',86,128)]
    pixels=_head_pixels([row for i,row in enumerate(positions) if i!=erased])
    requests=[_request('head_black',y) for y in (30,40,80,90,140)]
    result=raster_matching.match_glyphs_joint(pixels,requests,100,dys=range(-4,5))
    if erased is not None:
        assert result is None
    else:
        assert result is not None
        owned=set()
        for row in result:
            assert row['score']>=.79
            assert owned.isdisjoint(row['support'])
            owned.update(row['support'])


def test_ownership_work_exhaustion_cannot_return_partial_head_credit():
    pixels=_head_pixels([('head_black',86,48),('head_black',112,58)])
    requests=[_request('head_black',60),_request('head_black',70)]
    assert raster_matching.match_glyphs_joint(pixels,requests,100,dys=range(-4,5)) is not None
    diagnostic={}
    assert raster_matching.match_glyphs_joint(pixels,requests,100,
        dys=range(-4,5),max_assignment_work=1,diagnostics=diagnostic) is None
    assert diagnostic['exhausted']


def test_excessive_candidate_envelope_fails_before_allocating_image_windows():
    pixels=_head_pixels([('head_black',86,48)])
    diagnostic={}
    result=raster_matching.match_glyphs_joint(pixels,
        [_request('head_black',60,dxs=range(-1000000,1000001))],100,
        dys=range(-4,5),diagnostics=diagnostic)
    assert result is None and diagnostic['exhausted']
