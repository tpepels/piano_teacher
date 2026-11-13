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
