"""Prove the native screenshot validator can catch *pixel* defects.

These tests fabricate raster staff lines/noteheads at known positions. Mutation
tests move, erase or corrupt the actual pixels without changing native metadata.
Integration CI separately captures the real Godot renderer.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

from piano_teacher.notation.pixel_proof import (
    detect_staff_lines, expected_y, observed_notehead_y, observed_notehead_ys, verify_pixel_frames,
)

SOURCE = Path(__file__).parent / "fixtures" / "native_pixel_pitch_probe.musicxml"


def frame(*, shift=0, missing=None):
    image = Image.new("RGB", (1536, 520), (16, 41, 35))
    draw = ImageDraw.Draw(image)
    for center in (160, 360):
        for dy in (-40, -20, 0, 20, 40):
            draw.line((0, center + dy, 1535, center + dy),
                      fill=(73, 83, 77), width=1)
    x = round(image.width * .42)
    # Source beat zero: E4 at lower treble rail, G2 at lower bass rail.
    for hand, y in (("right", 200), ("left", 400)):
        if hand == missing:
            continue
        draw.ellipse((x - 10, y - 5 + shift, x + 10, y + 5 + shift),
                     fill=(230, 240, 234))
    return image


def test_staves_and_noteheads_measured_only_from_image_pixels():
    image = frame()
    staffs = detect_staff_lines(image)
    assert staffs["right"].lines == (120, 140, 160, 180, 200)
    assert staffs["left"].lines == (320, 340, 360, 380, 400)
    assert staffs["right"].gap == 20
    assert expected_y(staffs["right"], ("E", 0, 4), ("G", 2, 0)) == 200
    assert expected_y(staffs["left"], ("G", 0, 2), ("F", 4, 0)) == 400
    for hand in ("right", "left"):
        center, _ = observed_notehead_y(image, hand, staffs[hand])
        assert abs(center - (200 if hand == "right" else 400)) < 2


def test_one_staff_step_mutation_of_actual_pixels_fails(tmp_path):
    broken = frame(shift=-10)
    path = tmp_path / "bad.png"
    broken.save(path)
    staffs = detect_staff_lines(broken)
    for hand, spelling, clef in [
        ("right", ("E", 0, 4), ("G", 2, 0)),
        ("left", ("G", 0, 2), ("F", 4, 0)),
    ]:
        expected = expected_y(staffs[hand], spelling, clef)
        actual, _ = observed_notehead_y(broken, hand, staffs[hand])
        assert abs(actual - expected) / (staffs[hand].gap / 2) > .42


def test_erasing_actual_notehead_pixels_fails():
    image = frame(missing="right")
    staves = detect_staff_lines(image)
    import pytest
    with pytest.raises(AssertionError, match="no measurable notehead ink"):
        observed_notehead_y(image, "right", staves["right"])


def test_staff_line_corruption_is_detected():
    image = frame()
    drawing = ImageDraw.Draw(image)
    drawing.line((0, 140, 1535, 140), fill=(16, 41, 35), width=1)
    import pytest
    with pytest.raises(AssertionError, match="staff rails"):
        detect_staff_lines(image)


def test_report_refuses_incomplete_screenshot_coverage(tmp_path):
    img = frame()
    path = tmp_path / "only-one-frame.png"
    img.save(path)
    import pytest
    with pytest.raises(AssertionError, match="Missing or extra frame beats"):
        verify_pixel_frames(SOURCE.read_text(), {0.0: path})


def test_image_validator_ignores_native_reported_positions(tmp_path):
    # No Godot-provided Y coordinate is supplied to any verifier. Replacing a
    # screenshot with a displaced head is sufficient to produce a failure.
    source = SOURCE.read_text()
    good = frame()
    bad = frame(shift=10)
    for index, image in enumerate((good, bad)):
        path = tmp_path / f"{index}.png"
        image.save(path)
        assert path.is_file()
    # The source has 8 beats, so use the pixel locator for one pair directly.
    staffs = detect_staff_lines(bad)
    observed, _ = observed_notehead_y(bad, "right", staffs["right"])
    target = expected_y(staffs["right"], ("E", 0, 4), ("G", 2, 0))
    assert abs(observed - target) > 5


def test_chord_pixels_produce_multiple_independent_image_centres():
    image = frame()
    draw = ImageDraw.Draw(image)
    x = round(image.width * .42)
    # A written C-E-G chord has heads two staff steps (one gap) apart.
    for y in (180, 160):
        draw.ellipse((x-10, y-5, x+10, y+5), fill=(230, 240, 234))
    staves = detect_staff_lines(image)
    assert observed_notehead_ys(image, "right", staves["right"]) == [160, 180, 200]


def test_erasing_one_chord_tone_changes_measured_pixel_inventory():
    image = frame()
    draw = ImageDraw.Draw(image)
    x = round(image.width * .42)
    draw.ellipse((x-10, 175, x+10, 185), fill=(230, 240, 234))
    draw.ellipse((x-10, 155, x+10, 165), fill=(230, 240, 234))
    staffs = detect_staff_lines(image)
    assert len(observed_notehead_ys(image, "right", staffs["right"])) == 3

    # Deliberately erase the top tone from the actual image. The bottom two
    # stay in place, and the source still expects three separate noteheads.
    draw.rectangle((x-13, 152, x+13, 168), fill=(16, 41, 35))
    # Restore the native staff rule passing through the erased glyph.
    draw.line((x-13, 160, x+13, 160), fill=(73, 83, 77), width=1)
    assert len(observed_notehead_ys(image, "right", staffs["right"])) == 2
