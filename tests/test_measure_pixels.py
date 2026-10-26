"""Physical rule widths: real retained failure plus isolated image controls."""
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


REAL = Path(__file__).parent / "fixtures/measure_pixels/ala30-rest-before-width-fix.png"
DPI_REAL = Path(__file__).parent / "fixtures/measure_pixels/source-rests-1600x1000-scale-1_25.png"
BACKGROUND = (25, 47, 48)
RAIL = (68, 91, 89)
INK = (165, 190, 185)


def picture(styles=("regular", "regular", "regular"), *, shifts=None):
    """Supplementary hand-authored rules, not replacement production goldens.

    Principal anchors are x=318,510,702: public origin 800*.42, 96px/beat,
    beats 0,2,4 and a single 18px clearance. Staff gap is 10 pixels.
    """
    image = Image.new("RGB", (800, 280), BACKGROUND)
    draw = ImageDraw.Draw(image)
    for y in (40, 50, 60, 70, 80, 170, 180, 190, 200, 210):
        draw.line((0, y, 799, y), fill=RAIL)
    draw.line((29, 40, 29, 210), fill=INK, width=2)  # Public system gutter.
    weights = {"regular": (1,), "heavy": (5,), "light-light": (1, 1),
               "light-heavy": (1, 5), "heavy-light": (5, 1), "heavy-heavy": (5, 5)}
    for i, style in enumerate(styles):
        x = (318, 510, 702)[i] + (shifts or {}).get(i, 0)
        widths = weights[style]
        # Double/final strokes are at measured offsets -7 and 0. The oracle
        # must recover those strokes without receiving these coordinates.
        for offset, width in zip((0,) if len(widths) == 1 else (-7, 0), widths):
            draw.rectangle((x+offset-width//2, 40, x+offset+width//2, 210), fill=INK)
    return image


def boundaries(styles=("regular", "regular", "regular")):
    return [{"beat": beat, "style": style} for beat, style in zip((0, 2, 4), styles)]


def test_real_retained_ala_rules_are_measured_without_renderer_coordinates():
    from piano_teacher.notation.measure_pixels import detect_barline_strokes
    with Image.open(REAL) as raw:
        result = detect_barline_strokes(raw)
    assert result["passed"], result
    assert result["staff_gap"] == pytest.approx(21.875)
    assert [rule["center"] for rule in result["strokes"]] == [490.5, 759, 1066.5, 1335]
    assert all(rule["cols"] and rule["width"] == len(rule["cols"])
               for rule in result["strokes"])


def test_real_before_ala_rest_is_268_half_pixels_and_must_fail_288_pixel_invariant():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    with Image.open(REAL) as raw:
        result = verify_measure_frame(raw, [{"beat": b} for b in (3, 6, 9, 12)],
                                      clock_beat=4.5, density=96)
    assert not result["passed"]
    assert result["errors"]
    assert result["widths"][0]["expected_px"] == 288
    assert result["widths"][0]["observed_px"] == 268.5
    assert result["widths"][0]["error_px"] == -19.5


@pytest.mark.parametrize("styles", [
    ("regular", "regular", "regular"),
    ("regular", "light-light", "regular"),
    ("regular", "light-heavy", "regular"),
    ("heavy-light", "heavy-heavy", "heavy"),
])
def test_one_clearance_and_explicit_solid_styles_keep_equal_widths(styles):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    result = verify_measure_frame(picture(styles), boundaries(styles), clock_beat=0, density=96)
    assert result["passed"], result
    assert result["clearance_px"] == pytest.approx(18)
    assert [w["observed_px"] for w in result["widths"]] == [192, 192]
    assert [b["observed_x"] for b in result["boundaries"]] == [318, 510, 702]


def test_stems_and_repeat_dots_cannot_become_grand_staff_rules():
    from piano_teacher.notation.measure_pixels import detect_barline_strokes, verify_measure_frame
    image = picture(("heavy-light", "regular", "light-heavy"))
    draw = ImageDraw.Draw(image)
    draw.line((400, 45, 400, 78), fill=INK, width=2)
    draw.line((430, 172, 430, 205), fill=INK, width=2)
    for x in (330, 682):
        for y in (55, 65, 185, 195):
            draw.ellipse((x-2, y-2, x+2, y+2), fill=INK)
    rules = detect_barline_strokes(image)
    assert len(rules["strokes"]) == 5
    expected = boundaries(("heavy-light", "regular", "light-heavy"))
    expected[0]["repeat"] = "forward"
    expected[-1]["repeat"] = "backward"
    assert verify_measure_frame(image, expected, clock_beat=0, density=96)["passed"]


@pytest.mark.parametrize("change", ("move", "duplicate", "missing", "local-density", "wrong-style"))
def test_boundary_mutations_fail_without_changing_musical_inputs(change):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    if change == "move":
        image = picture(shifts={1: 6})
    elif change == "local-density":
        image = picture(shifts={1: -48})
    elif change == "wrong-style":
        image = picture(("regular", "light-light", "regular"))
    else:
        image = picture()
        draw = ImageDraw.Draw(image)
        if change == "duplicate":
            draw.line((518, 40, 518, 210), fill=INK)
        else:
            draw.line((510, 40, 510, 210), fill=BACKGROUND)
            for y in (40, 50, 60, 70, 80, 170, 180, 190, 200, 210):
                draw.point((510, y), fill=RAIL)
    result = verify_measure_frame(image, boundaries(), clock_beat=0, density=96)
    assert not result["passed"], (change, result)
    assert result["errors"]


def test_frozen_reference_clearance_rejects_uniform_later_jump():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    calibration = verify_measure_frame(picture(), boundaries(), clock_beat=0, density=96)
    assert calibration["passed"]
    moved = picture(shifts={0: 6, 1: 6, 2: 6})
    # Fitting again would conceal this common displacement; the sequence must
    # retain its populated reference's sole clearance.
    assert verify_measure_frame(moved, boundaries(), clock_beat=0, density=96)["passed"]
    frozen = verify_measure_frame(moved, boundaries(), clock_beat=0, density=96,
                                  clearance_px=calibration["clearance_px"])
    assert not frozen["passed"]


def test_only_public_gutter_is_exempt_and_extra_rule_just_outside_it_fails():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    image = picture()
    ImageDraw.Draw(image).line((34, 40, 34, 210), fill=INK)
    result = verify_measure_frame(image, boundaries(), clock_beat=0, density=96)
    assert not result["passed"]
    assert any("unexpected" in message.lower() for message in result["errors"])


def test_fully_clipped_expected_boundaries_do_not_require_invented_rules():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    expected = [{"beat": -5}, *boundaries(), {"beat": 10}]
    result = verify_measure_frame(picture(), expected, clock_beat=0, density=96, clearance_px=18)
    assert result["passed"], result
    assert [b["beat"] for b in result["boundaries"]] == [0, 2, 4]


@pytest.mark.parametrize("anchor", (38, 799))
def test_partly_clipped_declared_double_group_is_not_an_extra_rule(anchor):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    image = picture()
    draw = ImageDraw.Draw(image)
    for x in (anchor-7, anchor):
        draw.line((x, 40, x, 210), fill=INK)
    edge_beat = (anchor+18-800*.42)/96
    expected = [*boundaries(), {"beat": edge_beat, "style": "light-light"}]
    result = verify_measure_frame(image, expected, clock_beat=0, density=96, clearance_px=18)
    assert result["passed"], result
    assert [b["beat"] for b in result["boundaries"]] == [0, 2, 4]
    assert len(result["clipped_boundaries"]) == 1


def test_visible_double_near_gutter_still_participates_in_projection():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    image = picture()
    draw = ImageDraw.Draw(image)
    for x in (35, 42):
        draw.line((x, 40, x, 210), fill=INK)
    beat = (42+18-800*.42)/96
    expected = [{"beat": beat, "style": "light-light"}, *boundaries()]
    result = verify_measure_frame(image, expected, clock_beat=0, density=96, clearance_px=18)
    assert result["passed"], result
    assert result["boundaries"][0]["observed_x"] == 42
    assert not result["clipped_boundaries"]


@pytest.mark.parametrize("principal_present", (True, False))
def test_left_clipped_double_requires_its_visible_principal(principal_present):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    image = picture()
    # At x=40 the secondary rule may legitimately be behind the 32px
    # gutter; the principal rule is fully visible and remains mandatory.
    if principal_present:
        ImageDraw.Draw(image).line((40, 40, 40, 210), fill=INK)
    beat = (40+18-800*.42)/96
    expected = [{"beat": beat, "style": "light-light"}, *boundaries()]
    result = verify_measure_frame(image, expected, clock_beat=0, density=96,
                                  clearance_px=18)
    assert result["passed"] is principal_present, result
    if not principal_present:
        assert any("principal" in error.lower() for error in result["errors"])


def test_missing_staff_ink_is_not_filled_from_an_assumed_lattice():
    from piano_teacher.notation.measure_pixels import detect_barline_strokes
    image = picture()
    ImageDraw.Draw(image).line((0, 60, 799, 60), fill=BACKGROUND)
    result = detect_barline_strokes(image)
    assert not result["passed"] and result["errors"]


def test_duplicate_expected_shared_boundary_and_relaxed_tolerance_fail_closed():
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    duplicate = verify_measure_frame(picture(), [*boundaries(), {"beat": 2}],
                                     clock_beat=0, density=96)
    relaxed = verify_measure_frame(picture(), boundaries(), clock_beat=0,
                                   density=96, tolerance_px=3)
    assert not duplicate["passed"] and duplicate["errors"]
    assert not relaxed["passed"] and relaxed["errors"]


@pytest.mark.parametrize("bad", ("dashed", "dotted", "tick", "short", "unknown"))
def test_unproved_styles_fail_closed(bad):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    expected = boundaries()
    expected[1]["style"] = bad
    result = verify_measure_frame(picture(), expected, clock_beat=0, density=96)
    assert not result["passed"] and result["errors"]


def test_actual_dpi_capture_scales_only_the_public_system_gutter():
    from piano_teacher.notation.measure_pixels import detect_barline_strokes, verify_measure_frame
    with Image.open(DPI_REAL) as image:
        unscaled = detect_barline_strokes(image)
        scaled = detect_barline_strokes(image, pixel_scale=1.25)
        assert any(rule["center"] == 35.5 for rule in unscaled["strokes"])
        assert all(rule["center"] >= 40 for rule in scaled["strokes"])
        expected = [{"beat": b} for b in range(4, 81, 4)]
        assert not verify_measure_frame(image, expected, clock_beat=12, density=120)["passed"]
        result = verify_measure_frame(image, expected, clock_beat=12, density=120,
                                      pixel_scale=1.25)
    assert result["passed"], result
    assert len(result["widths"]) == 2
    assert [w["expected_px"] for w in result["widths"]] == [480, 480]
    assert [w["observed_px"] for w in result["widths"]] == [480, 480]


def test_dpi_scale_does_not_exempt_rules_outside_scaled_gutter_or_relax_tolerance():
    from piano_teacher.notation.measure_pixels import detect_barline_strokes, verify_measure_frame
    with Image.open(DPI_REAL) as raw:
        image = raw.convert("RGB")
    measured = detect_barline_strokes(image, pixel_scale=1.25)
    top = round(measured["staffs"]["right"]["lines"][0])
    bottom = round(measured["staffs"]["left"]["lines"][-1])
    stroke = measured["strokes"][0]
    color = image.getpixel((stroke["cols"][0], (top+bottom)//2))
    ImageDraw.Draw(image).line((42, top, 42, bottom), fill=color)
    expected = [{"beat": b} for b in range(4, 81, 4)]
    result = verify_measure_frame(image, expected, clock_beat=12, density=120,
                                  pixel_scale=1.25)
    assert not result["passed"]
    assert any("unexpected" in error.lower() for error in result["errors"])
    relaxed = verify_measure_frame(image, expected, clock_beat=12, density=120,
                                   pixel_scale=1.25, tolerance_px=1.875)
    assert not relaxed["passed"]
    assert any("tolerance" in error.lower() for error in relaxed["errors"])


@pytest.mark.parametrize("scale", (0, -1, float("nan"), float("inf"), -float("inf")))
def test_nonpositive_or_nonfinite_pixel_scale_fails_closed(scale):
    from piano_teacher.notation.measure_pixels import detect_barline_strokes, verify_measure_frame
    detected = detect_barline_strokes(picture(), pixel_scale=scale)
    result = verify_measure_frame(picture(), boundaries(), clock_beat=0, density=96,
                                  pixel_scale=scale)
    assert not detected["passed"] and detected["errors"]
    assert not result["passed"] and result["errors"]
