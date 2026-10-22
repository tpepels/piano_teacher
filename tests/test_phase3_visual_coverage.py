"""Original-score expectations must survive generated/model agreement."""
from collections import Counter
import json

import pytest


def score(*bars, part_id="P1", name="Piano"):
    return (f'<score-partwise><part-list><score-part id="{part_id}">'
            f'<part-name>{name}</part-name></score-part></part-list>'
            f'<part id="{part_id}">' + "".join(bars) + '</part></score-partwise>')


def bar(notes, number=1, attributes=""):
    return (f'<measure number="{number}"><attributes><divisions>1</divisions>'
            f'{attributes}</attributes>{notes}</measure>')


def note(step="C", *, identity="n1", voice="1", staff="1", extra="", kind="quarter"):
    xml_id = f' id="{identity}"' if identity else ""
    return (f'<note{xml_id}><pitch><step>{step}</step><octave>4</octave></pitch>'
            f'<duration>1</duration><voice>{voice}</voice><type>{kind}</type>'
            f'<staff>{staff}</staff>{extra}</note>')


def rest(*, identity="r1", kind="quarter", extra="", voice="1"):
    xml_id = f' id="{identity}"' if identity else ""
    return (f'<note{xml_id}><rest/><duration>1</duration><voice>{voice}</voice>'
            f'<type>{kind}</type>{extra}</note>')


def pitch_row(identity="n1", *, step="C", beat=0, voice="1", measure=1, status="verified"):
    return dict(source_id=identity, measure=measure, beat=beat, voice=voice,
                staff="right", spelling=[step, 0, 4], status=status,
                glyph="head_black", match=.95)


def rest_row(identity="r1", *, beat=0, kind="quarter", status="verified"):
    return dict(source_id=identity, measure=1, beat=beat, staff="right", voice="1",
                required_rest=kind, status=status, shape_match=.9,
                changed_pixels=40, delta_file="removed.png")


def ledger(original, generated=None, *, pitches=(), rests=(), **kwargs):
    from piano_teacher.notation.visual_coverage import visual_elements
    return visual_elements(original, generated if generated is not None else original,
                           {"passed": True, "measured": list(pitches)},
                           {"passed": True, "measured": list(rests)}, **kwargs)


def rows(elements, construct):
    return [row for row in elements if row["construct"] == construct]


def test_pitch_witness_does_not_verify_rhythm_stem_flag_or_dot():
    xml = score(bar(note(kind="eighth", extra="<dot/><stem>up</stem>")))
    elements = ledger(xml, pitches=[pitch_row()])
    assert rows(elements, "pitch")[0]["status"] == "verified"
    for construct in ("note_rhythm", "stem", "flag", "dot"):
        assert rows(elements, construct)
        assert {r["status"] for r in rows(elements, construct)} == {"unsupported"}


def test_original_note_lost_from_generated_is_still_a_mismatch():
    original = score(bar(note() + note("D", identity="n2")))
    generated = score(bar(note()))
    elements = ledger(original, generated, pitches=[pitch_row()])
    missing = next(r for r in rows(elements, "pitch") if r["source"]["id"] == "n2")
    assert missing["status"] == "mismatch"
    assert missing["source"]["beat"] == 1


def test_generated_and_pixel_agreement_cannot_rewrite_original_pitch():
    elements = ledger(score(bar(note())), score(bar(note("D"))),
                      pitches=[pitch_row(step="D")])
    source = next(r for r in rows(elements, "pitch") if r["source"].get("origin") != "generated_extra")
    assert source["source"]["spelling"] == ["C", 0, 4]
    assert source["status"] == "mismatch"
    assert not any(r["status"] == "verified" for r in elements)


def test_report_success_and_counts_cannot_replace_missing_pixel_row():
    elements = ledger(score(bar(note())))
    assert rows(elements, "pitch")[0]["status"] == "unverified"


@pytest.mark.parametrize("status", ["ambiguous", "unsupported", "unverified", "mismatch"])
def test_individual_pitch_status_is_preserved(status):
    elements = ledger(score(bar(note())), pitches=[pitch_row(status=status)])
    assert rows(elements, "pitch")[0]["status"] == status


def test_status_alone_without_a_measured_glyph_is_not_proof():
    pixel = pitch_row()
    pixel.pop("match")
    elements = ledger(score(bar(note())), pitches=[pixel])
    assert rows(elements, "pitch")[0]["status"] == "unverified"


def test_original_only_beams_rests_and_notations_are_not_dropped():
    source_note = note(kind="eighth", extra=(
        '<beam number="1">begin</beam><notations><slur type="start"/>'
        '<tuplet type="start"/><articulations><staccato/></articulations></notations>'
        '<accidental>natural</accidental>'))
    original = score(bar(source_note + rest(extra="<dot/>"), attributes=(
        '<clef><sign>G</sign><line>2</line></clef><key><fifths>1</fifths></key>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>')))
    elements = ledger(original, score(bar(note())))
    for construct in ("beam", "slur", "tuplet", "staccato", "accidental", "clef", "key", "meter", "barline"):
        assert rows(elements, construct), construct
        assert {r["status"] for r in rows(elements, construct)} == {"unsupported"}
    assert rows(elements, "rest")[0]["status"] == "mismatch"
    assert rows(elements, "rest_placement")[0]["status"] == "unsupported"


def test_window_is_by_original_index_and_generated_beats_are_relative():
    original = score(bar(note(), 10) + bar(note("D", identity="n2"), 20)
                     + bar(note("E", identity="n3"), 30))
    generated = score(bar(note("D", identity="generated", voice="9"), 20))
    elements = ledger(original, generated, pitches=[pitch_row("generated", step="D", voice="9", measure=20)],
                      first_bar=2, last_bar=2)
    pitches = rows(elements, "pitch")
    assert len(pitches) == 1
    assert pitches[0]["source"]["id"] == "n2"
    assert pitches[0]["source"]["measure"] == 20
    assert pitches[0]["source"]["beat"] == 1
    assert pitches[0]["status"] == "verified"


def test_omitted_last_bar_defaults_to_generated_window_length():
    original = score(bar(note()) + bar(note("D", identity="n2"), 2) + bar(note("E", identity="n3"), 3))
    elements = ledger(original, score(bar(note("D", identity="n2"), 2)), first_bar=2)
    assert [r["source"]["id"] for r in rows(elements, "pitch")] == ["n2"]


def test_explicit_window_keeps_source_bars_missing_from_generated():
    original = score(bar(note()) + bar(rest(), 2))
    elements = ledger(original, score(bar(note())), first_bar=1, last_bar=2)
    assert rows(elements, "rest")[0]["status"] == "mismatch"
    assert {r["source"]["measure"] for r in rows(elements, "measure")} == {1, 2}


def test_one_generated_note_or_pixel_record_cannot_cover_two_unisons():
    duplicate = note(identity="a") + '<backup><duration>1</duration></backup>' + note(identity="b", voice="2")
    original = score(bar(duplicate))
    generated = score(bar(note(identity="generated", voice="9")))
    elements = ledger(original, generated, pitches=[pitch_row("generated", voice="9")])
    assert Counter(r["status"] for r in rows(elements, "pitch")) == {"verified": 1, "mismatch": 1}
    generated = score(bar(duplicate))
    elements = ledger(original, generated, pitches=[pitch_row("a")])
    assert Counter(r["status"] for r in rows(elements, "pitch")) == {"verified": 1, "unverified": 1}


def test_ordinal_source_ids_are_stable_across_windows_and_unique():
    original = score(bar(note(identity=None) + note(identity=None))
                     + bar(note(identity=None), 2))
    whole = ledger(original)
    window = ledger(original, score(bar(note(identity=None), 2)), first_bar=2, last_bar=2)
    assert rows(whole, "pitch")[2]["source"]["id"] == rows(window, "pitch")[0]["source"]["id"]
    assert len({r["id"] for r in whole}) == len(whole)
    assert len({r["source"]["id"] for r in rows(whole, "pitch")}) == 3


def test_anonymous_rest_matches_report_fallback_identity_by_coordinates():
    xml = score(bar(rest(identity=None)))
    elements = ledger(xml, rests=[rest_row("measure-1-voice-1-rest-0")])
    assert rows(elements, "rest")[0]["status"] == "verified"
    assert rows(elements, "rest_placement")[0]["status"] == "unsupported"


@pytest.mark.parametrize("kind", ["half", "whole"])
def test_rectangular_rest_contour_remains_ambiguous(kind):
    xml = score(bar(rest(kind=kind)))
    elements = ledger(xml, rests=[rest_row(kind=kind)])
    assert rows(elements, "rest")[0]["status"] == "ambiguous"


def test_changed_rest_type_is_a_mismatch_despite_successful_generated_contour():
    elements = ledger(score(bar(rest())), score(bar(rest(kind="eighth"))),
                      rests=[rest_row(kind="eighth")])
    assert rows(elements, "rest")[0]["status"] == "mismatch"


def test_tied_continuation_noteheads_each_require_evidence():
    original = score(bar(note(extra='<tie type="start"/><notations><tied type="start"/></notations>'))
                     + bar(note(identity="n2", extra='<tie type="stop"/><notations><tied type="stop"/></notations>'), 2))
    elements = ledger(original, pitches=[pitch_row(), pitch_row("n2", beat=1, measure=2)])
    assert len(rows(elements, "pitch")) == 2
    assert all(r["status"] == "verified" for r in rows(elements, "pitch"))
    assert len(rows(elements, "tie")) == 2
    assert all(r["status"] == "unsupported" for r in rows(elements, "tie"))


def test_left_hand_filter_understands_separate_lh_part_staff_one():
    original = score(bar(note()), part_id="LH", name="Left hand")
    pixel = dict(pitch_row(), staff="left")
    assert rows(ledger(original, pitches=[pixel], hand="left"), "pitch")[0]["status"] == "verified"
    assert not rows(ledger(original, hand="right"), "pitch")


def test_midi_reports_written_transcription_and_explicit_limitation():
    elements = ledger(None, score(bar(note())), pitches=[pitch_row()], source_name="example.midi", first_bar=5, last_bar=5)
    assert rows(elements, "pitch")[0]["status"] == "verified"
    assert rows(elements, "pitch")[0]["source"]["source_name"] == "example.midi"
    limitation = rows(elements, "midi_written_transcription")
    assert len(limitation) == 1
    assert limitation[0]["status"] == "unsupported"
    assert limitation[0]["source"]["id"]


def test_counts_are_aggregator_schema_and_ledger_is_json_serializable():
    from piano_teacher.notation.visual_coverage import coverage_counts
    elements = ledger(score(bar(note())), pitches=[pitch_row()])
    counts = coverage_counts(elements)
    assert set(counts) == {"expected", "verified", "ambiguous", "unsupported", "unverified", "mismatch"}
    assert counts["expected"] == len(elements)
    assert counts["verified"] == 1
    assert counts["unsupported"] == len(elements) - 1
    assert sum(v for k, v in counts.items() if k != "expected") == counts["expected"]
    assert json.loads(json.dumps(elements)) == elements
    assert coverage_counts([]) == dict(expected=0, verified=0, ambiguous=0, unsupported=0, unverified=0, mismatch=0)


def test_source_inventory_is_exactly_the_original_projection_across_windows():
    from piano_teacher.notation.visual_coverage import source_inventory
    original = score(bar(note(), 10) + bar(note("D", identity=None), 20))
    first = ledger(original, score(bar(note(), 10)), first_bar=1, last_bar=1)
    second = ledger(original, score(bar(note("D", identity=None), 20)), first_bar=2, last_bar=2)
    projection = [{key: row[key] for key in ("id", "construct", "source")} for row in first + second]
    assert projection == source_inventory(original)


def test_midi_inventory_exposes_required_sentinel_without_generated_score():
    from piano_teacher.notation.visual_coverage import source_inventory
    inventory = source_inventory(None, "left", source_name="example.midi")
    assert inventory == [{"id": "midi-written-transcription", "construct": "midi_written_transcription",
                          "source": {"id": "midi-written-transcription", "source_name": "example.midi",
                                     "origin": "midi", "staff": "left"}}]


def test_blank_absent_hand_rest_is_unsupported_scaffolding_not_a_source_error():
    original = score(bar(note()), part_id="RH", name="Right hand")
    generated = original.replace('</score-partwise>',
        '<part id="LH"><measure number="1"><attributes><divisions>1</divisions>'
        '</attributes>' + rest() + '</measure></part></score-partwise>')
    elements = ledger(original, generated, pitches=[pitch_row()])
    scaffolds = rows(elements, "staff_scaffolding")
    assert len(scaffolds) == 1
    assert scaffolds[0]["status"] == "unsupported"
    assert scaffolds[0]["source"]["staff"] == "left"
    assert not any(r["status"] == "mismatch" for r in elements)


def test_extra_note_on_absent_hand_remains_a_mismatch():
    original = score(bar(note()), part_id="RH")
    generated = original.replace('</score-partwise>',
        '<part id="LH">' + bar(note(identity="extra")) + '</part></score-partwise>')
    elements = ledger(original, generated)
    extra = next(r for r in elements if r["source"].get("origin") == "generated_extra")
    assert extra["construct"] == "pitch"
    assert extra["status"] == "mismatch"


def test_missing_authored_rest_cannot_be_excused_as_scaffolding():
    original = score(bar(note() + rest()))
    elements = ledger(original, score(bar(note())))
    assert rows(elements, "rest")[0]["status"] == "mismatch"


@pytest.mark.parametrize("field,value", [("measure", 50), ("glyph", "stem")])
def test_inconsistent_pixel_identity_or_non_head_glyph_cannot_verify_pitch(field, value):
    pixel = dict(pitch_row(), **{field: value})
    assert rows(ledger(score(bar(note())), pitches=[pixel]), "pitch")[0]["status"] == "unverified"


def test_unpitched_note_is_explicitly_unsupported_without_shifting_pitched_facts():
    unpitched = ('<note><unpitched><display-step>C</display-step><display-octave>4</display-octave>'
                 '</unpitched><duration>1</duration><type>quarter</type></note>')
    xml = score(bar(unpitched + note()))
    elements = ledger(xml, pitches=[pitch_row(beat=1)])
    assert rows(elements, "unpitched")[0]["status"] == "unsupported"
    assert rows(elements, "pitch")[0]["source"]["beat"] == 1
    assert rows(elements, "pitch")[0]["status"] == "verified"


def test_window_tie_endpoints_do_not_invalidate_independent_notehead_timing():
    original = score(bar(note(extra='<tie type="start"/>'))
                     + bar(note(identity="n2", extra='<tie type="stop"/>'), 2))
    generated = score(bar(note(identity="n2", extra='<tie type="stop"/>'), 2))
    elements = ledger(original, generated, first_bar=2, last_bar=2,
                      pitches=[pitch_row("n2", measure=2)])
    assert rows(elements, "pitch")[0]["status"] == "verified"
    assert rows(elements, "tie")[0]["status"] == "unsupported"


def test_tuplet_window_subtraction_preserves_fractional_onsets():
    def triplet_bar(notes, number):
        return bar(notes, number).replace('<divisions>1</divisions>', '<divisions>3</divisions>')
    original = score(triplet_bar(note(identity="a"), 1)
                     + triplet_bar(note(identity="b") + note("D", identity="c"), 2))
    generated = score(triplet_bar(note(identity="b") + note("D", identity="c"), 2))
    elements = ledger(original, generated, first_bar=2, last_bar=2,
                      pitches=[pitch_row("b", measure=2), pitch_row("c", step="D", beat=1/3, measure=2)])
    assert [r["status"] for r in rows(elements, "pitch")] == ["verified", "verified"]


def test_integral_decimal_alteration_uses_the_oracles_written_spelling():
    original = score(bar(note().replace('<step>C</step>', '<step>C</step><alter>1.0</alter>')))
    generated = score(bar(note().replace('<step>C</step>', '<step>C</step><alter>1</alter>')))
    pixel = dict(pitch_row(), spelling=["C", 1, 4])
    elements = ledger(original, generated, pitches=[pixel])
    assert len(rows(elements, "pitch")) == 1
    assert rows(elements, "pitch")[0]["status"] == "verified"
    assert rows(elements, "pitch")[0]["source"]["spelling"] == ["C", 1, 4]
