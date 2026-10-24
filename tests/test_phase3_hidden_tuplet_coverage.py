"""Explicitly hidden ratios are semantic facts, never fabricated glyph proofs."""
from copy import deepcopy
from pathlib import Path
from shutil import copyfile
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.semantic_contract import verify_generated_contract
from piano_teacher.notation.visual_coverage import source_inventory, visual_elements


def chosen_xml(*, start=' bracket="no" show-number="none"', stop=True, duration=19):
    end = '<tuplet type="stop" number="1"/>' if stop else ''
    return f'''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>20</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="q"><pitch><step>C</step><octave>4</octave></pitch><duration>{duration}</duration>
    <voice>1</voice><type>quarter</type><time-modification><actual-notes>20</actual-notes>
    <normal-notes>19</normal-notes></time-modification><notations>
    <tuplet type="start" number="1"{start}/>{end}</notations></note></measure></part></score-partwise>'''


def native_model():
    # Literal, independently calculated native event: a quarter at 20:19 is
    # 19/20 beat. The parser/consumer under test does not construct this model.
    return dict(measures=[dict(number=1, start_beat=0.)], notation_events=[dict(
        id="q", staff="right", voice="1", measure=1, beat=0., duration_beats=.95,
        kind="note", midi_pitch=60, spelling=dict(step="C", alter=0, octave=4),
        note_type="quarter", dots=0, chord=False, accidental=None, beams=[],
        tie_start=False, tie_stop=False, tied_marks=[],
        time_modification=dict(actual=20, normal=19),
        tuplet_marks=[dict(type="start", number="1", bracket="no", show_number="none"),
                      dict(type="stop", number="1", bracket="no", show_number="actual")],
        tuplet_extras=[[], []])])


@pytest.fixture(scope="module")
def proof(tmp_path_factory):
    folder = tmp_path_factory.mktemp("hidden-ratio")
    copyfile(Path(__file__).parent/"fixtures/feature_pixels/rhythms/native-6.00000.png",
             folder/"native-0.00000.png")
    xml = chosen_xml()
    feature = verify_note_feature_pixels(xml, folder, hand="right")
    pitch = verify_all_notehead_pixels(xml, folder, hand="right")
    assert pitch["complete"]
    assert feature["complete"], feature
    semantic = verify_generated_contract(xml, native_model())
    assert semantic["complete"], semantic
    return folder, feature, pitch, semantic


def ledger(proof, *, xml=None, original=None, semantic=None, feature=None, **kwargs):
    _folder, features, pitches, semantics = proof
    xml = xml or chosen_xml()
    return visual_elements(original, xml, pitches, {}, hand="right", feature_report=feature or features,
                           semantic_report=semantics if semantic is None else semantic, **kwargs)


def rhythm(rows):
    return next(r for r in rows if r["construct"] == "note_rhythm")


def tuplets(rows):
    return [r for r in rows if r["construct"] == "tuplet"]


@pytest.mark.parametrize("original", [None, chosen_xml()])
def test_hidden_19_20_quarter_combines_semantics_with_actual_head_stem_and_absent_flag(proof, original):
    rows = ledger(proof, original=original)
    metadata = tuplets(rows)
    assert len(metadata) == 3
    assert all(r["scope"] == "semantic" and r["status"] == "verified" for r in metadata), metadata
    assert all(r["evidence"]["kind"] == "semantic" and "pixel" not in r["evidence"] for r in metadata)
    result = rhythm(rows)
    assert result["status"] == "verified", result
    assert result["evidence"]["expected_duration"] == "19/20"
    assert result["evidence"]["flag_absence"]["status"] == "verified"


def test_hidden_inventory_scope_is_source_derived_without_incoming_authority(proof):
    inventory = tuplets(source_inventory(chosen_xml(), "right"))
    assert len(inventory) == 3 and all(r["scope"] == "semantic" for r in inventory)
    rows = visual_elements(None, chosen_xml(), proof[2], {}, feature_report=proof[1])
    assert all(r["status"] != "verified" for r in tuplets(rows))
    assert rhythm(rows)["status"] != "verified"


@pytest.mark.parametrize("mutate", [
    lambda e: e["time_modification"].update(actual=21),
    lambda e: e["time_modification"].update(normal=18),
    lambda e: e.update(duration_beats=1.),
    lambda e: e.update(id="other"),
    lambda e: e.update(voice="2"),
    lambda e: e.update(note_type="half"),
    lambda e: e["tuplet_marks"][0].update(show_number="actual"),
    lambda e: e["tuplet_marks"][0].update(bracket="yes"),
    lambda e: e["tuplet_marks"][1].update(number="2"),
    lambda e: e["tuplet_marks"].pop(),
])
def test_native_model_tamper_blocks_semantic_metadata_and_rhythm(proof, mutate):
    model = native_model()
    mutate(model["notation_events"][0])
    semantic = verify_generated_contract(chosen_xml(), model)
    rows = ledger(proof, semantic=semantic)
    assert all(r["status"] != "verified" for r in tuplets(rows))
    assert rhythm(rows)["status"] != "verified"


@pytest.mark.parametrize("change", [
    lambda x: x.replace('<actual-notes>20</actual-notes>', '<actual-notes>21</actual-notes>'),
    lambda x: x.replace('<normal-notes>19</normal-notes>', '<normal-notes>18</normal-notes>'),
    lambda x: x.replace('show-number="none"', 'show-number="actual"'),
    lambda x: x.replace('bracket="no"', 'bracket="yes"'),
    lambda x: x.replace('<tuplet type="stop" number="1"/>', ''),
])
def test_original_ratio_and_hiding_policy_cannot_be_rewritten_by_generated_agreement(proof, change):
    rows = ledger(proof, original=change(chosen_xml()))
    assert rhythm(rows)["status"] != "verified"


@pytest.mark.parametrize("xml", [
    chosen_xml(start=' show-number="none"'),  # Default no is not explicit no.
    chosen_xml(start=' bracket="no"'),
    chosen_xml(stop=False),
    chosen_xml().replace('<tuplet type="stop" number="1"/>', '<tuplet type="stop" number="2"/>'),
    chosen_xml().replace('<tuplet type="stop" number="1"/>', '<tuplet type="stop" number="1" bracket="yes"/>'),
])
def test_unpaired_implicit_or_contradictory_hiding_is_not_a_graphics_exemption(proof, xml):
    rows = ledger(proof, xml=xml)
    assert rhythm(rows)["status"] != "verified"
    assert any(r.get("scope") != "semantic" or r["status"] != "verified" for r in tuplets(rows))


@pytest.mark.parametrize("semantic", [{}, {"complete": True, "passed": True},
                                      {"elements": [{"status": "verified"}]}])
def test_aggregate_or_unbound_semantic_status_never_authorizes(proof, semantic):
    rows = ledger(proof, semantic=semantic)
    assert rhythm(rows)["status"] != "verified"


@pytest.mark.parametrize("mode", ["duplicate", "other-source", "other-context", "other-boundary", "both-payloads", "missing"])
def test_contract_rows_bind_source_context_and_actual_expected_payloads(proof, mode):
    report = deepcopy(proof[3])
    row = next(r for r in report["elements"] if r["construct"] == "tuplets")
    if mode == "duplicate":
        report["elements"].append(deepcopy(row))
    elif mode == "other-source":
        row["source"]["id"] = "foreign"
    elif mode == "other-context":
        row["source"]["staff"] = "2"
    elif mode == "other-boundary":
        row["boundary"] = "original->native"
    elif mode == "both-payloads":
        row["expected"]["time_modification"] = [3, 2]
        row["actual"]["time_modification"] = [3, 2]
    else:
        report["elements"].remove(row)
    assert rhythm(ledger(proof, semantic=report))["status"] != "verified"


@pytest.mark.parametrize("construct", ["stem", "flag_absence"])
def test_hidden_ratio_cannot_bypass_required_quarter_graphics(proof, construct):
    feature = deepcopy(proof[1])
    feature["measured"][0]["features"][construct]["status"] = "unverified"
    assert rhythm(ledger(proof, feature=feature))["status"] != "verified"


def test_exact_arithmetic_is_required_even_when_xml_and_model_agree(proof):
    xml = chosen_xml(duration=20)
    model = native_model()
    model["notation_events"][0]["duration_beats"] = 1.
    report = verify_generated_contract(xml, model)
    assert rhythm(ledger(proof, xml=xml, semantic=report))["status"] != "verified"


@pytest.mark.parametrize("tamper", [None, "ratio", "missing-member"])
def test_every_member_of_a_hidden_group_needs_its_own_native_contract(proof, tmp_path, tamper):
    root = ET.fromstring(chosen_xml())
    measure = root.find("part/measure")
    first = measure.find("note")
    first.find("notations").remove(first.find('notations/tuplet[@type="stop"]'))
    second = deepcopy(first)
    second.set("id", "r")
    second.find("notations").clear()
    ET.SubElement(second.find("notations"), "tuplet", type="stop", number="1")
    measure.append(second)
    xml = ET.tostring(root, encoding="unicode")
    for beat in (0., .95):
        copyfile(proof[0]/"native-0.00000.png", tmp_path/f"native-{beat:.5f}.png")
    feature = verify_note_feature_pixels(xml, tmp_path, hand="right")
    pitch = verify_all_notehead_pixels(xml, tmp_path, hand="right")
    model = native_model()
    a = model["notation_events"][0]
    a["tuplet_marks"] = a["tuplet_marks"][:1]
    a["tuplet_extras"] = [[]]
    b = deepcopy(a)
    b.update(id="r", beat=.95, tuplet_marks=[dict(type="stop", number="1", bracket="no", show_number="actual")])
    model["notation_events"].append(b)
    if tamper == "ratio":
        b["time_modification"]["actual"] = 21
    elif tamper == "missing-member":
        model["notation_events"].pop()
    semantic = verify_generated_contract(xml, model)
    rows = visual_elements(None, xml, pitch, {}, feature_report=feature, semantic_report=semantic)
    rhythms = [r for r in rows if r["construct"] == "note_rhythm"]
    metadata = tuplets(rows)
    assert len(rhythms) == 2 and len(metadata) == 4
    assert all((r["status"] == "verified") == (tamper is None) for r in [*rhythms, *metadata])


def test_hidden_group_in_a_source_window_binds_generated_clock_voice_and_ids(proof):
    original = chosen_xml().replace('id="q"', 'id="authored"').replace('<voice>1</voice>', '<voice>7</voice>')
    original = original.replace('<measure number="1">',
        '<measure number="0"><attributes><divisions>20</divisions></attributes>'
        '<note><rest/><duration>20</duration><type>quarter</type></note></measure><measure number="1">')
    rows = ledger(proof, original=original, first_bar=2, last_bar=2)
    assert rhythm(rows)["status"] == "verified"
    assert rhythm(rows)["source"]["id"] == "authored"
    assert rhythm(rows)["source"]["beat"] == 1.


def test_source_model_agreement_cannot_reinterpret_an_actual_flag_as_quarter_absence(proof, tmp_path):
    copyfile(Path(__file__).parent/"fixtures/feature_pixels/rhythms/native-7.00000.png",
             tmp_path/"native-0.00000.png")
    feature = verify_note_feature_pixels(chosen_xml(), tmp_path, hand="right")
    assert feature["measured"][0]["features"]["flag_absence"]["status"] != "verified"
    assert rhythm(ledger(proof, feature=feature))["status"] != "verified"


def test_semantically_valid_dotted_value_still_requires_an_actual_dot(proof):
    xml = chosen_xml(duration=57).replace('<divisions>20</divisions>', '<divisions>40</divisions>')
    xml = xml.replace('<type>quarter</type>', '<type>quarter</type><dot/>')
    model = native_model()
    model["notation_events"][0].update(dots=1, duration_beats=1.425)
    semantic = verify_generated_contract(xml, model)
    assert semantic["complete"], semantic
    result = ledger(proof, xml=xml, semantic=semantic)
    assert all(r["status"] == "verified" for r in tuplets(result))
    assert rhythm(result)["status"] != "verified"


def test_nonprinting_member_cannot_silently_disappear_from_hidden_group_ownership(proof, tmp_path):
    root = ET.fromstring(chosen_xml())
    measure = root.find("part/measure")
    first = measure.find("note")
    first.find("notations").remove(first.find('notations/tuplet[@type="stop"]'))
    hidden = deepcopy(first)
    hidden.set("id", "nonprinting")
    hidden.set("print-object", "no")
    hidden.find("notations").clear()
    last = deepcopy(hidden)
    last.set("id", "s")
    last.attrib.pop("print-object")
    ET.SubElement(last.find("notations"), "tuplet", type="stop", number="1")
    measure.extend([hidden, last])
    xml = ET.tostring(root, encoding="unicode")
    for beat in (0., 1.9):
        copyfile(proof[0]/"native-0.00000.png", tmp_path/f"native-{beat:.5f}.png")
    model = native_model()
    a = model["notation_events"][0]
    a.update(tuplet_marks=a["tuplet_marks"][:1], tuplet_extras=[[]])
    b = deepcopy(a)
    b.update(id="s", beat=1.9, tuplet_marks=[dict(type="stop", number="1", bracket="no", show_number="actual")])
    model["notation_events"].append(b)
    semantic = verify_generated_contract(xml, model)
    assert semantic["complete"], semantic
    rows = visual_elements(None, xml, verify_all_notehead_pixels(xml, tmp_path, hand="right"), {},
        feature_report=verify_note_feature_pixels(xml, tmp_path, hand="right"), semantic_report=semantic)
    assert all(r["status"] != "verified" for r in rows if r["construct"] == "note_rhythm")
