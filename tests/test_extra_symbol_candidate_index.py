"""Dense-frame candidate index must implement the original exact NMS oracle.

Coverage may not improve by dropping a source glyph, changing overlap/Dice,
or ignoring a full-frame resource overrun. We compare exhaustive NMS to the
same-family cell index at realistic densities and at cell boundaries.
"""
import random

import pytest

from piano_teacher.notation.extra_symbol_pixels import (
    _distinct_candidates, _overlap, MAX_CANDIDATES,
)


def exhaustive(rows):
    accepted = []
    for row in sorted(rows, key=lambda item: -item["score"]):
        box = row["bbox"]
        if any(row["family"] == other["family"]
               and _overlap(box, other["bbox"]) >
               .65*min((box[2]-box[0])*(box[3]-box[1]),
                       (other["bbox"][2]-other["bbox"][0]) *
                       (other["bbox"][3]-other["bbox"][1]))
               for other in accepted):
            continue
        accepted.append(row)
    return accepted


def rect(x, y, width=18, height=12, family="head", score=.9):
    return {"family":family, "bbox":[x,y,x+width,y+height], "score":score}


@pytest.mark.parametrize("seed", [1, 3, 7, 11])
def test_spatial_candidate_index_is_exact_exhaustive_nms(seed):
    rng = random.Random(seed)
    rows = [
        rect(rng.randrange(-30, 1460), rng.randrange(-30, 510),
             rng.randrange(2, 110), rng.randrange(2, 70),
             rng.choice(("head", "rest", "flag", "dot")),
             rng.randrange(79, 100)/100)
        for _ in range(650)
    ]
    assert _distinct_candidates(rows, limit=2048) == exhaustive(rows)


def test_cell_boundary_and_equal_score_order_remain_exact():
    rows = [
        rect(63,63,2,2,score=.9),
        rect(64,64,2,2,score=.9),
        rect(62,62,4,4,score=.9),
        rect(63,63,2,2,family="rest",score=.9),
        rect(-1,-1,4,4,score=.9),
        rect(0,0,4,4,score=.9),
        rect(127,64,3,2,score=.9),
        rect(128,64,3,2,score=.9),
    ]
    assert _distinct_candidates(rows, limit=2048) == exhaustive(rows)


def test_dense_full_frame_stays_source_complete_beyond_old_256_limit():
    rows = [rect((i%35)*42,(i//35)*24,score=.9)
            for i in range(750)]
    assert len(_distinct_candidates(rows)) == len(rows) == 750
    assert MAX_CANDIDATES >= 750


def test_the_budget_still_fails_closed_not_truncate_the_tail():
    rows = [rect(i*42,0) for i in range(5)]
    with pytest.raises(ValueError, match="Family candidate budget exceeded"):
        _distinct_candidates(rows, limit=4)
    with pytest.raises(ValueError, match="must be positive"):
        _distinct_candidates(rows, limit=0)


def test_damaged_distinct_glyph_remains_in_the_inventory():
    rows = [rect(i*40,0,score=.91) for i in range(30)]
    extra = rect(17*40,19,score=.80,family="flag")
    rows.append(extra)
    accepted = _distinct_candidates(rows, limit=100)
    assert extra in accepted
    assert accepted == exhaustive(rows)


def test_partial_bass_clef_pair_requires_curved_ink_not_just_two_dots():
    import math
    import numpy as np
    from types import SimpleNamespace
    from piano_teacher.notation.extra_symbol_pixels import _partial_bass_clef_dot_tracks

    rail=SimpleNamespace(gap=22.,lines=(314.5,336.5,358.5,380.5,402.5))
    ink=np.zeros((520,1536),dtype=bool)
    for y in range(315,381):
        x=round(36+12*math.sin(math.pi*(y-315)/66))
        ink[y,x:x+5]=True
    photo=dict(head_pixels=ink,staves={'left':rail})
    upper=dict(name='augmentation_dot',family='dot',bbox=[63,319,76,333],track=4)
    lower=dict(name='augmentation_dot',family='dot',bbox=[63,340,76,354],track=5)
    source=SimpleNamespace(clefs=[(0,'left','F',4,0)])
    assert _partial_bass_clef_dot_tracks(photo,[upper,lower],source)=={4,5}
    assert not _partial_bass_clef_dot_tracks(photo,[upper],source)
    assert not _partial_bass_clef_dot_tracks(photo,[upper,lower],SimpleNamespace(clefs=[]))
    assert not _partial_bass_clef_dot_tracks(dict(photo,head_pixels=np.zeros_like(ink)),[upper,lower],source)
    straight=np.zeros_like(ink)
    straight[315:381,40:45]=True
    assert not _partial_bass_clef_dot_tracks(dict(photo,head_pixels=straight),[upper,lower],source)
    detached=dict(lower,bbox=[98,340,111,354],track=6)
    assert not _partial_bass_clef_dot_tracks(photo,[upper,detached],source)
