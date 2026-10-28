"""Subpixel reference sampling must preserve genuine thin connector ink."""
import numpy as np
from piano_teacher.notation.connector_pixels import _bracket_mask, _fit_bracket, _bracket_topology


def test_joint_bracket_registration_requires_complete_hooks():
    mask = np.zeros((17, 100), dtype=bool)
    mask[:2] = True
    mask[:, :2] = mask[:, -2:] = True
    pixels = np.zeros((40, 130), dtype=bool)
    pixels[10:27, 11:111] = mask
    numeral = np.zeros((1, 1), dtype=bool)
    number_box = [59, 30, 60, 31]
    _, x, y, _ = _fit_bracket(pixels, mask, [10, 10, 110, 27], numeral, number_box, 10)
    assert _bracket_topology(pixels, mask, x, y, number_box, 10) is None
    pixels[13:27, 109:111] = False
    _, x, y, _ = _fit_bracket(pixels, mask, [10, 10, 110, 27], numeral, number_box, 10)
    assert _bracket_topology(pixels, mask, x, y, number_box, 10) is not None
