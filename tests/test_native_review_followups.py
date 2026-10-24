"""Regressions for symbol ownership in the independent native image oracle."""
from pathlib import Path
from shutil import copyfile, copytree

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels, verify_structure_pixels
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.visual_coverage import visual_elements
from piano_teacher.notation.symbol_pixel_proof import bright, _outline

FIXTURES = Path(__file__).parent / "fixtures"


def quarter_xml(step="C", octave=4):
    return f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><time><beats>1</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes><note id="quarter">
    <pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>1</duration>
    <voice>1</voice><type>quarter</type></note></measure></part></score-partwise>'''


@pytest.mark.parametrize("clock,verified", [(6, True), (7, False), (7.5, False)])
def test_quarter_rhythm_requires_actual_absent_flag_pixels(tmp_path, clock, verified):
    # Retained real native C4 quarters/eighths have identical heads and pitch.
    copyfile(FIXTURES/f"feature_pixels/rhythms/native-{clock:.5f}.png",
             tmp_path/"native-0.00000.png")
    xml = quarter_xml()
    features = verify_note_feature_pixels(xml, tmp_path, hand="right")
    pitches = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    elements = visual_elements(None, xml, pitches, {}, hand="right", feature_report=features)
    rhythm, = [r for r in elements if r["construct"] == "note_rhythm"]
    assert (rhythm["status"] == "verified") is verified, rhythm
    absence = features["measured"][0]["features"]["flag_absence"]
    assert (absence["status"] == "verified") is verified, absence


def test_quarter_rhythm_cannot_trust_an_absence_status_without_measurements(tmp_path):
    copyfile(FIXTURES/"feature_pixels/rhythms/native-6.00000.png", tmp_path/"native-0.00000.png")
    xml = quarter_xml()
    features = verify_note_feature_pixels(xml, tmp_path, hand="right")
    features["measured"][0]["features"]["flag_absence"] = {"status": "verified", "evidence": {}}
    pitches = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    elements = visual_elements(None, xml, pitches, {}, hand="right", feature_report=features)
    assert next(r for r in elements if r["construct"] == "note_rhythm")["status"] != "verified"


def test_downward_32nd_flag_cannot_certify_a_quarter(tmp_path):
    copyfile(FIXTURES/"native_flag_down_32/native-5.50000.png", tmp_path/"native-0.00000.png")
    report = verify_note_feature_pixels(quarter_xml("D", 6), tmp_path, hand="right")
    features = report["measured"][0]["features"]
    assert features["stem"]["status"] == "verified"
    assert features["stem"]["evidence"]["direction"] == "down"
    assert features["flag_absence"]["status"] == "mismatch"


def test_unclassified_ink_beside_a_quarter_stem_is_not_absence(tmp_path):
    path = tmp_path/"native-0.00000.png"
    copyfile(FIXTURES/"feature_pixels/rhythms/native-6.00000.png", path)
    picture = Image.open(path).convert("RGB")
    ImageDraw.Draw(picture).rectangle((666, 190, 669, 193), fill="#E5F2EA")
    picture.save(path)
    features = verify_note_feature_pixels(quarter_xml(), tmp_path, hand="right")["measured"][0]["features"]
    assert features["stem"]["status"] == "verified"
    assert features["flag_absence"]["status"] == "unverified"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(bbox=[v+100 for v in e["bbox"]]),
    lambda e: e.update(stem_bbox=[0, 0, 1, 1]),
    lambda e: e.update(bright_pixels=False),
    lambda e: e.update(expected_count=False),
    lambda e: e.update(family_scores={}),
    lambda e: e["family_scores"].update(flag_up_1=float("nan")),
    lambda e: e.update(shared_source_ids=["another-event"]),
])
def test_quarter_absence_must_measure_its_bound_stem_attachment(tmp_path, mutate):
    copyfile(FIXTURES/"feature_pixels/rhythms/native-6.00000.png", tmp_path/"native-0.00000.png")
    xml = quarter_xml()
    features = verify_note_feature_pixels(xml, tmp_path, hand="right")
    absence = features["measured"][0]["features"]["flag_absence"]
    assert absence["status"] == "verified"
    mutate(absence["evidence"])
    pitches = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    elements = visual_elements(None, xml, pitches, {}, hand="right", feature_report=features)
    assert next(r for r in elements if r["construct"] == "note_rhythm")["status"] != "verified"


def test_source_chord_shares_one_absent_flag_attachment_at_its_common_stem():
    folder = FIXTURES/"native_ledger_chord"
    xml = (folder/"score.musicxml").read_text()
    report = verify_note_feature_pixels(xml, folder)
    chord = [r for r in report["measured"] if r["beat"] == 0]
    assert len(chord) == 4
    assert all(r["features"]["stem"]["status"] == "verified" for r in chord)
    absence = [r["features"]["flag_absence"] for r in chord]
    assert all(r["status"] == "verified" for r in absence), absence
    assert all(r == absence[0] for r in absence)
    assert len(absence[0]["evidence"]["shared_source_ids"]) == 4
    pitches = verify_all_notehead_pixels(xml, folder)
    ledger = visual_elements(None, xml, pitches, {}, feature_report=report)
    rhythms = {tuple(r["source"]["spelling"]): r["status"] for r in ledger
               if r["construct"] == "note_rhythm" and r["source"]["beat"] == 0}
    # Shared absence does not authorize the still-unresolved C4 dot.
    assert rhythms == {("C", 0, 4): "unverified", ("D", 0, 4): "verified",
                       ("F", 0, 4): "verified", ("D", 0, 5): "verified"}


def test_unrelated_ink_at_a_common_stem_blocks_absence_for_every_chord_member(tmp_path):
    folder = FIXTURES/"native_ledger_chord"
    copytree(folder, tmp_path, dirs_exist_ok=True)
    path = tmp_path/"native-0.00000.png"
    picture = Image.open(path).convert("RGB")
    ImageDraw.Draw(picture).rectangle((675, 120, 678, 123), fill="#E5F2EA")
    picture.save(path)
    report = verify_note_feature_pixels((folder/"score.musicxml").read_text(), tmp_path)
    chord = [r for r in report["measured"] if r["beat"] == 0]
    assert len(chord) == 4
    assert all(r["features"]["stem"]["status"] == "verified" for r in chord)
    assert all(r["features"]["flag_absence"]["status"] != "verified" for r in chord)


def structures(folder):
    xml = (folder/"score.musicxml").read_text()
    return verify_structure_pixels(xml, folder, visual_elements(None, xml, {}, {}))


def test_erased_barline_cannot_borrow_a_nearby_full_staff_stem(tmp_path):
    copytree(FIXTURES/"native_structure", tmp_path, dirs_exist_ok=True)
    path = tmp_path/"native-4.00000.png"
    picture = Image.open(path).convert("RGB")
    staves = detect_staff_lines(picture)
    draw = ImageDraw.Draw(picture)
    for staff in staves.values():
        for y in range(round(staff.lines[0])+2, round(staff.lines[-1])-2):
            if min(abs(y-line) for line in staff.lines) >= 2:
                draw.line((555, y, 735, y), fill="#102923")
        x = round(picture.width*.42+3*staff.gap)
        draw.line((x, round(staff.lines[0]), x, round(staff.lines[-1])), fill="#E5F2EA", width=2)
    picture.save(path)
    rules = [r for r in structures(tmp_path) if r["construct"] in {"measure", "barline"}]
    assert rules and all(r["status"] != "verified" for r in rules), rules


def test_boundary_needs_the_same_moving_rule_in_another_actual_frame(tmp_path):
    copytree(FIXTURES/"native_structure", tmp_path, dirs_exist_ok=True)
    # Keep the real rule at the exact boundary, erase its earlier witness.
    path = tmp_path/"native-0.00000.png"
    picture = Image.open(path).convert("RGB")
    ImageDraw.Draw(picture).rectangle((1016, 140, 1022, 405), fill="#102923")
    picture.save(path)
    rules = [r for r in structures(tmp_path) if r["construct"] in {"measure", "barline"}]
    assert rules and all(r["status"] != "verified" for r in rules), rules


def test_boundary_cannot_choose_between_two_source_interval_tracks(tmp_path):
    copytree(FIXTURES/"native_structure", tmp_path, dirs_exist_ok=True)
    # A second dim line follows the same camera motion. It cannot steal the
    # original rule's source identity simply by being nearer the playhead.
    for name, x in (("native-0.00000.png", 984), ("native-4.00000.png", 600)):
        path = tmp_path/name
        picture = Image.open(path).convert("RGB")
        ImageDraw.Draw(picture).line((x, 143, x, 402), fill=(110, 119, 115), width=2)
        if x == 600:
            ImageDraw.Draw(picture).rectangle((633, 140, 637, 405), fill="#102923")
        picture.save(path)
    rules = [r for r in structures(tmp_path) if r["construct"] in {"measure", "barline"}]
    assert rules and all(r["status"] != "verified" for r in rules), rules


def test_boundary_ownership_allows_a_different_readable_rule_offset(tmp_path):
    copytree(FIXTURES/"native_structure", tmp_path, dirs_exist_ok=True)
    # Both frames retain the same source-owned line, ten pixels farther from
    # the next onset. A native implementation constant is not the oracle.
    for name, x in (("native-0.00000.png", 1019), ("native-4.00000.png", 635)):
        path = tmp_path/name
        picture = Image.open(path).convert("RGB")
        strip = picture.crop((x-1, 140, x+2, 405))
        ImageDraw.Draw(picture).rectangle((x-1, 140, x+1, 405), fill="#102923")
        picture.paste(strip, (x-11, 140))
        picture.save(path)
    rules = [r for r in structures(tmp_path) if r["construct"] in {"measure", "barline"}]
    assert rules and all(r["status"] == "verified" for r in rules), rules


def test_frozen_frames_do_not_establish_a_boundary_clock(tmp_path):
    copytree(FIXTURES/"native_structure", tmp_path, dirs_exist_ok=True)
    copyfile(tmp_path/"native-0.00000.png", tmp_path/"native-4.00000.png")
    rules = [r for r in structures(tmp_path) if r["construct"] in {"measure", "barline"}]
    assert rules and all(r["status"] != "verified" for r in rules), rules


def meter_fixture(folder, numerator, denominator, *, painted=None):
    # Keep authentic staff pixels; render independent external-font digits in
    # a freely spaced header. Expectations below are the literal XML numbers.
    from piano_teacher.notation.feature_pixels import _feature_glyphs
    source = FIXTURES/"native_structure"
    xml = (source/"score.musicxml").read_text().replace("<beats>4</beats>", f"<beats>{numerator}</beats>")
    xml = xml.replace("<beat-type>4</beat-type>", f"<beat-type>{denominator}</beat-type>")
    (folder/"score.musicxml").write_text(xml)
    picture = Image.open(source/"native-0.00000.png").convert("RGB")
    staves = detect_staff_lines(picture)
    pixels = np.array(picture)
    erase = bright(picture)
    erase[:, :450] = False
    erase[:, 600:] = False
    pixels[erase] = [16, 41, 35]
    glyphs = _feature_glyphs()
    for staff in staves.values():
        for text, y in ((painted or numerator, sum(staff.lines)/5-staff.gap),
                        (denominator, sum(staff.lines)/5+.8*staff.gap)):
            for i, digit in enumerate(text):
                glyph = glyphs["time_"+digit]
                b, gap = glyph["bounds"], staff.gap
                width, height = round(b[2]*gap/250), round(b[3]*gap/250)
                mask = _outline(glyph["svg"], width, height)
                x = 520+(i-(len(text)-1)/2)*42
                left, top = round(x-b[2]*gap/500), round(y+b[1]*gap/250)
                pixels[top:top+height, left:left+width][mask] = [229, 242, 234]
    Image.fromarray(pixels).save(folder/"native-0.00000.png")
    elements = [r for r in visual_elements(None, xml, {}, {}) if r["construct"] == "meter"]
    return verify_structure_pixels(xml, folder, elements)


@pytest.mark.parametrize("numerator,denominator", [("12", "8"), ("11", "16"), ("10", "8")])
def test_multidigit_meter_uses_ordered_distinct_actual_contours(tmp_path, numerator, denominator):
    rows = meter_fixture(tmp_path, numerator, denominator)
    assert rows and all(r["status"] == "verified" for r in rows), rows
    for row in rows:
        digits = row["evidence"]["digits"]
        assert len(digits) == len(numerator)+len(denominator)
        assert [d["evidence"]["observed"] for d in digits] == ["time_"+d for d in numerator+denominator]
        assert len({tuple(d["evidence"]["bbox"]) for d in digits}) == len(digits)


@pytest.mark.parametrize("expected,painted", [("12", "21"), ("11", "1"), ("12", "112")])
def test_meter_does_not_reorder_reuse_or_skip_digit_ink(tmp_path, expected, painted):
    rows = meter_fixture(tmp_path, expected, "8", painted=painted)
    assert rows and all(r["status"] != "verified" for r in rows), rows
