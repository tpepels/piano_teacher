"""Measure score movement from pixels, independently of renderer coordinates."""
from PIL import Image, ImageDraw

from piano_teacher.notation import phase3_pixels


def frame(shift):
    image = Image.new("RGB", (480, 240), "#102923")
    pen = ImageDraw.Draw(image)
    for x, y in ((130, 80), (210, 110), (340, 150)):
        pen.ellipse((x-shift-7, y-4, x-shift+7, y+4), fill="#E5F2EA")
        pen.line((x-shift+7, y, x-shift+7, y-50), fill="#E5F2EA", width=2)
    return image


def test_equal_musical_steps_have_equal_forward_image_displacement():
    result = phase3_pixels.verify_translation_sequence(frame(0), frame(6), frame(12))
    assert result["passed"]
    assert result["pixel_steps"] == [6, 6]


def test_frozen_reversed_or_jumping_score_does_not_pass():
    for shifts in ((0, 0, 0), (0, -6, -12), (0, 6, 24)):
        result = phase3_pixels.verify_translation_sequence(*(frame(s) for s in shifts))
        assert not result["passed"], shifts


def test_no_foreground_is_explicitly_unverified():
    blank = Image.new("RGB", (480, 240), "#102923")
    result = phase3_pixels.verify_translation_sequence(blank, blank, blank)
    assert not result["passed"]
    assert result["status"] == "unverified"



def test_repeated_ink_does_not_prove_an_arbitrary_scroll_displacement():
    """Tiled identical music must not authorize a single guessed jump."""
    from PIL import Image, ImageDraw
    def repeated(offset):
        photo = Image.new("RGB", (480, 240), "#102923")
        draw = ImageDraw.Draw(photo)
        for x in range(45, 490, 28):
            draw.rectangle((x-offset, 70, x-offset+9, 81), fill="#E5F2EA")
        return photo
    result = phase3_pixels.verify_translation_sequence(
        repeated(0), repeated(6), repeated(12))
    assert result["passed"] or result["status"] == "unverified"
    if result["competing_shifts"]:
        assert not result["passed"]
