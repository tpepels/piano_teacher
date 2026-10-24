"""Source ledger requirements cannot be supplied by a head or nearby mark."""
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.feature_pixels import verify_ledger_pixels, verify_note_feature_pixels
from piano_teacher.notation.visual_coverage import source_inventory, visual_elements
from test_phase3_visual_coverage import bar, note, score

FIXTURE = Path(__file__).parent/"fixtures/native_ledger_chord"


@pytest.fixture(scope="module")
def captured():
    xml = (FIXTURE/"score.musicxml").read_text()
    report = verify_ledger_pixels(xml, FIXTURE, hand="right")
    assert report["complete"], report
    return xml, report


def rows(xml, report, *, original=True, **kwargs):
    return [r for r in visual_elements(xml if original is True else original, xml, {}, {},
                                      hand="right", ledger_report=report, **kwargs)
            if r["construct"] == "ledger"]


@pytest.mark.parametrize("original", [True, None])
def test_actual_lines_verify_all_three_source_notes_without_changing_feature_counts(captured, original):
    xml, report = captured
    result = rows(xml, report, original=original)
    assert len(result) == 3 and all(r["status"] == "verified" for r in result), result
    assert sorted(r["source"]["details"]["expected_steps"] for r in result) == [[-2], [-2], [-2, -4]]
    ordinary = verify_note_feature_pixels(xml, FIXTURE, hand="right")
    assert all("ledger" not in r["features"] for r in ordinary["measured"])
    assert report["coverage"]["verified"] == 4


def test_inventory_preserves_missing_ledger_requirements_without_an_incoming_report(captured):
    xml, _ = captured
    required = [r for r in source_inventory(xml, "right") if r["construct"] == "ledger"]
    assert len(required) == 3
    unmeasured = rows(xml, None)
    assert all(r["status"] == "unsupported" for r in unmeasured)
    assert [{k: r[k] for k in ("id", "construct", "source")} for r in unmeasured] == required


@pytest.mark.parametrize("step,octave,clef,expected", [
    ("D", 4, ("G", 2, 0), []),
    ("C", 4, ("G", 2, 0), [-2]),
    ("G", 3, ("G", 2, 0), [-2, -4]),
    ("A", 5, ("G", 2, 0), [10]),
    ("C", 4, ("F", 4, 0), [10]),
    ("C", 4, ("C", 3, 0), []),
    ("C", 5, ("G", 2, 1), [-2]),
    ("G", 4, ("G", 1, 0), []),
])
def test_requirements_follow_written_pitch_and_declared_clef(step, octave, clef, expected):
    sign, line, change = clef
    xml = score(bar(note(step).replace('<octave>4</octave>', f'<octave>{octave}</octave>'),
                    attributes=f'<clef><sign>{sign}</sign><line>{line}</line>'
                               f'<clef-octave-change>{change}</clef-octave-change></clef>'))
    result = [r for r in source_inventory(xml, "right") if r["construct"] == "ledger"]
    assert [r["source"]["details"]["expected_steps"] for r in result] == ([expected] if expected else [])


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(source_id="foreign"),
    lambda r: r.update(beat=99.),
    lambda r: r.update(measure=True),
    lambda r: r.update(spelling=["C", 0, 6]),
    lambda r: r["features"]["ledger"].update(status="unverified"),
    lambda r: r["features"]["ledger"].update(expected_steps=[-4]),
    lambda r: r["features"]["ledger"].update(matched_segments=[]),
    lambda r: r["features"]["ledger"].update(evidence={}),
])
def test_exact_note_identity_steps_and_individual_measurements_are_required(captured, mutation):
    xml, saved = captured
    report = deepcopy(saved)
    report["measured"] = report["measured"][:1]
    mutation(report["measured"][0])
    assert all(r["status"] != "verified" for r in rows(xml, report))


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(head_match=.78),
    lambda e: e.update(staff_gap=0),
    lambda e: e.pop("registration"),
    lambda e: e.update(frame="not-an-image"),
    lambda e: e["segments"][0].update(continuous=False),
    lambda e: e["segments"][0].update(step=-4),
    lambda e: e["segments"][0].update(expected_y=e["segments"][0]["expected_y"]+20),
    lambda e: e["segments"][0].update(head_bbox=[0, 0, 1, 1]),
])
def test_consistently_forged_selected_witness_still_needs_ledger_measurements(captured, mutate):
    xml, saved = captured
    report = deepcopy(saved)
    report["measured"] = report["measured"][:1]
    observation = report["measured"][0]["features"]["ledger"]
    mutate(observation["evidence"])
    # Keep duplicate summary data consistent, so this probes the actual
    # geometric/measurement validator rather than only copy equality.
    observation["matched_segments"] = deepcopy(observation["evidence"].get("segments", []))
    for witness in observation["evidence"].get("witnesses", []):
        if witness.get("status") == "verified":
            mutate(witness)
    assert all(r["status"] != "verified" for r in rows(xml, report))


@pytest.mark.parametrize("mutation", ["head-only", "detached", "wrong-y", "thick"])
def test_a_head_detached_line_or_wrong_y_cannot_supply_the_required_segment(captured, mutation):
    xml, saved = captured
    report = deepcopy(saved)
    report["measured"] = report["measured"][:1]
    observation = report["measured"][0]["features"]["ledger"]
    def corrupt(e):
        segment, = e["segments"]
        box, head, gap = segment["bbox"], e["head_bbox"], e["staff_gap"]
        if mutation == "head-only":
            box[0], box[2] = head[0], head[2]
        elif mutation == "detached":
            box[0], box[2] = head[2]+5, head[2]+50
        elif mutation == "wrong-y":
            box[1] += round(gap/2)
            box[3] += round(gap/2)
        else:
            box[3] += round(gap)
        segment.update(y=(box[1]+box[3]-1)/2, thickness_spaces=(box[3]-box[1])/gap,
                       left_extension_spaces=(head[0]-box[0])/gap,
                       right_extension_spaces=(box[2]-head[2])/gap)
    corrupt(observation["evidence"])
    observation["matched_segments"] = deepcopy(observation["evidence"]["segments"])
    for witness in observation["evidence"]["witnesses"]:
        if witness["status"] == "verified":
            corrupt(witness)
    assert all(r["status"] != "verified" for r in rows(xml, report))


def test_duplicate_reports_and_partial_two_line_proofs_cannot_authorize(captured):
    xml, saved = captured
    duplicate = deepcopy(saved)
    duplicate["measured"].append(deepcopy(duplicate["measured"][0]))
    assert sum(r["status"] == "verified" for r in rows(xml, duplicate)) == 2
    partial = deepcopy(saved)
    lower = next(r for r in partial["measured"] if len(r["features"]["ledger"]["expected_steps"]) == 2)
    lower["features"]["ledger"]["matched_segments"].pop()
    result = rows(xml, partial)
    assert next(r for r in result if r["source"]["id"] == lower["source_id"])["status"] != "verified"


@pytest.mark.parametrize("report", [{}, {"complete": True, "status": "verified"},
                                    {"measured": [{"status": "verified"}]}])
def test_aggregate_or_status_only_reports_do_not_authorize_ledger_lines(captured, report):
    xml, _ = captured
    assert len(rows(xml, report)) == 3
    assert all(r["status"] != "verified" for r in rows(xml, report))


def test_source_window_retains_original_ids_but_binds_generated_clock_and_identity(captured):
    xml, saved = captured
    root = ET.fromstring(xml)
    for part in root.findall("part"):
        # The original source's first bar lasts four beats in divisions=8.
        prefix = ET.fromstring('<measure number="16"><attributes><divisions>8</divisions></attributes>'
                               '<note><rest/><duration>32</duration><type>whole</type></note></measure>')
        part.insert(0, prefix)
    original = ET.tostring(root, encoding="unicode")
    root = ET.fromstring(xml)
    replacements = {}
    for index, n in enumerate(root.findall("part/measure/note")):
        if n.get("id"):
            replacements[n.get("id")] = f"generated-{index}"
            n.set("id", replacements[n.get("id")])
    generated = ET.tostring(root, encoding="unicode")
    report = deepcopy(saved)
    for record in report["measured"]:
        record["source_id"] = replacements[record["source_id"]]
    result = rows(generated, report, original=original, first_bar=2, last_bar=2)
    assert len(result) == 3 and all(r["status"] == "verified" for r in result), result
    assert [r["source"]["beat"] for r in result] == [4., 6., 6.]
    assert all(r["source"]["id"] not in replacements.values() for r in result)
    for record in report["measured"]:
        record["beat"] += 4
    assert all(r["status"] != "verified" for r in rows(generated, report, original=original, first_bar=2, last_bar=2))


def test_generated_clef_cannot_rewrite_original_ledger_requirements(captured):
    xml, report = captured
    original = xml.replace('<sign>G</sign><line>2</line>', '<sign>F</sign><line>4</line>')
    result = rows(xml, report, original=original)
    assert result and all(r["status"] != "verified" for r in result)


def test_midmeasure_clef_requirements_are_retained_without_guessing_a_final_clef():
    notes = note(identity="before")+'<attributes><clef><sign>F</sign><line>4</line></clef></attributes>'+note(identity="after")
    xml = score(bar(notes, attributes='<clef><sign>G</sign><line>2</line></clef>'))
    inventory = [r for r in source_inventory(xml, "right") if r["construct"] == "ledger"]
    assert [r["source"]["details"]["expected_steps"] for r in inventory] == [[-2], [10]]
    assert all(r["source"]["details"]["error"] for r in inventory)


def test_known_missing_ledger_witness_cannot_be_overridden_by_another_green_frame(captured):
    xml, saved = captured
    report = deepcopy(saved)
    report["measured"] = report["measured"][:1]
    evidence = report["measured"][0]["features"]["ledger"]["evidence"]
    evidence["witnesses"].append(dict(frame="native-0.12500.png", status="mismatch"))
    assert all(r["status"] != "verified" for r in rows(xml, report))
