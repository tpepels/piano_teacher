"""Hand-authored beam facts exercise each semantic boundary independently."""
from copy import deepcopy
import json
from xml.etree import ElementTree as ET

import mido
import pytest

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import LessonScore
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation import semantic_contract as contract


def example():
    # Two quarter beats: four sixteenths and a quarter, over a half rest.
    # Beam 1 spans all four sixteenths; beam 2 makes two separate pairs.
    # These are literal, hand-calculated expectations, not parser output.
    specs = [
        ('C', 72, 0., .25, '16th', [['1', 'begin', []], ['2', 'begin', []]]),
        ('D', 74, .25, .25, '16th', [['1', 'continue', []], ['2', 'end', []]]),
        ('E', 76, .5, .25, '16th', [['1', 'continue', []], ['2', 'begin', []]]),
        ('F', 77, .75, .25, '16th', [['1', 'end', []], ['2', 'end', []]]),
        ('G', 79, 1., 1., 'quarter', []),
    ]
    xml_notes, notes, events = [], [], []
    for i, (step, pitch, beat, duration, typ, beams) in enumerate(specs):
        beam_xml = ''.join(f'<beam number="{level}">{value}</beam>'
                           for level, value, _ in beams)
        xml_notes.append(f'<note id="g{i}"><pitch><step>{step}</step><octave>5</octave>'
                         f'</pitch><duration>{round(duration*10080)}</duration><voice>7</voice>'
                         f'<type>{typ}</type>{beam_xml}</note>')
        source_id = f'xml-p0-m0-e{i+1}'
        notes.append(dict(id=source_id, onset_beats=beat, duration_beats=duration,
                          midi_pitch=pitch, velocity=85, hand='right',
                          voice='xml-p0-s1-v7', track=0, channel=0,
                          spelling=[step, 0, 5]))
        events.append(dict(id=f'g{i}', source_id=source_id, staff='right', voice='1',
                           measure=1, beat=beat, duration_beats=duration, kind='note',
                           midi_pitch=pitch, spelling=dict(step=step, alter=0, octave=5),
                           note_type=typ, dots=0, chord=False, tie_start=False,
                           tie_stop=False, is_attack=True, accidental=None,
                           time_modification=None, tuplet_marks=[], beams=deepcopy(beams),
                           tied_marks=[], tuplet_extras=[]))
    attributes = ('<attributes><divisions>10080</divisions><key><fifths>0</fifths></key>'
                  '<time><beats>2</beats><beat-type>4</beat-type></time>'
                  '<clef><sign>{sign}</sign><line>{line}</line></clef></attributes>')
    original = ('<score-partwise><part-list>'
                '<score-part id="RH"><part-name>Right Hand</part-name></score-part>'
                '<score-part id="LH"><part-name>Left Hand</part-name></score-part>'
                '</part-list><part id="RH"><measure number="1">' +
                attributes.format(sign='G', line=2) + ''.join(xml_notes) +
                '</measure></part><part id="LH"><measure number="1">' +
                attributes.format(sign='F', line=4) +
                '<note><rest/><duration>20160</duration><voice>9</voice><type>half</type>'
                '</note></measure></part></score-partwise>')
    generated = original.replace('<voice>7</voice>', '<voice>1</voice>').replace(
        '<voice>9</voice>', '<voice>1</voice>')
    events.append(dict(id='rest:left:1:5', source_id=None, staff='left', voice='1',
                       measure=1, beat=0., duration_beats=2., kind='rest', midi_pitch=None,
                       spelling=None, note_type='half', dots=0, chord=False,
                       tie_start=False, tie_stop=False, is_attack=False, accidental=None,
                       time_modification=None, tuplet_marks=[], beams=[],
                       tied_marks=[], tuplet_extras=[]))
    model = dict(notes=notes, notation_events=events, active_hand='both',
                 active_note_ids=[n['id'] for n in notes], measures=[dict(
                     number=1, start_beat=0., end_beat=2., meter=[2, 4],
                     keys=dict(right=0, left=0), clefs=dict(
                         right=dict(sign='G', line=2, octave_change=0),
                         left=dict(sign='F', line=4, octave_change=0)))])
    return original, generated, model


def audit(original, generated, model):
    return contract.verify_musicxml_contract(original, generated, model)


def beam_rows(report, boundary):
    return [e for e in report['elements'] if e['construct'] == 'beams'
            and e['boundary'] == boundary and e['source']['id'] != 'score:beam-metadata']


def sentinel(report):
    return next(e for e in report['elements'] if e['source']['id'] == 'score:beam-metadata')


def test_model_preserves_levels_hooks_attributes_and_explicit_absence_as_json():
    _, generated, handmade = example()
    root = ET.fromstring(generated)
    first = root.find('.//beam')
    first.attrib.pop('number')  # MusicXML defaults the first level to 1.
    first.set('fan', 'accel')
    first.set('color', '#123456')
    first.text = ' begin '
    root.findall('.//beam')[1].text = 'forward hook'
    root.findall('.//beam')[3].text = 'backward hook'
    phrase = Phrase(1, 1, 1, 0., 2., tuple(
        Note(n['onset_beats'], n['onset_beats'] + n['duration_beats'], n['midi_pitch'],
             0, 0, 'right', n['id'], voice=n['voice'], spelling=tuple(n['spelling']))
        for n in handmade['notes']))
    bindings = {e['id']: dict(source_id=e['source_id'], pitch=e['midi_pitch'],
                             hand='right', display_beat=e['beat'], source_beat=e['beat'],
                             is_attack=True)
                for e in handmade['notation_events'] if e['kind'] == 'note'}
    score = LessonScore(ET.tostring(root, encoding='unicode'), phrase, bindings)
    model = build_score_model(score, boundaries=(0., 2.))
    assert [e.get('beams') for e in model['notation_events']] == [
        [['1', 'begin', [['color', '#123456'], ['fan', 'accel']]], ['2', 'forward hook', []]],
        [['1', 'continue', []], ['2', 'backward hook', []]],
        [['1', 'continue', []], ['2', 'begin', []]],
        [['1', 'end', []], ['2', 'end', []]], [], [],
    ]
    assert json.loads(json.dumps(model)) == model
    result = contract.verify_generated_contract(score.musicxml, model)
    assert result['complete'], result


def test_explicit_beams_and_absence_are_verified_at_all_boundaries():
    result = audit(*example())
    assert result['complete'], result
    assert sentinel(result)['status'] == 'verified'
    for boundary in ('original->generated', 'original->native', 'generated->native'):
        rows = beam_rows(result, boundary)
        assert len(rows) == 6
        assert {r['status'] for r in rows} == {'verified'}
        assert rows[4]['expected'] == rows[4]['actual'] == []
        assert rows[5]['expected'] == rows[5]['actual'] == []


@pytest.mark.parametrize('mutation', ['membership', 'level', 'missing_level', 'all_missing', 'attributes',
                                     'extra_note_beam', 'extra_rest_beam'])
@pytest.mark.parametrize('shared_generated', [False, True])
def test_original_catches_wrong_native_beams_even_when_generated_agrees(mutation, shared_generated):
    original, generated, model = example()
    root = ET.fromstring(generated)
    event = model['notation_events'][0]
    node = root.find('.//note')
    if mutation == 'membership':
        event['beams'][0][1] = 'end'
        node.find('beam').text = 'end'
    elif mutation == 'level':
        event['beams'][1][0] = '3'
        node.findall('beam')[1].set('number', '3')
    elif mutation == 'missing_level':
        event['beams'].pop()
        node.remove(node.findall('beam')[1])
    elif mutation == 'all_missing':
        event['beams'] = []
        for beam in node.findall('beam'):
            node.remove(beam)
    elif mutation == 'attributes':
        event['beams'][0][2] = [['fan', 'rit']]
        node.find('beam').set('fan', 'rit')
    else:
        index = 4 if mutation == 'extra_note_beam' else 5
        event = model['notation_events'][index]
        event['beams'] = [['1', 'begin', []]]
        ET.SubElement(root.findall('.//note')[index], 'beam', number='1').text = 'begin'
    if shared_generated:
        generated = ET.tostring(root, encoding='unicode')
    result = audit(original, generated, model)
    assert not result['passed']
    failures = [r for r in beam_rows(result, 'original->native') if r['status'] == 'mismatch']
    assert len(failures) == 1, result
    assert failures[0]['expected'] != failures[0]['actual']
    generated_failures = [r for r in beam_rows(result, 'generated->native') if r['status'] == 'mismatch']
    assert len(generated_failures) == (0 if shared_generated else 1), result
    generated_only = contract.verify_generated_contract(generated, model)
    assert generated_only['passed'] is shared_generated


def test_wrong_original_beam_is_compared_to_native_independently():
    original, generated, model = example()
    root = ET.fromstring(original)
    root.find('.//beam').text = 'continue'
    result = audit(ET.tostring(root, encoding='unicode'), generated, model)
    assert any(r['status'] == 'mismatch' for r in beam_rows(result, 'original->native'))
    assert {r['status'] for r in beam_rows(result, 'generated->native')} == {'verified'}


@pytest.mark.parametrize('index', [0, 4, 5])
def test_one_missing_field_stays_unsupported_despite_score_claim(index):
    original, generated, model = example()
    del model['notation_events'][index]['beams']
    model['beam_metadata_complete'] = True
    result = audit(original, generated, model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    assert sentinel(result)['status'] == 'unsupported'
    for boundary in ('original->native', 'generated->native'):
        rows = beam_rows(result, boundary)
        assert len(rows) == 6
        assert rows[index]['status'] == 'unsupported'
    assert sentinel(contract.verify_generated_contract(generated, model))['status'] == 'unsupported'


@pytest.mark.parametrize('invalid', [None, True, {}, 'begin', [['1', 'begin']],
    [['0', 'begin', []]], [['9', 'begin', []]], [[True, 'begin', []]],
    [['1', 'wrong', []]], [['1', 'begin', {}]], [['1', 'begin', [['fan']]]],
    [['1', 'begin', [['number', '2']]]],
    [['1', 'begin', [['fan', 'accel'], ['fan', 'rit']]]],
    [['1', 'begin', []], ['1', 'end', []]]])
def test_malformed_metadata_blocks_coverage_and_wrong_values_mismatch(invalid):
    original, generated, model = example()
    model['notation_events'][0]['beams'] = invalid
    result = audit(original, generated, model)
    assert not result['complete']
    assert sentinel(result)['status'] == 'unsupported'
    for boundary in ('original->native', 'generated->native'):
        assert beam_rows(result, boundary)[0]['status'] == ('unsupported' if invalid is None else 'mismatch')


def test_empty_native_model_cannot_vacuously_verify_beam_metadata():
    original, generated, model = example()
    model['notation_events'] = []
    model['beam_metadata_complete'] = True
    assert sentinel(audit(original, generated, model))['status'] == 'unsupported'
    assert sentinel(contract.verify_generated_contract(generated, model))['status'] == 'unsupported'


def test_source_inventory_requires_beam_absence_for_notes_and_rests(tmp_path):
    original, generated, model = example()
    path = tmp_path / 'authored.musicxml'
    path.write_text(original)
    required = {r['id'] for r in contract.source_inventory(path)}
    assert 'original->native:xml-p0-m0-e5:beams' in required
    assert 'original->native:xml-p1-m0-e1:beams' in required
    assert required <= {r['id'] for r in audit(original, generated, model)['elements']}


@pytest.mark.parametrize('missing', [False, True, 'inventory'])
def test_midi_metadata_coverage_never_proves_written_beams(tmp_path, missing):
    _, _, model = example()
    if missing == 'inventory':
        del model['notation_events']
    elif missing:
        del model['notation_events'][-1]['beams']
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([
        mido.Message('note_on', note=72, velocity=85),
        mido.Message('note_off', note=72, time=480)]))
    path = tmp_path / 'performance.mid'
    midi.save(path)
    result = contract.verify_midi_performance(path, model)
    assert sentinel(result)['status'] == ('unsupported' if missing else 'verified')
    assert any(r['boundary'] == 'original->written' and r['construct'] == 'beams'
               and r['status'] == 'unsupported' for r in result['elements'])
