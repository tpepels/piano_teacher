"""Beam/tuplet observations credit exact graphical source obligations only."""
from copy import deepcopy
from pathlib import Path

import pytest

from piano_teacher.notation.connector_pixels import verify_beam_pixels, verify_tuplet_pixels
from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.visual_coverage import visual_elements

FIXTURES = Path(__file__).parent / "fixtures/connector_pixels"


@pytest.fixture(scope="module")
def reports():
    result = {}
    for case in ("beams", "beam16", "beam-chords", "beam-down", "tuplets"):
        folder = FIXTURES/case
        xml = (folder/"score.musicxml").read_text()
        kind = "tuplet" if case == "tuplets" else "beam"
        report = (verify_tuplet_pixels if kind == "tuplet" else verify_beam_pixels)(xml, folder, hand="right")
        assert report["complete"], report
        result[case] = xml, report
    return result


def ledger(xml, kind, report, *, original=None, **kwargs):
    return visual_elements(original or xml, xml, {}, {}, hand="right", **{kind+"_report": report}, **kwargs)


def graphical(rows, kind):
    return [r for r in rows if r["construct"] == kind and
            (kind == "beam" or r["source"].get("details", {}).get("attributes", {}).get("type") in {"start", "stop"})]


@pytest.mark.parametrize("case", ["beams", "beam16", "beam-chords", "beam-down", "tuplets"])
def test_actual_bound_graphics_credit_every_explicit_source_marker(reports, case):
    xml, report = reports[case]
    kind = "tuplet" if case == "tuplets" else "beam"
    rows = graphical(ledger(xml, kind, report), kind)
    assert rows and all(r["status"] == "verified" for r in rows), rows
    if kind == "tuplet":
        semantics = [r for r in ledger(xml, kind, report) if r["construct"] == "tuplet" and r not in rows]
        assert len(semantics) == 5 and all(r["status"] != "verified" for r in semantics)


@pytest.mark.parametrize("kind", ["beam", "tuplet"])
def test_none_preserves_existing_ledger(reports, kind):
    xml, _ = reports["beams" if kind == "beam" else "tuplets"]
    assert ledger(xml, kind, None) == visual_elements(xml, xml, {}, {}, hand="right")


@pytest.mark.parametrize("kind", ["beam", "tuplet"])
@pytest.mark.parametrize("mutation", [
    lambda r: r.update(source_ids=["unbound"]),
    lambda r: r.update(event_ids=["unbound"]),
    lambda r: r.update(source_ids=list(reversed(r["source_ids"]))),
    lambda r: r.update(graphical=False),
    lambda r: r.update(graphical="true"),
    lambda r: r.update(status="unverified"),
    lambda r: r.update(measure=True),
    lambda r: r.update(beat=99.),
    lambda r: r.update(staff="left"),
    lambda r: r.update(voice="other"),
    lambda r: r.update(reference_group=None),
    lambda r: r.update(evidence={}),
    lambda r: r["evidence"].pop("anchors"),
    lambda r: r["evidence"]["anchors"][0].update(source_id="unbound"),
    lambda r: r["evidence"]["anchors"][0].update(head_match=.78),
    lambda r: r["evidence"].update(witnesses=[]),
])
def test_status_and_one_identity_space_cannot_replace_bound_graphical_measurements(reports, kind, mutation):
    xml, saved = reports["beams" if kind == "beam" else "tuplets"]
    report = deepcopy(saved)
    # Keep one group so another valid group's status cannot hide this failure.
    report["measured"] = report["measured"][:1]
    record = report["measured"][0]
    witnesses = list(record["evidence"]["witnesses"])
    mutation(record)
    for witness in witnesses:
        mutation(dict(record, evidence=witness))
    assert all(r["status"] != "verified" for r in graphical(ledger(xml, kind, report), kind))


@pytest.mark.parametrize("kind", ["beam", "tuplet"])
def test_duplicate_group_measurements_cannot_choose_one_verified_row(reports, kind):
    xml, saved = reports["beams" if kind == "beam" else "tuplets"]
    report = deepcopy(saved)
    report["measured"] = [report["measured"][0], deepcopy(report["measured"][0])]
    report["measured"][1]["status"] = "unverified"
    assert all(r["status"] != "verified" for r in graphical(ledger(xml, kind, report), kind))


@pytest.mark.parametrize("mutation", [
    lambda e: e.pop("stems"),
    lambda e: e.update(samples=[]),
    lambda e: e.update(continuity_columns=0),
    lambda e: e["samples"][0].update(levels=1),
    lambda e: e["stems"][0].update(x=e["stems"][0]["x"]+100),
])
def test_beam_requires_source_levels_actual_stems_and_full_interval_samples(reports, mutation):
    xml, saved = reports["beam16"]
    report = deepcopy(saved)
    report["measured"] = report["measured"][:1]
    evidence = report["measured"][0]["evidence"]
    mutation(evidence)
    for witness in evidence["witnesses"]:
        mutation(witness)
    assert all(r["status"] != "verified" for r in graphical(ledger(xml, "beam", report), "beam"))


@pytest.mark.parametrize("mutation", [
    lambda e: e.update(expected_numeral="3"),
    lambda e: e["digits"][0].update(code="E883"),
    lambda e: e["digits"][0].update(margin=.02),
    lambda e: e.pop("bracket_bbox"),
    lambda e: e.update(bracket_match=.71),
])
def test_tuplet_requires_original_ratio_glyphs_and_required_bracket(reports, mutation):
    xml, saved = reports["tuplets"]
    report = deepcopy(saved)
    evidence = report["measured"][0]["evidence"]
    mutation(evidence)
    for witness in evidence["witnesses"]:
        mutation(witness)
    assert all(r["status"] != "verified" for r in graphical(ledger(xml, "tuplet", report), "tuplet"))


def test_original_explicit_hook_cannot_borrow_generated_full_beam(reports):
    xml, report = reports["beam16"]
    original = xml.replace('<beam number="2">begin</beam>', '<beam number="2">forward hook</beam>')
    assert all(r["status"] != "verified" for r in graphical(ledger(xml, "beam", report, original=original), "beam"))


def test_actual_beams_supply_rhythm_only_with_pitch_and_all_feature_obligations(reports):
    xml, beam = reports["beams"]
    folder = FIXTURES/"beams"
    pitch = verify_all_notehead_pixels(xml, folder, hand="right")
    feature = verify_note_feature_pixels(xml, folder, hand="right")
    rows = visual_elements(xml, xml, pitch, {}, hand="right", feature_report=feature, beam_report=beam)
    rhythms = [r for r in rows if r["construct"] == "note_rhythm"]
    assert len(rhythms) == 8 and all(r["status"] == "verified" for r in rhythms), rhythms
    missing = deepcopy(beam)
    missing["measured"] = missing["measured"][:1]
    rows = visual_elements(xml, xml, pitch, {}, hand="right", feature_report=feature, beam_report=missing)
    assert sum(r["status"] == "verified" for r in rows if r["construct"] == "note_rhythm") == 4
