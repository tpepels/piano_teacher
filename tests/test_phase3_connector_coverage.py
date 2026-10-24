"""Only unique, source-bound endpoint/curve observations may credit connectors."""
from copy import deepcopy

import pytest

from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels
from piano_teacher.notation.visual_coverage import source_inventory, visual_elements
from test_source_connector_pixels import pictures, score


@pytest.fixture(scope="module")
def proofs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("connector-consumer")
    pictures(folder)
    result = {}
    for kind in ("tie", "slur"):
        xml = score(construct=kind)
        report = verify_connector_pixels(xml, folder, constructs=(kind,))
        assert report["complete"], report
        result[kind] = xml, report
    return result


def connectors(xml, report, *, original=True, **kwargs):
    return [r for r in visual_elements(xml if original is True else original, xml, {}, {},
                                      connector_report=report, **kwargs)
            if r["construct"] in {"tie", "slur"}]


@pytest.mark.parametrize("kind", ["tie", "slur"])
@pytest.mark.parametrize("original", [True, None])
def test_measured_pair_credits_both_original_endpoint_obligations(proofs, kind, original):
    xml, report = proofs[kind]
    result = connectors(xml, report, original=original)
    assert len(result) == 2 and all(r["status"] == "verified" for r in result), result
    assert [r["source"]["id"] for r in result] == ["a", "b"]
    assert [r["source"]["details"]["attributes"]["type"] for r in result] == ["start", "stop"]
    inventory = source_inventory(xml)
    if original is None:
        for row in inventory:
            row["source"]["origin"] = "generated"
    assert [{k: r[k] for k in ("construct", "source")} for r in result] == [
        {k: r[k] for k in ("construct", "source")} for r in inventory if r["construct"] == kind]


def test_absent_optional_report_preserves_legacy_unsupported_rows(proofs):
    xml, _ = proofs["tie"]
    before = visual_elements(xml, xml, {}, {})
    assert visual_elements(xml, xml, {}, {}, connector_report=None) == before
    assert all(r["status"] == "unsupported" for r in before if r["construct"] == "tie")


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(source_ids=["a", "other"]),
    lambda r: r.update(oracle_source_ids=["xml-p0-m0-e1", "xml-p0-m0-e99"]),
    lambda r: r.update(source_ids=["b", "a"]),
    lambda r: r.update(oracle_source_ids=list(reversed(r["oracle_source_ids"]))),
    lambda r: r.pop("source_ids"),
    lambda r: r.pop("oracle_source_ids"),
    lambda r: r.update(construct="slur"),
    lambda r: r.update(number="2"),
    lambda r: r.update(status="unverified"),
    lambda r: r.update(status="mismatch"),
    lambda r: r.update(evidence={}),
])
def test_ordered_pair_both_identity_spaces_number_and_measurements_are_required(proofs, mutation):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    mutation(report["observations"][0])
    assert all(r["status"] != "verified" for r in connectors(xml, report))


@pytest.mark.parametrize("report", [None, {}, [], "verified", {"complete": True, "status": "verified"},
                                    {"observations": [{"status": "verified"}]},
                                    {"observations": [None, []]}])
def test_aggregate_or_unbound_status_cannot_authorize_an_endpoint(proofs, report):
    xml, _ = proofs["tie"]
    assert all(r["status"] != "verified" for r in connectors(xml, report))


@pytest.mark.parametrize("duplicate_status", ["verified", "unverified"])
def test_duplicate_pair_records_block_unique_evidence(proofs, duplicate_status):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    duplicate = deepcopy(report["observations"][0])
    duplicate["status"] = duplicate_status
    report["observations"].append(duplicate)
    assert all(r["status"] != "verified" for r in connectors(xml, report))


@pytest.mark.parametrize("mutate", [
    lambda e: e.pop("heads"),
    lambda e: e["heads"][0].update(source_id="other"),
    lambda e: e["heads"][0].update(contour_score=.78),
    lambda e: e["heads"][1].update(gap=0),
    lambda e: e["heads"][0].pop("bbox"),
    lambda e: e.pop("correspondence"),
    lambda e: e["correspondence"][1].update(onset_frame="native-99.00000.png"),
    lambda e: e["correspondence"][1].update(contour_agreement=.79),
    lambda e: e.update(frame="native-99.00000.png"),
    lambda e: e.update(connected_pixels=True),
    lambda e: e.update(connected_pixels=e["connected_pixels"]+1),
    lambda e: e.update(curvature_spaces=0),
    lambda e: e.update(max_thickness_spaces=.81),
    lambda e: e.update(endpoint_distances_spaces=[0, .91]),
    lambda e: e.pop("pixel_runs"),
    lambda e: e.update(pixel_runs=[]),
    lambda e: e.pop("component_bbox"),
])
def test_status_cannot_replace_head_translation_and_connected_thin_curve_fields(proofs, mutate):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    mutate(report["observations"][0]["evidence"])
    assert all(r["status"] != "verified" for r in connectors(xml, report))


def test_original_number_and_generated_endpoint_declarations_must_both_match(proofs):
    xml, report = proofs["slur"]
    original = xml.replace('number="7"', 'number="8"')
    assert all(r["status"] != "verified" for r in connectors(xml, report, original=original))
    generated = xml.replace('<slur type="stop" number="7"/>', '')
    assert all(r["status"] != "verified" for r in connectors(generated, report, original=xml))


def test_original_window_uses_mapped_generated_ids_and_clocks(proofs):
    xml, saved = proofs["slur"]
    # Original source window starts at beat four; generated window restarts
    # at zero, renames IDs/voice, and keeps the original measure label.
    prefix = '<measure number="10"><note><rest/><duration>4</duration><type>whole</type></note></measure>'
    original = xml.replace('<measure number="1">', '<measure number="20">')
    original = original.replace('<measure number="20">', prefix+'<measure number="20">')
    generated = xml.replace('number="1"><attributes>', 'number="20"><attributes>')
    generated = generated.replace('id="a"', 'id="g"').replace('id="b"', 'id="h"').replace('<voice>1</voice>', '<voice>9</voice>')
    report = deepcopy(saved)
    report["observations"][0]["source_ids"] = ["g", "h"]
    for head, sid in zip(report["observations"][0]["evidence"]["heads"], ("g", "h")):
        head["source_id"] = sid
    result = connectors(generated, report, original=original, first_bar=2, last_bar=2)
    assert len(result) == 2 and all(r["status"] == "verified" for r in result), result
    assert [r["source"]["id"] for r in result] == ["a", "b"]
    assert [r["source"]["beat"] for r in result] == [4., 6.]


def test_one_tie_chain_pair_cannot_credit_the_next_pair(proofs):
    xml, report = proofs["tie"]
    xml = xml.replace('<tie type="stop"/>', '<tie type="stop"/><tie type="start"/>')
    xml = xml.replace('<tied type="stop"/>', '<tied type="stop"/><tied type="start"/>')
    xml = xml.replace('<note><rest/><duration>1</duration><voice>1</voice><type>quarter</type></note>',
        '<note id="c"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>'
        '<voice>1</voice><type>quarter</type><tie type="stop"/><notations><tied type="stop"/></notations></note>')
    result = connectors(xml, report)
    assert len(result) == 4
    assert [(r["source"]["id"], r["source"]["details"]["attributes"]["type"])
            for r in result if r["status"] == "verified"] == [("a", "start"), ("b", "stop")]


def test_duplicate_source_ids_cannot_be_rescued_by_positional_ids(proofs):
    xml, saved = proofs["tie"]
    xml = xml.replace('id="b"', 'id="a"')
    report = deepcopy(saved)
    report["observations"][0]["source_ids"] = ["a", "a"]
    report["observations"][0]["evidence"]["heads"][1]["source_id"] = "a"
    assert all(r["status"] != "verified" for r in connectors(xml, report))


def test_one_component_cannot_be_credited_to_two_constructs(proofs):
    xml, saved = proofs["tie"]
    xml = xml.replace('<tied type="start"/>', '<tied type="start"/><slur type="start" number="7"/>')
    xml = xml.replace('<tied type="stop"/>', '<tied type="stop"/><slur type="stop" number="7"/>')
    report = deepcopy(saved)
    slur = deepcopy(report["observations"][0])
    slur.update(construct="slur", number="7")
    report["observations"].append(slur)
    assert len(connectors(xml, report)) == 4
    assert all(r["status"] != "verified" for r in connectors(xml, report))


def test_anonymous_endpoints_use_oracle_ids_in_both_identity_spaces(tmp_path):
    pictures(tmp_path)
    xml = score().replace(' id="a"', '').replace(' id="b"', '')
    report = verify_connector_pixels(xml, tmp_path)
    assert report["complete"], report
    assert report["observations"][0]["source_ids"] == ["xml-p0-m0-e1", "xml-p0-m0-e2"]
    result = connectors(xml, report)
    assert len(result) == 2 and all(r["status"] == "verified" for r in result)


def test_original_placement_cannot_be_replaced_by_generated_default(proofs):
    xml, report = proofs["slur"]
    original = xml.replace('<slur type="start" number="7"/>',
                           '<slur type="start" number="7" placement="above"/>')
    assert all(r["status"] != "verified" for r in connectors(xml, report, original=original))


def test_onset_binding_accepts_the_producers_two_decimal_png_names(proofs):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    evidence = report["observations"][0]["evidence"]
    evidence["frame"] = f"native-{float(evidence['frame'][7:-4]):.2f}.png"
    for motion in evidence["correspondence"]:
        motion["onset_frame"] = f"native-{float(motion['onset_frame'][7:-4]):.2f}.png"
    assert all(r["status"] == "verified" for r in connectors(xml, report))


def test_a_counted_but_disconnected_curve_report_is_not_measurement_proof(proofs):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    evidence = report["observations"][0]["evidence"]
    runs = evidence["pixel_runs"]
    middle = (evidence["component_bbox"][1]+evidence["component_bbox"][3])//2
    evidence["pixel_runs"] = [r for r in runs if r[0] != middle]
    evidence["connected_pixels"] = sum(b-a for y, a, b in evidence["pixel_runs"])
    assert all(r["status"] != "verified" for r in connectors(xml, report))


@pytest.mark.parametrize("evidence", [None, [], "verified"])
def test_malformed_nonverified_evidence_cannot_crash_the_consumer(proofs, evidence):
    xml, saved = proofs["tie"]
    report = deepcopy(saved)
    report["observations"][0].update(status="unverified", evidence=evidence)
    assert all(r["status"] != "verified" for r in connectors(xml, report))
