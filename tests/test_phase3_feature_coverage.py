"""Feature evidence is bound to exact written events, never report totals."""
from pathlib import Path
import re

import pytest

from piano_teacher.notation.visual_coverage import source_inventory, visual_elements
from test_phase3_visual_coverage import score, bar, note, pitch_row, rows


def glyph(name):
    return dict(expected=name, observed=name, score=.95, runner_up=.4,
                margin=.55, bbox=[1, 2, 4, 8])


def feature_row(**changes):
    row = dict(source_id="n1", measure=1, staff="right", voice="1", beat=0.,
               spelling=["C", 0, 4], features={
                   "stem": dict(status="verified", reason="measured attached stem", evidence=dict(
                       group_id="xml-p0-m0-e1", shared_source_ids=["n1"], bbox=[4, 2, 5, 30],
                       direction="up", x=4, tip_y=2, head_matches=[.95])),
                   "flag": dict(status="verified", reason="measured flag", evidence=glyph("flag_up_1")),
                   "dot": dict(status="verified", reason="measured dots", evidence=dict(
                       expected_count=1, dots=[glyph("augmentation_dot")], bbox=[1, 2, 4, 8])),
                   "accidental": dict(status="verified", reason="measured natural", evidence=glyph("acc_natural")),
               })
    row.update(changes)
    return row


def dotted_eighth():
    return score(bar(note(kind="eighth", extra="<dot/><stem>up</stem><accidental>natural</accidental>")
                     .replace("<duration>1</duration>", "<duration>3</duration>"))
                 .replace("<divisions>1</divisions>", "<divisions>4</divisions>"))


def coverage(xml=None, generated=None, measured=None, pitches=None, **kwargs):
    xml = dotted_eighth() if xml is None else xml
    return visual_elements(xml, generated or xml,
                           dict(measured=[pitch_row()] if pitches is None else pitches), {},
                           feature_report=dict(complete=True, passed=True,
                                               coverage=dict(expected=0, verified=999),
                                               measured=[feature_row()] if measured is None else measured),
                           **kwargs)


def test_feature_totals_cannot_replace_missing_per_event_measurements():
    result = coverage(measured=[])
    assert rows(result, "pitch")[0]["status"] == "verified"
    for construct in ("stem", "flag", "dot", "accidental", "note_rhythm"):
        assert rows(result, construct)[0]["status"] == "unverified"


@pytest.mark.parametrize("field,value", [
    ("source_id", "forged"), ("measure", 2), ("staff", "left"),
    ("voice", "2"), ("beat", 1.), ("spelling", ["D", 0, 4]),
    ("spelling", None), ("beat", True), ("measure", True),
    ("spelling", ["C", False, 4]),
])
def test_forged_identity_or_coordinates_cannot_authorize_features(field, value):
    result = coverage(measured=[feature_row(**{field: value})])
    assert all(r["status"] != "verified" for r in result if r["construct"] in
               {"stem", "flag", "dot", "accidental", "note_rhythm"})


@pytest.mark.parametrize("construct", ["stem", "flag", "dot", "accidental"])
@pytest.mark.parametrize("corruption", ["missing", "ambiguous", "unverified", "empty_evidence"])
def test_missing_ambiguous_or_unmeasured_features_stay_blocking(construct, corruption):
    measurement = feature_row()
    if corruption == "missing":
        measurement["features"].pop(construct)
    elif corruption in {"ambiguous", "unverified"}:
        measurement["features"][construct]["status"] = corruption
    else:
        measurement["features"][construct]["evidence"] = {}
    result = coverage(measured=[measurement])
    assert rows(result, construct)[0]["status"] != "verified"
    if construct != "accidental":
        assert rows(result, "note_rhythm")[0]["status"] != "verified"


def test_duplicate_feature_rows_do_not_create_unique_source_evidence():
    result = coverage(measured=[feature_row(), feature_row()])
    assert all(rows(result, c)[0]["status"] != "verified"
               for c in ("stem", "flag", "dot", "accidental", "note_rhythm"))


@pytest.mark.parametrize("construct,mutate", [
    ("stem", lambda e: e.update(shared_source_ids=["other"])),
    ("stem", lambda e: e.update(direction="down")),
    ("flag", lambda e: e.update(expected="flag_up_2", observed="flag_up_2")),
    ("dot", lambda e: e.update(expected_count=2)),
    ("dot", lambda e: e.update(dots=[])),
    ("accidental", lambda e: e.update(expected="acc_sharp", observed="acc_sharp")),
])
def test_features_must_measure_the_original_required_family_and_count(construct, mutate):
    measurement=feature_row()
    mutate(measurement["features"][construct]["evidence"])
    assert rows(coverage(measured=[measurement]), construct)[0]["status"] != "verified"


def test_verified_bound_features_combine_rhythm_but_never_other_constructs():
    xml=dotted_eighth()
    result=coverage(xml)
    for construct in ("pitch", "stem", "flag", "dot", "accidental", "note_rhythm"):
        assert rows(result, construct)[0]["status"] == "verified", construct
    assert all(r["status"] == "unsupported" for r in result
               if r["construct"] not in {"pitch", "stem", "flag", "dot", "accidental", "note_rhythm"})
    assert [{k:r[k] for k in ("id", "construct", "source")} for r in result] == source_inventory(xml)


@pytest.mark.parametrize("extra", [
    '<beam number="1">begin</beam>',
    '<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>',
    '<notations><tuplet type="start"/></notations>',
])
def test_unmeasured_beam_or_tuplet_cannot_be_certified_as_note_rhythm(extra):
    xml=dotted_eighth().replace("</note>", extra+"</note>")
    result=coverage(xml)
    assert rows(result, "note_rhythm")[0]["status"] != "verified"
    assert all(r["status"] == "unsupported" for r in result if r["construct"] in {"beam", "tuplet"})


def test_generated_rhythm_changes_do_not_rewrite_original_obligations():
    original=dotted_eighth()
    generated=original.replace('<type>eighth</type>', '<type>16th</type>').replace('<dot/>', '')
    measurement=feature_row()
    measurement['features'].pop('dot')
    measurement['features']['flag']['evidence']=glyph('flag_up_2')
    result=coverage(original, generated, measured=[measurement])
    assert rows(result, 'dot') and rows(result, 'flag')
    assert all(rows(result,c)[0]['status'] != 'verified' for c in ('dot','flag','note_rhythm'))


def test_missing_source_note_retains_all_feature_rows_without_credit():
    original=dotted_eighth()
    generated=score(bar(note('D', identity='different')))
    result=coverage(original, generated, measured=[feature_row()], pitches=[])
    assert {r['id'] for r in result} >= {r['id'] for r in source_inventory(original)}
    assert all(r['status'] != 'verified' for r in result)


def test_anonymous_event_uses_independent_xml_ordinal_not_arbitrary_supplied_id():
    xml=score(bar(note(identity=None)))
    measurement=feature_row(source_id='xml-p0-m0-e1')
    measurement['features']['stem']['evidence']['shared_source_ids']=['xml-p0-m0-e1']
    result=coverage(xml, measured=[measurement], pitches=[pitch_row('anonymous')])
    assert rows(result, 'stem')[0]['status'] == 'verified'
    measurement['source_id']='forged'
    assert rows(coverage(xml, measured=[measurement]), 'stem')[0]['status'] != 'verified'


def test_window_binds_features_to_generated_clock_but_keeps_original_source_rows():
    original=score(bar(note(identity='a'), 10)+bar(note('D',identity='b'),20))
    generated=score(bar(note('D',identity='g',voice='9'),20))
    measurement=feature_row(source_id='g', measure=20, voice='9', spelling=['D',0,4])
    measurement['features']['stem']['evidence'].update(shared_source_ids=['g'])
    result=coverage(original, generated, measured=[measurement],
                    pitches=[pitch_row('g',step='D',voice='9',measure=20)], first_bar=2,last_bar=2)
    stem=rows(result,'stem')[0]
    assert stem['status']=='verified'
    assert stem['source']['id']=='b' and stem['source']['beat']==1
    measurement['beat']=1
    assert rows(coverage(original,generated,measured=[measurement], first_bar=2,last_bar=2),'stem')[0]['status']!='verified'


def test_implicit_accidentals_follow_key_measure_octave_and_cross_voice_state():
    sharp=lambda ident, voice='1', tie='': note('F',identity=ident,voice=voice,extra=tie).replace('<step>F</step>','<step>F</step><alter>1</alter>')
    xml=score(bar(sharp('key')+note('F',identity='cancel')+note('F',identity='same',voice='2')+sharp('restore'),
                  attributes='<key><fifths>1</fifths></key>')+
              bar(sharp('reset')+sharp('octave').replace('<octave>4</octave>','<octave>5</octave>'),2))
    accidental=rows(source_inventory(xml),'accidental')
    assert [r['source']['id'] for r in accidental]==['cancel','restore']
    assert all(r['source']['details']['implicit'] for r in accidental)


def test_actual_detector_explicit_and_implicit_accidentals_map_without_dropping_originals():
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder=Path(__file__).parent/'fixtures/feature_pixels/accidentals'
    xml=(folder/'source.musicxml').read_text()
    for candidate in (xml, re.sub(r'<accidental>[^<]+</accidental>', '', xml)):
        report=verify_note_feature_pixels(candidate,folder,hand='right')
        result=visual_elements(candidate,candidate,{}, {},hand='right',feature_report=report)
        assert len(rows(result,'accidental'))==8
        assert all(r['status']=='verified' for r in rows(result,'accidental'))
        assert all(r['status']=='verified' for r in rows(result,'stem'))
        assert all(r['status']!='verified' for r in rows(result,'note_rhythm'))
        assert [{k:r[k] for k in ('id','construct','source')} for r in result]==source_inventory(candidate,'right')


def test_flags_must_attach_to_the_same_measured_stem_direction():
    measurement=feature_row()
    measurement['features']['flag']['evidence']=glyph('flag_down_1')
    assert rows(coverage(measured=[measurement]),'flag')[0]['status']!='verified'


def test_captured_beam_or_tuplet_requirements_cannot_disappear_in_correspondence():
    original=score(bar(note()))
    for extra in ('<beam number="1">begin</beam>',
                  '<notations><tuplet type="start"/></notations>'):
        generated=original.replace('</note>',extra+'</note>')
        assert rows(coverage(original,generated),'note_rhythm')[0]['status']!='verified'


def test_inconsistent_written_value_cannot_be_certified_from_its_shape():
    xml=score(bar(note(kind='eighth')))
    assert rows(coverage(xml),'note_rhythm')[0]['status']!='verified'


def test_explicit_none_argument_preserves_existing_feature_statuses():
    xml=dotted_eighth()
    previous=visual_elements(xml,xml,dict(measured=[pitch_row()]),{})
    assert visual_elements(xml,xml,dict(measured=[pitch_row()]),{},feature_report=None)==previous
    assert all(r['status']=='unsupported' for r in previous if r['construct'] in
               {'stem','flag','dot','accidental','note_rhythm'})


@pytest.mark.parametrize('value', [None, [], 'verified'])
def test_malformed_feature_objects_cannot_crash_or_verify_the_ledger(value):
    measurement=feature_row()
    measurement['features']['stem']=value
    assert rows(coverage(measured=[measurement]),'stem')[0]['status']!='verified'


def test_malformed_stem_direction_cannot_crash_or_verify_the_ledger():
    measurement=feature_row()
    measurement['features']['stem']['evidence']['direction']=[]
    assert rows(coverage(measured=[measurement]),'stem')[0]['status']!='verified'


def test_independent_voices_cannot_forge_shared_chord_stem_ownership():
    xml=score(bar(note(identity='a')+'<backup><duration>1</duration></backup>'+note('E',identity='b',voice='2')))
    first=feature_row(source_id='a')
    second=feature_row(source_id='b',voice='2',spelling=['E',0,4])
    shared=dict(first['features']['stem']['evidence'], shared_source_ids=['a','b'])
    first['features']['stem']['evidence']=shared
    second['features']['stem']['evidence']=shared
    assert all(r['status']!='verified' for r in rows(coverage(xml,measured=[first,second]),'stem'))


def test_genuine_chord_report_can_verify_each_shared_source_stem():
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    folder=Path(__file__).parent/'fixtures/feature_pixels/chords'
    xml=(folder/'source.musicxml').read_text()
    report=verify_note_feature_pixels(xml,folder,hand='right')
    result=visual_elements(xml,xml,{}, {},hand='right',feature_report=report)
    assert sum(r['status']=='verified' for r in rows(result,'stem'))==24
    assert len(rows(result,'stem'))==24


def test_erased_feature_pixels_cannot_keep_verified_coverage(tmp_path):
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    from test_phase3_feature_pixels import copied, erase, feature
    folder=copied('accidentals',tmp_path)
    xml=(folder/'source.musicxml').read_text()
    before=verify_note_feature_pixels(xml,folder,hand='right')
    erase(folder,0.,feature(before,0.,'accidental')['evidence']['bbox'])
    after=verify_note_feature_pixels(xml,folder,hand='right')
    previous=visual_elements(xml,xml,{}, {},hand='right',feature_report=before)
    result=visual_elements(xml,xml,{}, {},hand='right',feature_report=after)
    assert rows(previous,'accidental')[0]['status']=='verified'
    assert rows(result,'accidental')[0]['status']!='verified'


def test_midi_transcription_keeps_its_limitation_with_feature_evidence():
    xml=dotted_eighth()
    result=visual_elements(None,xml,dict(measured=[pitch_row()]),{},
                           source_name='piece.midi',first_bar=7,last_bar=7,
                           feature_report=dict(measured=[feature_row()]))
    assert rows(result,'stem')[0]['status']=='verified'
    assert rows(result,'midi_written_transcription')[0]['status']=='unsupported'
    assert all(r['id'].startswith('w7-7:') for r in result)


def test_tied_implicit_accidental_continuation_does_not_add_an_extra_mark():
    def sharp(identity, tie):
        return note('C',identity=identity,extra=f'<tie type="{tie}"/>').replace(
            '<step>C</step>','<step>C</step><alter>1</alter>')
    xml=score(bar(sharp('start','start'))+bar(sharp('stop','stop'),2))
    assert [r['source']['id'] for r in rows(source_inventory(xml),'accidental')]==['start']
