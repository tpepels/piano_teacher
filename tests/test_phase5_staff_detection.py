"""Image-only staff rails must survive long ties without inventing missing ink.

The PNG fixture is the unmodified native Clair_de_Lune capture at beat 8.5:
phase3-report-3-both/raw/measures-001-004/native-8.50000.png. Its bytes have SHA256
5993de8f942ab91d39a983d9be2a7a1720116a1c26ea7c4f65c00f3bf888b5c0.
No renderer metadata or detector-produced coordinates define expectations.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.pixel_proof import detect_staff_lines


BACKGROUND = (16, 41, 35)
RAIL = (73, 83, 77)
RAILS = (143, 165, 187, 209, 231, 315, 337, 359, 381, 403)


def _frame(*, ties=False):
    image = Image.new("RGB", (1536, 520), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for y in RAILS:
        draw.line((0, y, 1535, y), fill=RAIL)
    if ties:
        # Long shallow curves meet the fourth rail at their endpoints and
        # cover both sets of peripheral columns near its +4px shoulder.
        # A second tie reproduces the nearby lower contour. Their geometry
        # is literal synthetic input, independent of the detector.
        for offset in (0, 12):
            for x0, x1, peak, scale in (
                (0, 640, 200, 440), (1020, 1535, 1500, 480)
            ):
                points = [
                    (x, 381 + offset + round(5 * (1 - ((x - peak) / scale) ** 2)))
                    for x in range(x0, x1 + 1)
                ]
                draw.line(points, fill=(230, 240, 234), width=3)
    return image


def test_long_curved_ties_touching_a_rail_do_not_shift_staff_positions():
    staves = detect_staff_lines(_frame(ties=True))
    assert staves["right"].lines == (143, 165, 187, 209, 231)
    assert staves["left"].lines == (315, 337, 359, 381, 403)
    assert staves["right"].gap == staves["left"].gap == 22


@pytest.mark.parametrize("mutation", ("erase", "move"))
def test_ties_cannot_replace_an_erased_or_moved_real_rule(mutation):
    image = _frame(ties=True)
    pixels = np.array(image)
    mask = np.all(pixels[381] == RAIL, axis=1)
    assert int(mask.sum()) > 1000
    pixels[381, mask] = BACKGROUND
    if mutation == "move":
        pixels[387, mask] = RAIL
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(Image.fromarray(pixels))


@pytest.mark.parametrize("rows", (
    (80, 88, 96, 104, 112, 250, 258, 266, 274, 282),
    (80, 112, 144, 176, 208, 300, 332, 364, 396, 428),
))
def test_existing_staff_gap_boundaries_keep_literal_positions(rows):
    image = Image.new("RGB", (1536, 520), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for y in rows:
        draw.line((0, y, 1535, y), fill=RAIL)
    staves = detect_staff_lines(image)
    assert staves["right"].lines == rows[:5]
    assert staves["left"].lines == rows[5:]


@pytest.mark.parametrize("lower", (
    (315, 322, 329, 336, 343),  # 7px, below the permitted interval
    (280, 313, 346, 379, 412),  # 33px, above the permitted interval
    (315, 337, 359, 387, 403),  # one displaced line, invalid local spacing
))
def test_wrong_staff_spacing_is_not_repaired_from_a_lattice(lower):
    image = Image.new("RGB", (1536, 520), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for y in (143, 165, 187, 209, 231) + lower:
        draw.line((0, y, 1535, y), fill=RAIL)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


def test_regular_edge_fragments_cannot_supply_the_missing_viewport_rail():
    image = _frame()
    draw = ImageDraw.Draw(image)
    # Leave aligned gray fragments at both edges, but erase most of the real
    # rail. Peripheral sampling alone mistakes these fragments for a rule.
    draw.line((160, 381, 1370, 381), fill=BACKGROUND)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


@pytest.mark.parametrize("amplitude", (0, 1, 2, 3, 4, 5, 8))
def test_shallow_viewport_tie_cannot_replace_a_missing_gray_rule(amplitude):
    image = _frame()
    draw = ImageDraw.Draw(image)
    draw.line((0, 381, 1535, 381), fill=BACKGROUND)
    draw.line([(x, 381 + round(amplitude * ((x - 768) / 768) ** 2))
               for x in range(1536)], fill=(230, 240, 234), width=3)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


def test_antialiased_bright_tie_cannot_hide_behind_a_weak_row_peak():
    image = _frame()
    ImageDraw.Draw(image).line((0, 381, 1535, 381), fill=BACKGROUND)
    # A real synthetic stroke at 4x resolution, then coverage antialiasing.
    # The reduced row profile sees a faint edge; the actual 2D stroke is bright.
    tie = Image.new("RGBA", (6144, 2080))
    ImageDraw.Draw(tie).line([
        (x, round(4 * (381 + 3.75 * ((x / 4 - 768) / 768) ** 2)))
        for x in range(6144)
    ], fill=(230, 240, 234, 255), width=8)
    tie = tie.resize(image.size, Image.Resampling.LANCZOS)
    image.paste(tie, mask=tie.getchannel("A"))
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


def test_a_majority_of_bright_curves_cannot_define_the_gray_rule_reference():
    image = _frame()
    draw = ImageDraw.Draw(image)
    for y in (231, 315, 337, 359, 381, 403):
        draw.line((0, y, 1535, y), fill=BACKGROUND)
        draw.line([(x, y + round(3 * ((x - 768) / 768) ** 2))
                   for x in range(1536)], fill=(230, 240, 234), width=3)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


@pytest.mark.parametrize('both_staves', (False, True))
@pytest.mark.parametrize('color', ((230, 240, 234), RAIL))
def test_replacing_every_rule_with_equal_curves_cannot_certify_a_staff(both_staves, color):
    image = _frame()
    draw = ImageDraw.Draw(image)
    for y in RAILS if both_staves else RAILS[5:]:
        draw.line((0, y, 1535, y), fill=BACKGROUND)
        draw.line([(x, y + round(3 * ((x - 768) / 768) ** 2))
                   for x in range(1536)], fill=color, width=3)
    with pytest.raises(AssertionError, match='staff'):
        detect_staff_lines(image)


@pytest.mark.parametrize('both_staves', (False, True))
@pytest.mark.parametrize('color', ((230, 240, 234), RAIL))
@pytest.mark.parametrize('width,taper', ((1, 0), (2, 0), (3, 1), (3, 8)))
def test_thin_or_tapered_curves_cannot_supply_horizontal_staff_evidence(both_staves, color, width, taper):
    image = _frame()
    draw = ImageDraw.Draw(image)
    for y in RAILS if both_staves else RAILS[5:]:
        draw.line((0, y, 1535, y), fill=BACKGROUND)
        points = [(x, y + round(3 * ((x - 768) / 768) ** 2)) for x in range(1536)]
        draw.line(points, fill=tuple(v - taper for v in color), width=width)
        if taper:
            draw.line(points, fill=color, width=1)
    with pytest.raises(AssertionError, match='staff'):
        detect_staff_lines(image)


def test_same_gray_curved_stroke_is_not_a_straight_thin_rule():
    image = _frame()
    draw = ImageDraw.Draw(image)
    draw.line((0, 381, 1535, 381), fill=BACKGROUND)
    draw.line([(x, 381 + round(3 * ((x - 768) / 768) ** 2))
               for x in range(1536)], fill=RAIL, width=3)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


def test_gray_rule_split_over_two_antialiased_rows_is_still_measured():
    image = _frame()
    draw = ImageDraw.Draw(image)
    # Equal total contrast: 83-41 == 2*(62-41). The nine split gray rules
    # and one unsplit rule must agree despite different peak brightness.
    for y in (143, 165, 187, 209, 231, 315, 337, 359, 403):
        draw.line((0, y, 1535, y), fill=(45, 62, 56))
        draw.line((0, y + 1, 1535, y + 1), fill=(45, 62, 56))
    staves = detect_staff_lines(image)
    assert staves["right"].lines == (143.5, 165.5, 187.5, 209.5, 231.5)
    assert staves["left"].lines == (315.5, 337.5, 359.5, 381, 403.5)


def test_flat_notehead_columns_do_not_count_as_zero_weight_gray_rules():
    image = _frame()
    draw = ImageDraw.Draw(image)
    # Dense heads cover more than one quarter of an edge region, completely
    # hiding vertical contrast there. The exposed gray rail remains visible.
    for x in range(30, 370, 25):
        draw.rectangle((x, 160, x + 14, 170), fill=(230, 240, 234))
    staves = detect_staff_lines(image)
    assert staves["right"].lines == (143, 165, 187, 209, 231)
    assert staves["left"].lines == (315, 337, 359, 381, 403)


@pytest.mark.parametrize("rows", (
    (80, 88, 96, 104, 112, 250, 258, 266, 274, 282),
    (80, 92, 104, 116, 128, 250, 262, 274, 286, 298),
    (80, 102, 124, 146, 168, 300, 322, 344, 366, 388),
    (80, 112, 144, 176, 208, 300, 332, 364, 396, 428),
))
@pytest.mark.parametrize("phase", (0, .25, .5, .75))
def test_gap_and_subpixel_phase_allow_one_or_two_level_rounding(rows, phase):
    pixels = np.empty((520, 1536, 3), dtype=np.uint8)
    pixels[:] = BACKGROUND
    # Area coverage of literal thin rectangles, with independent 8-bit
    # rounding. Different gray levels model a 1-2 unit quantization difference
    # in otherwise legitimate rules. No renderer positioning is consulted.
    for i, y in enumerate(rows):
        gray = np.array(RAIL) + (i % 3 - 1)
        center = y + phase
        for row in (y - 1, y, y + 1):
            coverage = max(0, min(row + .5, center + .5)
                           - max(row - .5, center - .5))
            if coverage:
                pixels[row] = np.rint(np.array(BACKGROUND)
                                      + coverage * (gray - BACKGROUND)).astype(np.uint8)
    staves = detect_staff_lines(Image.fromarray(pixels))
    assert staves["right"].lines == pytest.approx(tuple(y + phase for y in rows[:5]), abs=.5)
    assert staves["left"].lines == pytest.approx(tuple(y + phase for y in rows[5:]), abs=.5)
    assert staves["right"].gap == staves["left"].gap == rows[1] - rows[0]


def _asymmetric_frame(faint_hand):
    image = _frame()
    draw = ImageDraw.Draw(image)
    rows = (143, 165, 187, 209, 231) if faint_hand == "right" else (315, 337, 359, 381, 403)
    for y in rows:
        draw.line((0, y, 1535, y), fill=(35, 54, 48))
    return image


@pytest.mark.parametrize("faint_hand", ("right", "left"))
def test_active_and_inactive_staves_can_have_different_gray_ink(faint_hand):
    staves = detect_staff_lines(_asymmetric_frame(faint_hand))
    assert staves["right"].lines == (143, 165, 187, 209, 231)
    assert staves["left"].lines == (315, 337, 359, 381, 403)


@pytest.mark.parametrize("faint_hand", ("right", "left"))
@pytest.mark.parametrize("staff_y", (165, 381))
@pytest.mark.parametrize("mutation", ("erase", "move", "tie"))
def test_asymmetric_staff_still_requires_each_actual_gray_rule(faint_hand, staff_y, mutation):
    image = _asymmetric_frame(faint_hand)
    draw = ImageDraw.Draw(image)
    gray = image.getpixel((800, staff_y))
    draw.line((0, staff_y, 1535, staff_y), fill=BACKGROUND)
    if mutation == "move":
        draw.line((0, staff_y + 6, 1535, staff_y + 6), fill=gray)
    elif mutation == "tie":
        draw.line([(x, staff_y + round(3 * ((x - 768) / 768) ** 2))
                   for x in range(1536)], fill=(230, 240, 234), width=3)
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(image)


@pytest.mark.parametrize("size", ((1536, 520), (40, 520)))
def test_no_rail_evidence_is_a_failure(size):
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(Image.new("RGB", size, BACKGROUND))


def _native_frame():
    with Image.open(Path(__file__).parent / "fixtures/native_staff_tie_overlap.png") as image:
        return image.convert("RGB")


def test_actual_clair_de_lune_long_ties_preserve_the_ten_visible_gray_rails():
    staves = detect_staff_lines(_native_frame())
    # Manually inspected row centers in the supplied native raster, ~22px
    # apart. In particular the fourth bass rail is 380.5, not the tie at 384.5.
    assert staves["right"].lines == pytest.approx((143, 164.5, 186.5, 208.5, 230.5))
    assert staves["left"].lines == pytest.approx((314.5, 336.5, 358.5, 380.5, 402))


@pytest.mark.parametrize("mutation", ("erase", "move"))
def test_actual_gray_rail_ink_is_required_even_when_the_other_four_form_a_lattice(mutation):
    pixels = np.array(_native_frame())
    # The fourth bass rule's two real antialiased gray rows, sampled directly
    # from the PNG. Leave all foreground tie/note ink in place.
    for y, gray in ((380, (90, 107, 101)), (381, (41, 61, 55))):
        mask = np.all(pixels[y] == gray, axis=1)
        assert int(mask.sum()) > 1000
        pixels[y, mask] = (16, 37, 31)
        if mutation == "move":
            pixels[y + 6, mask] = gray
    with pytest.raises(AssertionError, match="staff"):
        detect_staff_lines(Image.fromarray(pixels))
