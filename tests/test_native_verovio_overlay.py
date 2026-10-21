"""The native-vs-Verovio audit must fail on the user's original defects."""
from PIL import Image, ImageDraw

from scripts.check_native_verovio_overlay import (
    MAX_AUTUMN_DENSITY, readability_errors, visible_ink,
)


def _model():
    return {
        "notes": [{"id": "note-a"}],
        "notation_events": [
            {"id": "glyph-a", "kind": "note", "dots": 1,
             "source_id": "note-a", "is_attack": True}
        ],
    }


def _report():
    return {
        "density": 188.0,
        "unavoidable_rest_overlaps": 0,
        "staff_gap": 18.0,
        "staff_centers": {"right": 190.0, "left": 359.0},
        "frames": [],
    }


def test_reported_excessive_density_is_detected():
    healthy = _report()
    assert not readability_errors(_model(), healthy)
    healthy["density"] = 438.68
    assert any("px/beat" in error for error in
               readability_errors(_model(), healthy))
    assert MAX_AUTUMN_DENSITY < 438.68


def test_unreadable_source_generated_triple_dots_are_detected():
    model = _model()
    model["notation_events"][0]["dots"] = 3
    assert any("triple/quadruple" in error for error in
               readability_errors(model, _report()))


def test_extra_source_graded_note_identity_is_detected():
    model = _model()
    model["notes"].append({"id": "missing-note"})
    assert any("attacks differ" in error for error in
               readability_errors(model, _report()))


def test_cross_voice_rest_collisions_are_detected():
    report = _report()
    report["unavoidable_rest_overlaps"] = 1
    assert any("collide" in error for error in
               readability_errors(_model(), report))


def test_visible_notehead_pixel_check_is_not_staff_rule_test():
    image = Image.new("RGB", (70, 70), "#102923")
    pen = ImageDraw.Draw(image)
    pen.line((0, 30, 69, 30), fill="#5B776C", width=1)
    assert visible_ink(image, 35, 30) == 0
    pen.ellipse((31, 26, 39, 34), fill="#E5F2EA")
    assert visible_ink(image, 35, 30) >= 35


def test_source_midi_micro_rest_clutter_is_detected():
    model = _model()
    for index in range(3):
        model["notation_events"].append({
            "id": f"rest-{index}", "kind":"rest",
            "note_type":"64th", "dots":0, "is_attack":False,
        })
    assert any("tiny printed rests" in error for error in
               readability_errors(model,_report()))


def test_native_rest_a_long_way_off_its_staff_is_detected():
    report = _report()
    report["frames"] = [{
        "rests": [{
            "id":"orphan-rest", "hand":"right",
            "x":720.0, "y":260.0,
        }],
    }]
    assert any("displaced too far" in error for error in
               readability_errors(_model(),report))
