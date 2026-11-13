"""Beam profiles must distinguish actual antialias edge ink from damage.

A missing pixel is never reconstructed from the MusicXML beam level or native
geometry. Only photographed subthreshold RGB at exactly that location, bounded
by full-bright continuous contour above and below, can join a split beam run.
"""
import numpy as np

from piano_teacher.notation.connector_pixels import _photographed_beam_runs


def _frame():
    pixels = np.zeros((50, 9), dtype=bool)
    edge = np.zeros_like(pixels)
    pixels[5:16, 4] = True
    pixels[22:33, 4] = True
    edge[:] = pixels
    return dict(pixels=pixels, beam_edge=edge)


def test_antialiased_single_pixel_keeps_one_photographed_beam():
    frame = _frame()
    frame["pixels"][10, 4] = False
    frame["beam_edge"][10, 4] = True
    assert _photographed_beam_runs(frame, 0, 40, 4) == [(5, 16), (22, 33)]


def test_erased_single_pixel_is_not_invented():
    frame = _frame()
    frame["pixels"][10, 4] = False
    frame["beam_edge"][10, 4] = False
    assert _photographed_beam_runs(frame, 0, 40, 4) == [
        (5, 10), (11, 16), (22, 33)]


def test_two_pixel_gap_is_never_bridged_even_if_faint():
    frame = _frame()
    frame["pixels"][9:11, 4] = False
    frame["beam_edge"][9:11, 4] = True
    assert _photographed_beam_runs(frame, 0, 40, 4) == [
        (5, 9), (11, 16), (22, 33)]


def test_faint_unbounded_ink_cannot_create_new_beam():
    frame = _frame()
    frame["beam_edge"][16:22, 4] = True
    frame["beam_edge"][35:39, 4] = True
    assert _photographed_beam_runs(frame, 0, 40, 4) == [
        (5, 16), (22, 33)]


def test_entire_erased_column_has_no_beam_witness():
    frame = _frame()
    frame["pixels"][:, 4] = False
    frame["beam_edge"][:, 4] = False
    assert _photographed_beam_runs(frame, 0, 40, 4) == []


def test_clipped_registered_beam_endpoints_cannot_be_called_missing_stems():
    from piano_teacher.notation.connector_pixels import _full_beam_head_visible
    # Original Chopin bar 14 at beat 7.65: a partially visible head is
    # registered at x=28, while its stem lies outside production clipping.
    assert not _full_beam_head_visible({"bbox": [21, 153, 36, 166]}, 1536)
    assert _full_beam_head_visible({"bbox": [29, 153, 45, 166]}, 1536)
    assert _full_beam_head_visible({"bbox": [35, 153, 49, 166]}, 1536)
    assert not _full_beam_head_visible({"bbox": [1508, 153, 1520, 166]}, 1536)
    # The absence of a complete endpoint must stay unavailable: the beam
    # verifier is forbidden to award positive proof for any partial glyph.



def test_detached_real_tuplet_bracket_is_not_invented_fourth_beam():
    """Actual separate bracket ink must not defeat a correct source beam."""
    from piano_teacher.notation.connector_pixels import (
        _connected_source_beam_runs, _photographed_beam_runs)
    pixels = np.zeros((260, 600), dtype=bool)
    for start, end in ((198, 204), (207, 212), (215, 220)):
        pixels[start:end, 430:501] = True
    # Real physical shaft joins source levels.
    pixels[198:220, 430] = True
    pixels[198:220, 500] = True
    # Real tuplet bracket endpoint is bright but physically detached.
    pixels[224:232, 438:461] = True
    frame = {"pixels": pixels}
    observed = _photographed_beam_runs(frame, 190, 240, 438)
    assert observed == [(198, 204), (207, 212), (215, 220), (224, 232)]
    stems = [{"x": 430., "top": 198, "bottom": 250},
             {"x": 500., "top": 198, "bottom": 250}]
    owned = _connected_source_beam_runs(frame, observed, x=438,
                                         tip=198., stems=stems, gap=11.)
    assert owned == observed[:3]
    # A counterfeit fourth-level stroke genuinely connected to the
    # source's printed stem/beam must still trigger a mismatch.
    pixels[219:225, 460] = True
    owned = _connected_source_beam_runs(frame, observed, x=438,
                                         tip=198., stems=stems, gap=11.)
    assert owned == observed
    # A truly deleted second beam remains missing, never reconstituted.
    pixels[207:212, 430:501] = False
    remaining = _photographed_beam_runs(frame, 190, 240, 438)
    assert (207, 212) not in remaining



def test_real_subdued_antialias_stem_connects_actual_head_to_source_beam():
    """Chopin bar 14 has measured 144/159/155 shaft pixels, not white."""
    import pytest
    from piano_teacher.notation.connector_pixels import _stem
    bright = np.zeros((75, 75), dtype=bool)
    edge = np.zeros_like(bright)
    bright[20:24, 30] = True       # exact pale notehead attachment
    bright[39:47, 30] = True       # exact pale beam attachment
    edge[20:47, 30] = True         # continuously photographed gray shaft
    anchors = [{"x": 35., "y": 21., "gap": 10.}]
    with pytest.raises(ValueError, match="absent"):
        _stem(bright, anchors, False)
    stem = _stem(bright, anchors, False, edge=edge)
    assert stem["top"] == 20 and stem["bottom"] == 47
    assert stem["x"] == 30.

    # A genuinely erased multi-pixel gap in both photographic masks
    # remains a failure. No source-interpolated stem may bridge it.
    edge[30:35, 30] = False
    with pytest.raises(ValueError, match="absent"):
        _stem(bright, anchors, False, edge=edge)

    # A broad unrelated polygon is not accepted as a thin stem.
    edge[20:47, 27:33] = True
    with pytest.raises(ValueError, match="too broad"):
        _stem(bright, anchors, False, edge=edge)
