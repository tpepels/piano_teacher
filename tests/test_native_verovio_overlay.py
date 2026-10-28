"""The native-vs-Verovio audit must fail on the user's original defects."""
from PIL import Image, ImageDraw

from scripts.audits.case_catalog import CASES, MAX_AUTUMN_DENSITY, selected_cases
from scripts.audits.frame_evidence import feature_errors, readability_errors, visible_ink


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

def test_focused_overlay_regressions_retain_hard_passages_and_notation_features():
    from scripts.audits.case_catalog import library_sources
    expected_files = {path.name for path in library_sources()}
    assert {case.filename for case in CASES if "/" not in case.filename} <= expected_files
    assert len(CASES) >= 15
    assert sum("/" in case.filename for case in CASES) >= 6
    assert {"chords", "ties", "tuplets", "grandstaff", "key_change", "rests"} <= {
        feature for case in CASES for feature in case.features
    }
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



def test_challenging_corpus_does_not_pass_if_feature_disappears():
    from scripts.check_native_verovio_overlay import AuditCase
    case = AuditCase("broken-tuplets", "demo.musicxml", 1, 1,
                     features=("tuplets",))
    assert feature_errors(_model(), case) == [
        "broken-tuplets stopped exercising required tuplets notation"]
    event = _model()
    event["notation_events"][0]["time_modification"] = {"actual": 3, "normal": 2}
    assert feature_errors(event, case) == []


def test_dense_chopin_requires_usable_forward_reading_context():
    from scripts.audits.case_catalog import CASES
    chopin = next(c for c in CASES if c.name == "chopin-5-6-both")
    assert chopin.min_lookahead_beats == 1.75
    # The previous "fix" merely raised the permitted density to 700. That
    # would accept <1.4 beats of visible musical future.
    assert chopin.max_density < 650.6
    report = _report()
    report.update({
        "density": 650.6,
        "density_witness": {"available_lookahead_beats":1.37}
    })
    assert any("beats ahead" in message for message in
               readability_errors(_model(), report, chopin))
    report["density"] = 500
    report["density_witness"]["available_lookahead_beats"] = 1.78
    # This synthetic model intentionally has no Chopin triplet; the
    # separate feature-loss test covers that constraint. Here verify only
    # the reading-context regression, without weakening either audit.
    assert not any("beats ahead" in problem for problem in
                   readability_errors(_model(), report, chopin))


def test_collision_explanation_identifies_real_source_ink_pair():
    # The native renderer's load-time witness is attached to a source-
    # backed note identity rather than a magic density threshold. This
    # keeps the next regression actionable.
    witness = {
        "reason":"horizontal-ink-clearance",
        "previous_kind":"note","next_kind":"note",
        "previous_beat":8.16458333,"next_beat":8.25,
        "required_density":650.6,
        "previous_rect":[-14.8,130.4,29.7,130.4],
        "next_rect":[-36.3,122.2,51.2,105.4],
    }
    separation = witness["next_beat"]-witness["previous_beat"]
    required = ((witness["previous_rect"][0]+witness["previous_rect"][2])
                - witness["next_rect"][0] + 22*.2) / separation
    assert required == __import__("pytest").approx(
        witness["required_density"], rel=.006)



def _absence_report(*, status='unverified'):
    return {
        'measured': [{'region':'viewport','frame':'native-0.00000.png',
                      'clock':0, 'status':status,'reason':'unowned header ink',
                      'evidence':{'unowned_pixels':8}}],
        'complete':False,
        'coverage':{'full_absence_status':'unverified','frames':1,
                    'measured_frames':1,'initial_viewport':True,
                    'terminal_viewport':True,'motion_status':'verified',
                    'clock_gaps':[],'motion_errors':[],
                    'missing_source_clocks':[],'binding_errors':[],
                    'expected_heads':1,'bound_heads':1,
                    'expected_rests':1,'bound_rests':1}
    }


def test_indeterminate_background_ink_is_not_misreported_as_a_wrong_note():
    from scripts.audits.proof_execution import absence_evidence_errors
    # A valid source-anchored score can still have ink from headers or
    # antialiasing the absence detector cannot uniquely attribute.
    report = _absence_report()
    assert not absence_evidence_errors(report)
    assert report['coverage']['full_absence_status'] == 'unverified'


def test_real_extra_glyphs_and_missing_capture_still_fail():
    from scripts.audits.proof_execution import absence_evidence_errors
    report = _absence_report(status='mismatch')
    assert any('Unexpected-symbol' in e for e in absence_evidence_errors(report))
    report = _absence_report()
    report['coverage']['bound_heads'] = 0
    assert any('heads ownership' in e for e in absence_evidence_errors(report))
    report['coverage']['bound_heads'] = 1
    report['coverage']['clock_gaps'] = [[0, 1]]
    assert any('clock' in e for e in absence_evidence_errors(report))
