"""Source-derived expectations; production builders are used only as audit targets."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

import mido
import pytest


def verify(*args, **kwargs):
    from piano_teacher.notation.midi_transcription_rules import verify_midi_transcription
    return verify_midi_transcription(*args, **kwargs)


def write_midi(path, tracks, *, ppq=480, end=1920):
    midi = mido.MidiFile(type=1, ticks_per_beat=ppq)
    for name, events in tracks:
        track = mido.MidiTrack()
        if name:
            track.append(mido.MetaMessage('track_name', name=name))
        tick = 0
        for at, kind, pitch, velocity in events:
            track.append(mido.Message(kind, note=pitch, velocity=velocity, time=at-tick))
            tick = at
        track.append(mido.MetaMessage('end_of_track', time=max(end-tick, 0)))
        midi.tracks.append(track)
    midi.save(path)
    return path


def target(path, hand='both'):
    # Outputs under test, NEVER the expected facts used by the verifier.
    from piano_teacher.music import Phrase, load_midi
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model
    piece = load_midi(path)
    phrase = Phrase(1, 1, len(piece.bar_boundaries)-1, 0, piece.bar_boundaries[-1], piece.notes)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
                              time_signatures=piece.time_signatures)
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
    model['import_warnings'] = list(piece.import_warnings)
    return score.musicxml, model


@pytest.fixture
def simple(tmp_path):
    path = write_midi(tmp_path/'simple.mid', [('Right Hand', [
        (0, 'note_on', 64, 71), (480, 'note_off', 64, 0),
        (480, 'note_on', 67, 52), (960, 'note_on', 67, 0),
    ])])
    return path, *target(path)


def assert_good(result):
    assert result['passed'] and result['complete'], result['discrepancies']
    assert result['schema_version'] == 1
    assert result['rule_version']
    assert result['elements']
    assert all(e['status'] == 'verified' for e in result['elements'])


def test_independent_rule_verifier_exists():
    assert importlib.util.find_spec('piano_teacher.notation.midi_transcription_rules') is not None


def test_literal_attacks_releases_velocities_and_evidence(simple):
    path, xml, model = simple
    result = verify(path, xml, model)
    assert_good(result)
    attacks = [r for r in result['elements'] if r['rule'] == 'physical_performance'
               and r['source_id'].startswith('midi-t')]
    assert {r['source_id'] for r in attacks} == {'midi-t0-e1', 'midi-t0-e3'}
    assert {r['expected']['velocity'] for r in attacks} == {71, 52}
    assert {r['expected']['onset_beats'] for r in attacks} == {0, 1}


@pytest.mark.parametrize('field,value', [('midi_pitch', 65), ('onset_beats', .01),
                                        ('duration_beats', .9), ('velocity', 99),
                                        ('track', 2), ('channel', 1), ('hand', 'left')])
def test_native_source_fact_mutations_fail(simple, field, value):
    path, xml, model = simple
    model['notes'][0][field] = value
    assert not verify(path, xml, model)['passed']


@pytest.mark.parametrize('event_index,field,value', [(1, 'note', 65), (1, 'time', 5),
                                                   (2, 'time', 479), (1, 'velocity', 70)])
def test_original_source_mutations_invalidate_old_target(simple, event_index, field, value):
    path, xml, model = simple
    midi = mido.MidiFile(path)
    setattr(midi.tracks[0][event_index], field, value)
    midi.save(path)
    assert not verify(path, xml, model)['passed']


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'identity', 'rhythm', 'tie',
                                     'written_tie', 'hand', 'barfill', 'meter', 'hidden_pitch'])
def test_generated_notation_mutations_fail(simple, mutation):
    path, xml, model = simple
    root = ET.fromstring(xml)
    part = root.find("part[@id='RH']")
    bar = part.find('measure')
    note = bar.find('note')
    if mutation == 'missing':
        bar.remove(note)
    elif mutation == 'extra':
        duplicate = deepcopy(note)
        ET.SubElement(duplicate, 'chord')
        bar.insert(list(bar).index(note)+1, duplicate)
    elif mutation == 'identity':
        note.set('id', 'forged-source-binding')
    elif mutation == 'rhythm':
        note.find('type').text = 'half'
    elif mutation == 'tie':
        ET.SubElement(note, 'tie', type='start')
    elif mutation == 'written_tie':
        ET.SubElement(ET.SubElement(note, 'notations'), 'tied', type='stop')
    elif mutation == 'hand':
        part.set('id', 'LH')
    elif mutation == 'barfill':
        bar.findall('note')[-1].find('duration').text = '10080'
    elif mutation == 'meter':
        bar.find('attributes/time/beats').text = '3'
    elif mutation == 'hidden_pitch':
        note.set('print-object', 'no')
    result = verify(path, ET.tostring(root, encoding='unicode'), model)
    assert not result['passed'], mutation


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'source_id', 'is_attack', 'tie_start', 'beat'])
def test_native_notation_mutations_fail(simple, mutation):
    path, xml, model = simple
    if mutation == 'missing':
        model['notation_events'].pop(0)
    elif mutation == 'extra':
        model['notation_events'].append(deepcopy(model['notation_events'][0]))
    else:
        model['notation_events'][0][mutation] = {
            'source_id':'midi-t0-e999', 'is_attack':False, 'tie_start':True, 'beat':.02}[mutation]
    assert not verify(path, xml, model)['passed']


def test_missing_xml_and_self_attestation_never_complete(simple):
    path, _, model = simple
    model['midi_transcription_rules'] = {'passed':True, 'complete':True}
    model['transcription_verified'] = True
    result = verify(path, None, model)
    assert not result['complete']
    assert any(e['status'] == 'unverified' for e in result['elements'])


def test_absent_required_rule_fails_closed(simple, monkeypatch):
    import piano_teacher.notation.midi_transcription_rules as rules
    checks = dict(rules.RULE_CHECKS)
    checks.pop('display_quantization')
    monkeypatch.setattr(rules, 'RULE_CHECKS', checks)
    result = verify(*simple)
    assert not result['complete']
    assert any(e['rule']=='display_quantization' and e['status']=='unverified'
               for e in result['elements'])


def test_fifo_overlap_requires_both_original_endpoints_and_warning(tmp_path):
    path = write_midi(tmp_path/'overlap.mid', [('Right Hand', [
        (0,'note_on',64,91), (120,'note_on',64,52),
        (480,'note_off',64,0), (600,'note_off',64,0),
    ])])
    xml, model = target(path)
    assert_good(verify(path, xml, model))
    assert [n['duration_beats'] for n in model['notes']] == [1, 1]
    altered = deepcopy(model)
    altered['notes'][0]['duration_beats'] = 1.25  # LIFO instead of FIFO.
    altered['notes'][1]['duration_beats'] = .75
    assert not verify(path, xml, altered)['passed']
    model['import_warnings'] = []
    assert not verify(path, xml, model)['passed']


def test_orphan_and_zero_duration_are_skipped_only_with_warnings(tmp_path):
    path = write_midi(tmp_path/'repairs.mid', [('Right Hand', [
        (0,'note_off',60,0), (0,'note_on',60,71), (0,'note_off',60,0),
        (0,'note_on',64,81), (480,'note_off',64,0),
    ])])
    xml, model = target(path)
    assert_good(verify(path, xml, model))
    assert model['notes'][0]['id'] == 'midi-t0-e4'
    model['import_warnings'] = model['import_warnings'][:1]
    assert not verify(path, xml, model)['passed']


@pytest.mark.parametrize('names,pitches,hands', [
    (['Left Hand'], [76], ['left']),
    (['Right Hand'], [40], ['right']),
    (['',''], [76,80], ['left','right']),
    (['',''], [80,76], ['right','left']),
    (['',''], [64,64], ['left','right']),
    (['','',''], [59,60,76], ['left','right','right']),
])
def test_named_then_two_track_median_then_middle_c_policy(tmp_path, names, pitches, hands):
    path = write_midi(tmp_path/'hands.mid', [(name, [
        (0,'note_on',pitch,71), (480,'note_off',pitch,0)])
        for name,pitch in zip(names,pitches)])
    xml, model = target(path)
    assert_good(verify(path, xml, model))
    assert {n['track']:n['hand'] for n in model['notes']} == dict(enumerate(hands))
    model['notes'][0]['hand'] = 'left' if model['notes'][0]['hand']=='right' else 'right'
    assert not verify(path, xml, model)['passed']


def test_crossbar_continuation_binding_and_tie_mutation(tmp_path):
    path = write_midi(tmp_path/'held.mid', [('Right Hand', [
        (0,'note_on',64,71), (2400,'note_off',64,0)])], end=3840)
    xml, model = target(path)
    assert_good(verify(path, xml, model))
    events = [n for n in model['notation_events'] if n['kind']=='note']
    assert len(events)==2 and events[1]['tie_stop'] and not events[1]['is_attack']
    root = ET.fromstring(xml)
    root.find("part[@id='RH']/measure/note/tie").set('type', 'stop')
    assert not verify(path, ET.tostring(root, encoding='unicode'), model)['passed']


def test_swing_stays_exact_and_complete_ornament_can_move_four_milliseconds(tmp_path):
    # .6 swing is not a straight eighth. 1/12 ornament noise is independently bounded.
    for name, ticks in [('swing', [0,288,480,768]), ('ornament', [0,39,79,120])]:
        events = []
        for i, tick in enumerate(ticks):
            events.extend([(tick,'note_on',64+i,71), (tick+20,'note_off',64+i,0)])
        path = write_midi(tmp_path/f'{name}.mid', [('Right Hand', events)])
        xml, model = target(path)
        assert_good(verify(path, xml, model))
        if name == 'swing':
            assert model['notes'][1]['onset_beats'] == .6
            model['notation_events'][1]['beat'] = .5
            assert not verify(path, xml, model)['passed']


def test_hidden_primary_rest_cannot_erase_visible_silence(simple):
    path, xml, model = simple
    root = ET.fromstring(xml)
    rest = root.find("part[@id='LH']/measure/note")
    rest.set('print-object', 'no')
    model['notation_events'] = [e for e in model['notation_events'] if e['staff']!='left']
    assert not verify(path, ET.tostring(root, encoding='unicode'), model)['complete']


def test_removing_tuplet_marks_from_xml_and_native_cannot_self_validate():
    path = Path(__file__).parent/'fixtures/musical_fidelity/midi_triplets.mid'
    xml, model = target(path)
    root = ET.fromstring(xml)
    for notations in root.findall('.//notations'):
        for mark in notations.findall('tuplet'):
            notations.remove(mark)
    for e in model['notation_events']:
        e['tuplet_marks'] = []
    assert not verify(path, ET.tostring(root, encoding='unicode'), model)['complete']


def test_rules_do_not_call_production_or_mido_decoders(simple, monkeypatch):
    import piano_teacher.music as music
    import piano_teacher.notation.lesson as lesson
    import piano_teacher.notation.model as model_module
    path, xml, model = simple

    def forbidden(*args, **kwargs):
        raise AssertionError('Production or Mido cannot supply independent facts')

    for module, name in [(music,'load_midi'), (music,'_assign_hands'),
                         (lesson,'build_lesson_score'), (lesson,'_phrase_lanes'),
                         (model_module,'build_score_model'), (mido,'MidiFile')]:
        monkeypatch.setattr(module,name,forbidden)
    assert_good(verify(path, xml, model))


def test_rule_inventory_counts_are_derived_from_evidence(simple):
    from piano_teacher.notation.midi_transcription_rules import REQUIRED_RULES, RULE_VERSION
    report = verify(*simple)
    assert report['rule_version'] == RULE_VERSION == 'midi-transcription-rules-v1'
    assert set(report['rules']) == set(REQUIRED_RULES)
    for rule,summary in report['rules'].items():
        elements = [e for e in report['elements'] if e['rule']==rule]
        assert summary['evidence']['element_count'] == len(elements) > 0
        assert summary['evidence']['verified'] == len(elements)


def test_two_track_policy_uses_median_instead_of_mean(tmp_path):
    tracks = []
    for pitches in ([40,40,127],[55,55,55]):
        events = []
        for i,pitch in enumerate(pitches):
            events.extend([(i*480,'note_on',pitch,71), ((i+1)*480,'note_off',pitch,0)])
        tracks.append(('',events))
    path = write_midi(tmp_path/'median.mid',tracks)
    xml,model = target(path)
    report = verify(path,xml,model)
    assert_good(report)
    rows = [r for r in report['elements'] if r['rule']=='hand_policy']
    assert {r['expected'][0] for r in rows if r['source_id'].startswith('midi-t0')} == {'left'}


def test_coordinated_false_proof_flags_do_not_override_wrong_source(simple):
    path,xml,model = simple
    model.update(transcription_verified=True, passed=True, complete=True,
                 midi_transcription_rules=dict(passed=True, complete=True))
    model['notes'][0]['velocity'] = 1
    assert not verify(path,xml,model)['passed']


def test_coordinated_xml_native_onset_straightening_is_rejected(tmp_path):
    path = write_midi(tmp_path/'swing.mid',[('Right Hand',[
        (288,'note_on',64,71),(768,'note_off',64,0)])])
    xml,model = target(path)
    root = ET.fromstring(xml)
    bar = root.find("part[@id='RH']/measure")
    notes = bar.findall('note')
    notes[0].find('duration').text = '5040'  # .6 opening rest -> .5
    notes[-1].find('duration').text = '25200'  # compensate at bar end
    # Keep note/rest types, dots, ratios and native written events consistent.
    for rest in (notes[0],notes[-1]):
        for tag in list(rest):
            if tag.tag in ('dot','time-modification','notations'):
                rest.remove(tag)
    notes[0].find('type').text = 'eighth'
    notes[-1].find('type').text = 'half'
    mod = ET.SubElement(notes[-1],'time-modification')
    ET.SubElement(mod,'actual-notes').text = '4'
    ET.SubElement(mod,'normal-notes').text = '5'
    notations = ET.SubElement(notes[-1],'notations')
    ET.SubElement(notations,'tuplet',type='start',number='1',bracket='no',**{'show-number':'none'})
    ET.SubElement(notations,'tuplet',type='stop',number='1')
    model['notation_events'][0].update(duration_beats=.5,note_type='eighth',dots=0,
                                      time_modification=None,tuplet_marks=[])
    model['notation_events'][1]['beat'] = .5
    model['notation_events'][2].update(beat=1.5,duration_beats=2.5,note_type='half',dots=0,
        time_modification=dict(actual=4,normal=5),tuplet_marks=[
            dict(type='start',number='1',bracket='no',show_number='none'),
            dict(type='stop',number='1',bracket='no',show_number='actual')])
    report = verify(path,ET.tostring(root,encoding='unicode'),model)
    assert report['rules']['native_notation']['status']=='verified'
    assert report['rules']['display_quantization']['status']=='mismatch'


def test_disposition_ledger_rows_require_complete_independent_evidence(tmp_path):
    from piano_teacher.notation.semantic_contract import verify_midi_performance
    path = write_midi(tmp_path/'dispositions.mid',[('Right Hand',[
        (0,'note_off',60,0),(0,'note_on',60,71),(0,'note_off',60,0),
        (0,'note_on',64,81),(480,'note_off',64,0)])])
    xml,model = target(path)
    result = verify_midi_performance(path,model,generated_xml=xml)
    disposition_ids = {'midi-t0-e1','midi-t0-e2'}
    rows = [e for e in result['elements'] if e['source']['id'] in disposition_ids]
    assert len(rows)==2 and all(e['status']=='verified' for e in rows)
    model['import_warnings'] = []
    result = verify_midi_performance(path,model,generated_xml=xml)
    assert all(e['status']=='unverified' for e in result['elements']
               if e['source']['id'] in disposition_ids)


def test_invalid_source_and_unimplemented_format_stay_incomplete(simple):
    path,xml,model = simple
    path.write_bytes(b'MThd')
    report = verify(path,xml,model)
    assert not report['complete'] and report['rules']['source_decode']['status']=='unverified'


def test_canonical_integration_and_backward_compatibility(simple):
    from piano_teacher.notation.semantic_contract import source_inventory, verify_midi_performance
    path, xml, model = simple
    report = verify_midi_performance(path, model, generated_xml=xml)
    rows = [r for r in report['elements'] if r['construct']=='midi_transcription_rules']
    assert len(rows)==1 and rows[0]['status']=='verified'
    assert rows[0]['source']['id']=='midi:transcription-rules'
    assert rows[0]['boundary']=='original->written'
    assert report['midi_transcription_rules']['elements']
    assert not report['complete']  # Authorial limitations remain explicit.
    inventory = [r for r in source_inventory(path) if r['construct']=='midi_transcription_rules']
    assert len(inventory)==1 and inventory[0]['id']==rows[0]['id']
    legacy = verify_midi_performance(path, model)
    assert any(r['status']=='unverified' for r in legacy['elements']
               if r['construct']=='midi_transcription_rules')


@pytest.mark.parametrize('filename', ['midi_raw_ppq997.mid', 'midi_mixed_meter.mid',
                                     'midi_triplets.mid', 'midi_held_crossbar.mid'])
def test_literal_corpus_sources(filename):
    path = Path(__file__).parent/'fixtures/musical_fidelity'/filename
    xml, model = target(path)
    assert_good(verify(path, xml, model))
