"""The native-vs-Verovio audit must fail on the user's original defects."""
from PIL import Image, ImageDraw

from scripts.check_native_verovio_overlay import (
    CASES, MAX_AUTUMN_DENSITY, readability_errors, selected_cases, visible_ink,
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

def test_real_overlay_corpus_is_pinned_to_every_bundled_midi():
    from scripts.check_user_midi_visual_regression import CASES as MIDI_CASES
    expected_files = {filename for filename, hand in MIDI_CASES}
    assert {case.filename for case in CASES} == expected_files
    assert len(CASES) >= 9
    assert len({case.name for case in CASES}) == len(CASES)
    assert any(case.name == "autumn-7-8-both" and
               case.max_density == MAX_AUTUMN_DENSITY for case in CASES)
    assert any(case.filename.startswith("Chopin") and
               case.first_bar > 1 for case in CASES)
    assert {"left", "right", "both"} <= {case.hand for case in CASES}
    assert all(case.first_bar > 0 and case.last_bar >= case.first_bar
               for case in CASES)


def test_overlay_case_selector_never_silently_drops_the_hard_passage():
    assert selected_cases() == CASES
    assert [case.name for case in selected_cases("autumn-7-8")] == [
        "autumn-7-8-both"]
    assert len(selected_cases("Chopin")) == 2
    import pytest
    with pytest.raises(ValueError, match="No native overlay cases"):
        selected_cases("not-a-real-midi")


def test_per_case_density_and_rest_budgets_are_isolated():
    from scripts.check_native_verovio_overlay import AuditCase
    easy = AuditCase("other", "test.midi", 1, 2, max_density=500,
                     max_tiny_rests=5, max_dots=4)
    test_model = _model()
    test_model["notation_events"][0]["dots"] = 3
    report = _report()
    report["density"] = 438.68
    assert readability_errors(test_model, report, easy) == []
    assert any("px/beat" in error for error in
               readability_errors(test_model, report, CASES[0]))

