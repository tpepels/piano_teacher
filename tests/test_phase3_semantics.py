"""Original-source mutations: generated XML/native agreement is not an oracle."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

import mido
import pytest

from piano_teacher.notation import semantic_contract as contract


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/musical_fidelity"


def example():
    # Four beats: two eighths, three triplet eighths, two tied quarters.
    # A second measure is an explicitly written whole rest. Native facts below
    # are hand calculated; the oracle/parser under test never builds them.
    specs = [
        ("C", 72, .0, .5, "eighth", "begin", None, False, False),
        ("D", 74, .5, .5, "eighth", "end", None, False, False),
        ("E", 76, 1., 1/3, "eighth", None, "start", False, False),
        ("F", 77, 4/3, 1/3, "eighth", None, None, False, False),
        ("G", 79, 5/3, 1/3, "eighth", None, "stop", False, False),
        ("A", 81, 2., 1., "quarter", None, None, True, False),
        ("A", 81, 3., 1., "quarter", None, None, False, True),
    ]
    notes = []
    events = []
    xml_notes = []
    for i, (step, pitch, beat, duration, typ, beam, mark, start, stop) in enumerate(specs):
        triplet = 2 <= i <= 4
        tie = ('<tie type="start"/>' if start else '') + ('<tie type="stop"/>' if stop else '')
        ratio = ('<time-modification><actual-notes>3</actual-notes>'
                 '<normal-notes>2</normal-notes></time-modification>') if triplet else ''
        limits = f'<notations><tuplet type="{mark}" number="1"/></notations>' if mark else ''
        beam_xml = f'<beam number="1">{beam}</beam>' if beam else ''
        xml_notes.append(f'<note id="g{i}"><pitch><step>{step}</step><octave>5</octave>'
                         f'</pitch><duration>{round(duration*6)}</duration>{tie}<voice>7</voice>'
                         f'<type>{typ}</type>{ratio}{beam_xml}{limits}</note>')
        source_id = f'xml-p0-m0-e{6 if i == 6 else i+1}'
        events.append(dict(id=f'g{i}', source_id=source_id, staff='right', voice='1',
                           measure=1, beat=round(beat, 8), duration_beats=round(duration, 8),
                           kind='note', midi_pitch=pitch,
                           spelling=dict(step=step, alter=0, octave=5), note_type=typ,
                           dots=0, chord=False, tie_start=start, tie_stop=stop,
                           is_attack=not stop, accidental=None,
                           time_modification=dict(actual=3, normal=2) if triplet else None,
                           tuplet_marks=[dict(type=mark, number='1', bracket='no',
                                              show_number='actual')] if mark else []))
        if i != 6:
            notes.append(dict(id=source_id, hand='right', voice='xml-p0-s1-v7',
                              onset_beats=round(beat, 8),
                              duration_beats=2. if i == 5 else round(duration, 8),
                              midi_pitch=pitch, spelling=[step, 0, 5], velocity=85,
                              track=0, channel=0))
    xml = ('<score-partwise><part-list><score-part id="RH"><part-name>Right Hand</part-name>'
           '</score-part></part-list><part id="RH"><measure number="1"><attributes>'
           '<divisions>6</divisions><time><beats>4</beats><beat-type>4</beat-type></time>'
           '<clef><sign>G</sign><line>2</line></clef></attributes>' + ''.join(xml_notes) +
           '</measure><measure number="2"><note id="g7"><rest/><duration>24</duration>'
           '<voice>7</voice><type>whole</type></note></measure></part></score-partwise>')
    events.append(dict(id='rest:right:2:7', source_id=None, staff='right', voice='1',
                       measure=2, beat=4., duration_beats=4., kind='rest', midi_pitch=None,
                       spelling=None, note_type='whole', dots=0, chord=False,
                       tie_start=False, tie_stop=False, is_attack=False, accidental=None,
                       time_modification=None, tuplet_marks=[]))
    model = dict(notes=notes, notation_events=events, active_hand='both',
                 active_note_ids=[n['id'] for n in notes],
                 measures=[dict(number=i+1, start_beat=i*4., end_beat=(i+1)*4.,
                                meter=[4, 4], keys={'right': 0},
                                clefs={'right': dict(sign='G', line=2, octave_change=0)})
                           for i in range(2)])
    return xml, xml.replace('<voice>7</voice>', '<voice>1</voice>'), model


def audit(source, generated, model, **kwargs):
    return contract.verify_musicxml_contract(source, generated, model, **kwargs)


def bad_rows(result, construct, boundary=None):
    return [e for e in result['elements'] if e['status'] == 'mismatch'
            and e['construct'] == construct and (boundary is None or e['boundary'] == boundary)]


def test_voice_renumbering_is_verified_but_missing_native_beam_metadata_is_not():
    result = audit(*example())
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    assert any(e['construct'] == 'voices' and e['status'] == 'verified'
               and e['evidence']['generated_voice'] == '1' for e in result['elements'])
    assert any(e['construct'] == 'beams' and e['status'] == 'unsupported'
               and e['boundary'] == 'original->native' for e in result['elements'])
    assert result['coverage']['expected'] == len(result['elements'])


@pytest.mark.parametrize('target,value,construct,native_field,native_value', [
    ('pitch/step', 'B', 'written_notes', 'midi_pitch', 83),
    ('duration', '2', 'written_notes', 'duration_beats', 1/3),
    ('type', '16th', 'written_notes', 'note_type', '16th'),
    ('voice', '2', 'voices', 'voice', '2'),
    ('beam', 'end', 'beams', None, None),
    ('tie', 'stop', 'ties', 'tie_start', False),
    ('time-modification/actual-notes', '5', 'tuplets', 'time_modification',
     {'actual': 5, 'normal': 2}),
    ('notations/tuplet', 'stop', 'tuplets', 'tuplet_marks',
     [dict(type='stop', number='1', bracket='no', show_number='actual')]),
])
def test_original_catches_shared_generated_and_native_wrong_fact(
        target, value, construct, native_field, native_value):
    source, generated, model = example()
    root = ET.fromstring(generated)
    index = 5 if target == 'tie' else 2 if 'modification' in target or 'tuplet' in target else 0
    node = root.findall('.//part/measure/note')[index].find(target)
    if target in ('tie', 'notations/tuplet'):
        node.set('type', value)
    else:
        node.text = value
    if native_field:
        model['notation_events'][index][native_field] = native_value
    result = audit(source, ET.tostring(root, encoding='unicode'), model)
    assert not result['passed']
    rows = bad_rows(result, construct, 'original->generated')
    assert rows, result['discrepancies']
    origin = rows[0]['source']
    assert origin['measure'] == '1'
    assert origin['voice'] == '7'
    assert origin['id'].startswith('xml-p0-m0-e')
    assert rows[0]['expected'] != rows[0]['actual']


@pytest.mark.parametrize('mutation', ['remove', 'hide', 'duration', 'kind'])
def test_source_rest_is_checked_even_when_generated_and_native_share_loss(mutation):
    source, generated, model = example()
    root = ET.fromstring(generated)
    bar = root.find('.//part/measure[@number="2"]')
    rest = bar.find('note')
    if mutation == 'remove':
        bar.remove(rest)
        model['notation_events'].pop()
    elif mutation == 'hide':
        rest.set('print-object', 'no')
        model['notation_events'].pop()
    elif mutation == 'duration':
        rest.find('duration').text = '12'
        model['notation_events'][-1]['duration_beats'] = 2.
    else:
        rest.remove(rest.find('rest'))
        rest.append(ET.fromstring('<pitch><step>C</step><octave>5</octave></pitch>'))
        model['notation_events'][-1].update(kind='note', midi_pitch=72)
    result = audit(source, ET.tostring(root, encoding='unicode'), model)
    assert bad_rows(result, 'written_rests', 'original->generated')
    assert bad_rows(result, 'written_rests', 'original->native')


@pytest.mark.parametrize('field', ['meter', 'boundaries', 'number', 'remove_measure', 'clef'])
def test_original_measure_structure_detects_shared_xml_model_mutations(field):
    source, generated, model = example()
    root = ET.fromstring(generated)
    if field == 'meter':
        root.find('.//time/beats').text = '3'
        model['measures'][0]['meter'] = [3, 4]
    elif field == 'boundaries':
        root.find('.//measure[@number="2"]/note/duration').text = '12'
        model['measures'][1]['end_beat'] = 6.
    elif field == 'number':
        root.find('.//measure').set('number', '23')
        model['measures'][0]['number'] = 23
    elif field == 'remove_measure':
        part = root.find('part')
        part.remove(part.findall('measure')[1])
        model['measures'].pop()
    else:
        root.find('.//clef/sign').text = 'F'
        model['measures'][0]['clefs']['right']['sign'] = 'F'
    result = audit(source, ET.tostring(root, encoding='unicode'), model)
    assert bad_rows(result, 'measure_structure', 'original->generated')
    assert bad_rows(result, 'measure_structure', 'original->native')


def test_native_only_note_rest_tie_tuplet_corruption_is_detected():
    source, generated, model = example()
    model['notation_events'][0]['spelling']['step'] = 'F'
    model['notation_events'][-1]['note_type'] = 'half'
    model['notation_events'][5]['tie_start'] = False
    model['notation_events'][2]['time_modification']['actual'] = 5
    result = audit(source, generated, model)
    for construct in ('written_notes', 'written_rests', 'ties', 'tuplets'):
        assert bad_rows(result, construct, 'original->native')


def test_hand_mode_comes_from_original_not_native_claimed_active_list():
    source, generated, model = example()
    model['active_hand'] = 'left'
    # Shared wrong claim: activating RH notes in LH mode.
    result = audit(source, generated, model, hand='left')
    assert bad_rows(result, 'hand_mode')
    model['active_note_ids'] = []
    assert not bad_rows(audit(source, generated, model, hand='left'), 'hand_mode')


def test_grace_and_unpitched_events_are_explicitly_uncovered():
    source, generated, model = example()
    root = ET.fromstring(source)
    root.find('part/measure').insert(1, ET.fromstring(
        '<note><grace/><pitch><step>C</step><octave>6</octave></pitch><voice>7</voice></note>'))
    result = audit(ET.tostring(root, encoding='unicode'), generated, model)
    assert any(e['construct'] == 'grace_notes' and e['status'] == 'unsupported'
               for e in result['elements'])
    assert not result['complete']


def test_real_secondary_voice_rest_loss_is_detected_after_projection_fix(tmp_path):
    from scripts.audit_phase3_semantics import audit_source
    result = audit_source('tests/fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml',
                          source_index=9, hand='both', artifact_dir=tmp_path)
    assert result['passed'], result['discrepancies']
    generated = ET.fromstring((tmp_path / 'generated.musicxml').read_text())
    model = json.loads((tmp_path / 'model.json').read_text())
    for note in generated.findall('./part[@id="RH"]/measure/note'):
        if note.find('rest') is not None and note.findtext('voice') == '2':
            note.set('print-object', 'no')
    model['notation_events'] = [event for event in model['notation_events']
                               if not (event['staff']=='right' and event['kind']=='rest'
                                       and event['voice']=='2')]
    result = audit((FIXTURES/'xml_parallel_tied_voices.musicxml').read_text(),
                   ET.tostring(generated, encoding='unicode'), model)
    rows = bad_rows(result, 'written_rests', 'original->generated')
    assert any(e['source']['voice'] == '2' and e['source']['measure'] == '1' for e in rows)
    assert any(e['source']['voice'] == '2' and e['source']['measure'] == '2' for e in rows)
    assert not result['passed']


def midi_example(tmp_path):
    path = tmp_path / 'crossed.mid'
    midi = mido.MidiFile(ticks_per_beat=997)
    for name, pitch in [('Right Hand', 48), ('Left Hand', 84)]:
        midi.tracks.append(mido.MidiTrack([
            mido.MetaMessage('track_name', name=name),
            mido.Message('note_on', note=pitch, velocity=71, time=17),
            mido.Message('note_off', note=pitch, time=991),
        ]))
    midi.save(path)
    notes = [dict(id=f'midi-t{i}-e1', hand=hand, voice=f'midi-t{i}-c0',
                  onset_beats=round(17/997, 8), duration_beats=round(991/997, 8),
                  midi_pitch=pitch, velocity=71, track=i, channel=0)
             for i, (hand, pitch) in enumerate([('right', 48), ('left', 84)])]
    return path, dict(notes=notes, active_hand='right', active_note_ids=['midi-t0-e1'])


@pytest.mark.parametrize('field,value', [('midi_pitch', 50), ('duration_beats', .5),
                                         ('onset_beats', .5), ('velocity', 20),
                                         ('hand', 'left'), ('channel', 3), ('track', 4)])
def test_midi_original_performance_and_named_crossed_hands_are_independent(tmp_path, field, value):
    path, model = midi_example(tmp_path)
    result = contract.verify_midi_performance(path, model, hand='right')
    assert result['passed'], result['discrepancies']
    assert not result['complete']  # A performance file specifies no written rests/beams/etc.
    model['notes'][0][field] = value
    assert not contract.verify_midi_performance(path, model, hand='right')['passed']


def test_midi_mode_cannot_be_just_a_self_consistent_native_claim(tmp_path):
    path, model = midi_example(tmp_path)
    model['active_note_ids'] = ['midi-t1-e1']
    assert bad_rows(contract.verify_midi_performance(path, model, hand='right'), 'hand_mode')


def test_semantic_runner_is_headless_and_writes_identity_bound_ledger(tmp_path):
    script = ('import sys; from scripts.audit_phase3_semantics import main; '
              'code=main(); '
              'assert not any(x in sys.modules for x in '
              '["piano_teacher.score", "piano_teacher.notation.phase3_pixels", '
              '"scripts.audit_phase3_whole_pieces", "scripts.check_native_verovio_overlay"]); '
              'raise SystemExit(code)')
    completed = subprocess.run([sys.executable, '-c', script, '--index', '7', '--hand', 'left',
                                '--out', str(tmp_path)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode in (0, 1), completed.stderr
    report = json.loads((tmp_path / 'summary.json').read_text())
    assert report['schema_version'] == 1 and report['verification_kind'] == 'semantic'
    assert report['source_index'] == 7 and report['hand'] == 'left'
    assert report['source_sha256'] == hashlib.sha256((ROOT/report['source']).read_bytes()).hexdigest()
    elements = report['elements']
    assert elements and len({e['id'] for e in elements}) == len(elements)
    assert all(e['source'].keys() >= {'id', 'measure', 'staff', 'voice'} for e in elements)
    assert report['coverage']['expected'] == len(elements)
    for status in ('verified', 'ambiguous', 'unsupported', 'unverified', 'mismatch'):
        assert report['coverage'][status] == sum(e['status'] == status for e in elements)
    assert report['complete'] == all(e['status'] == 'verified' for e in elements)
    assert report['environment']['python']['version']
    assert report['environment']['packages']['mido']
    for key, filename in [('original', 'original.musicxml'), ('generated', 'generated.musicxml'),
                          ('native', 'model.json')]:
        artifact = report['artifacts'][key]
        assert artifact['path'] == filename
        assert artifact['sha256'] == hashlib.sha256((tmp_path/filename).read_bytes()).hexdigest()
    assert report['artifacts']['original']['sha256'] == report['source_sha256']


def test_pipeline_failure_preserves_original_and_any_generated_diagnostics(tmp_path, monkeypatch):
    from scripts import audit_phase3_semantics as runner
    def fail_native(*args, **kwargs):
        raise ValueError('broken native parser')
    monkeypatch.setattr(runner, 'build_score_model', fail_native)
    result = runner.audit_source(runner.ALL_SOURCES[7], source_index=7, artifact_dir=tmp_path)
    assert not result['passed'] and 'broken native parser' in result['runtime_error']
    assert (tmp_path/'original.musicxml').exists()
    assert (tmp_path/'generated.musicxml').exists()
    assert not (tmp_path/'model.json').exists()
    assert result['artifacts'].keys() >= {'original', 'generated'}


def test_required_source_inventory_cannot_lose_native_beam_or_original_rest_rows(tmp_path):
    source, generated, model = example()
    path = tmp_path / 'original.musicxml'
    path.write_text(source)
    inventory = contract.source_inventory(path)
    required = {e['id'] for e in inventory}
    assert 'original->native:score:beam-metadata:beams' in required
    assert 'original->generated:xml-p0-m1-e0:written_rests' in required
    assert required <= {e['id'] for e in audit(source, generated, model)['elements']}


def test_midi_required_inventory_includes_attacks_releases_and_transcription_sentinel(tmp_path):
    path, model = midi_example(tmp_path)
    inventory = contract.source_inventory(path)
    required = {e['id'] for e in inventory}
    assert 'original->native:midi-t0-e1:midi_performance' in required
    assert 'original->native:midi-t0-e2:midi_release' in required
    assert 'original->written:midi:written-transcription:midi_written_transcription' in required
    result = contract.verify_midi_performance(path, model, hand='right')
    assert required <= {e['id'] for e in result['elements']}


def test_dropped_duplicate_and_extra_native_attack_identities_are_mismatches():
    source, generated, model = example()
    model['notes'].pop()
    model['notes'].append(deepcopy(model['notes'][0]))
    extra = deepcopy(model['notes'][1])
    extra['id'] = 'invented'
    model['notes'].append(extra)
    result = audit(source, generated, model)
    assert len(bad_rows(result, 'source_attacks')) >= 3


@pytest.mark.parametrize('field,value', [('dots', 2), ('chord', True),
                                         ('staff', 'left'), ('accidental', 'sharp'),
                                         ('spelling', dict(step='B', alter=-1, octave=4))])
def test_original_written_fields_are_checked_independently_of_native_only_mutations(field, value):
    source, generated, model = example()
    model['notation_events'][0][field] = value
    assert bad_rows(audit(source, generated, model), 'written_notes', 'original->native')


def test_consistent_measure_label_projection_preserves_grid_but_cannot_prove_original_labels():
    source, generated, model = example()
    root = ET.fromstring(source)
    for bar, label in zip(root.findall('part/measure'), ['0', '1']):
        bar.set('number', label)
    result = audit(ET.tostring(root, encoding='unicode'), generated, model)
    assert result['passed'], result['discrepancies']
    assert not bad_rows(result, 'measure_structure')
    labels = [e for e in result['elements'] if e['construct'] == 'measure_labels']
    assert labels and all(e['status'] == 'unsupported' for e in labels)
    assert any(e['expected'] == '0' and e['actual'] == '1' for e in labels)


def test_inferred_tuplet_brackets_do_not_override_verified_original_ratio():
    source, generated, model = example()
    root = ET.fromstring(source)
    for node in root.findall('.//notations'):
        for mark in list(node):
            if mark.tag == 'tuplet':
                node.remove(mark)
    result = audit(ET.tostring(root, encoding='unicode'), generated, model)
    assert result['passed'], result['discrepancies']
    ratios = [e for e in result['elements'] if e['construct'] == 'tuplets'
              and e['source']['id'] == 'xml-p0-m0-e3']
    assert ratios and all(e['status'] == 'verified' for e in ratios)
    groups = [e for e in result['elements'] if e['construct'] == 'tuplet_grouping'
              and e['boundary'].startswith('original->')
              and e['source']['id'] == 'xml-p0-m0-e3']
    assert groups and all(e['status'] == 'unsupported' for e in groups)


def test_original_authored_tuplet_bracket_disappearance_is_a_mismatch():
    source, generated, model = example()
    root = ET.fromstring(generated)
    mark = root.find('.//notations/tuplet')
    mark.set('bracket', 'yes')
    model['notation_events'][2]['tuplet_marks'][0]['bracket'] = 'yes'
    # Original default no bracket is explicit group semantics, not absent group.
    result = audit(source, ET.tostring(root, encoding='unicode'), model)
    assert bad_rows(result, 'tuplets', 'original->generated')


def test_original_explicit_key_change_is_checked_at_both_boundaries():
    source, generated, model = example()
    for_source = ET.fromstring(source)
    for_generated = ET.fromstring(generated)
    for root in (for_source, for_generated):
        root.find('.//attributes').append(ET.fromstring('<key><fifths>0</fifths></key>'))
    for_generated.find('.//key/fifths').text = '-3'
    model['measures'][0]['keys']['right'] = -3
    result = audit(ET.tostring(for_source, encoding='unicode'),
                   ET.tostring(for_generated, encoding='unicode'), model)
    assert bad_rows(result, 'measure_structure', 'original->generated')
    assert bad_rows(result, 'measure_structure', 'original->native')


def test_discrepancy_names_exact_changed_field_and_original_rest_identity():
    source, generated, model = example()
    root = ET.fromstring(generated)
    root.find('.//measure[@number="2"]/note').set('print-object', 'no')
    model['notation_events'].pop()
    rows = bad_rows(audit(source, ET.tostring(root, encoding='unicode'), model),
                    'written_rests', 'original->generated')
    assert rows[0]['source']['id'] == 'xml-p0-m1-e0'
    assert rows[0]['differences'] == [dict(field='visible', expected=True, actual=False)]


def test_midi_inferred_hand_provenance_is_required_by_original_inventory(tmp_path):
    path, model = midi_example(tmp_path)
    midi = mido.MidiFile(path)
    for track in midi.tracks:
        track[0].name = 'Piano'
    midi.save(path)
    required = {e['id'] for e in contract.source_inventory(path)}
    assert 'original->native:midi-t0:source_hand_assignment' in required
    assert 'original->native:score:beam-metadata:beams' in required
    result = contract.verify_midi_performance(path, model, hand='right')
    assert any(e['id'] == 'original->native:midi-t0:source_hand_assignment'
               and e['status'] == 'ambiguous' for e in result['elements'])


@pytest.mark.parametrize('field,value', [('source_id', 'wrong-physical-attack'),
                                         ('is_attack', False), ('id', 'wrong-segment')])
def test_note_segment_identity_and_original_attack_binding_are_not_self_attested(field, value):
    source, generated, model = example()
    model['notation_events'][0][field] = value
    result = audit(source, generated, model)
    assert not result['passed']
    assert bad_rows(result, 'segment_identity' if field == 'id' else 'source_binding')


def test_duplicate_segment_identity_shared_by_generated_and_native_is_invalid():
    source, generated, model = example()
    root = ET.fromstring(generated)
    root.findall('.//note')[1].set('id', 'g0')
    model['notation_events'][1]['id'] = 'g0'
    result = audit(source, ET.tostring(root, encoding='unicode'), model)
    assert not result['passed']
    assert bad_rows(result, 'source_binding')


def test_native_attack_and_written_voices_can_be_consistently_renamed():
    source, generated, model = example()
    generated = generated.replace('<voice>1</voice>', '<voice>bassline</voice>')
    for event in model['notation_events']:
        event['voice'] = 'bassline'
    for note in model['notes']:
        note['voice'] = 'bassline'
    result = audit(source, generated, model)
    assert result['passed'], result['discrepancies']
    # Reassigning just one original attack to a different voice breaks partition.
    model['notes'][0]['voice'] = 'other'
    assert bad_rows(audit(source, generated, model), 'source_attacks')


@pytest.mark.parametrize('attribute', ['show-type', 'placement', 'line-shape'])
def test_extra_authored_tuplet_attributes_are_not_silently_claimed_verified(attribute):
    source, generated, model = example()
    root = ET.fromstring(source)
    root.find('.//notations/tuplet').set(attribute, 'both' if attribute == 'show-type' else
                                       'above' if attribute == 'placement' else 'curved')
    result = audit(ET.tostring(root, encoding='unicode'), generated, model)
    assert bad_rows(result, 'tuplet_attributes', 'original->generated')
    assert any(e['construct'] == 'tuplet_attributes' and e['status'] == 'unsupported'
               and e['boundary'] == 'original->native' for e in result['elements'])


def test_separate_tuplet_group_with_same_ratio_can_have_inferred_limits():
    source, generated, model = example()
    original = ET.fromstring(source)
    output = ET.fromstring(generated)
    # Replace the two quarter ties by a second triplet group and a quarter rest.
    # First group's authored marks must not author limits for this later group.
    for root in (original, output):
        bar = root.find('part/measure')
        for note in list(bar.findall('note'))[5:]:
            bar.remove(note)
        for index, step in enumerate(('A', 'B', 'C')):
            mark = ('<notations><tuplet type="start"/></notations>' if index == 0 else
                    '<notations><tuplet type="stop"/></notations>' if index == 2 else '') if root is output else ''
            voice = '1' if root is output else '7'
            bar.append(ET.fromstring(f'<note id="second{index}"><pitch><step>{step}</step>'
                f'<octave>5</octave></pitch><duration>2</duration><voice>{voice}</voice>'
                '<type>eighth</type><time-modification><actual-notes>3</actual-notes>'
                f'<normal-notes>2</normal-notes></time-modification>{mark}</note>'))
        bar.append(ET.fromstring(f'<note><rest/><duration>6</duration><voice>{voice}</voice><type>quarter</type></note>'))
    result = audit(ET.tostring(original, encoding='unicode'), ET.tostring(output, encoding='unicode'), model)
    # Native was deliberately left unchanged: this asserts only this independent boundary.
    assert not bad_rows(result, 'tuplets', 'original->generated')
    assert any(e['construct'] == 'tuplet_grouping' and e['status'] == 'unsupported'
               and e['source']['id'] == 'xml-p0-m0-e6' and e['boundary'] == 'original->generated'
               for e in result['elements'])


def timed_clef_example():
    source, generated, model = example()
    root = ET.fromstring(source)
    root.find('part/measure').insert(2, ET.fromstring(
        '<attributes><clef><sign>F</sign><line>4</line></clef></attributes>'))
    # Source positional attack identities reflect the inserted attributes node.
    for note in model['notes']:
        ordinal = int(note['id'].rsplit('e', 1)[1])
        if ordinal >= 2:
            note['id'] = f'xml-p0-m0-e{ordinal+1}'
    for event in model['notation_events']:
        if event['source_id']:
            ordinal = int(event['source_id'].rsplit('e', 1)[1])
            if ordinal >= 2:
                event['source_id'] = f'xml-p0-m0-e{ordinal+1}'
    model['active_note_ids'] = [n['id'] for n in model['notes']]
    for bar in model['measures']:
        bar['clefs']['right'] = dict(sign='F', line=4, octave_change=0)
    # Generated F clef throughout has same final state, wrong source timeline.
    generated = generated.replace('<sign>G</sign><line>2</line>', '<sign>F</sign><line>4</line>')
    return ET.tostring(root, encoding='unicode'), generated, model


def test_timed_source_clef_change_cannot_be_replaced_by_same_final_clef():
    result = audit(*timed_clef_example())
    assert bad_rows(result, 'measure_attributes', 'original->generated')
    assert any(e['status'] == 'unsupported' and e['construct'] == 'mid_measure_attributes'
               and e['source']['id'] == 'xml-p0-m0-e2' for e in result['elements'])


def test_mid_measure_attribute_identity_and_coverage_are_required_by_inventory(tmp_path):
    source, generated, model = timed_clef_example()
    path = tmp_path/'timed.musicxml'
    path.write_text(source)
    required = {e['id'] for e in contract.source_inventory(path)}
    assert 'original->native:xml-p0-m0-e2:mid_measure_attributes' in required
    actual = {e['id'] for e in audit(source, generated, model)['elements']}
    assert required <= actual


@pytest.mark.parametrize('attribute', ['transpose', 'staff-details', 'instruments'])
def test_unhandled_musicxml_attributes_are_explicit_original_inventory_gaps(tmp_path, attribute):
    source, generated, model = example()
    root = ET.fromstring(source)
    root.find('.//attributes').append(ET.fromstring(
        '<transpose><octave-change>1</octave-change></transpose>' if attribute == 'transpose'
        else '<staff-details><staff-lines>1</staff-lines></staff-details>' if attribute == 'staff-details'
        else '<instruments>2</instruments>'))
    source = ET.tostring(root, encoding='unicode')
    result = audit(source, generated, model)
    rows = [e for e in result['elements'] if e['construct'] == attribute and e['boundary'] == 'original']
    assert rows and rows[0]['status'] == 'unsupported'
    path = tmp_path/'unsupported.musicxml'
    path.write_text(source)
    assert rows[0]['id'] in {e['id'] for e in contract.source_inventory(path)}


def test_nonprinting_pitched_event_may_be_absent_from_native_visible_inventory():
    source, generated, model = example()
    original = ET.fromstring(source)
    output = ET.fromstring(generated)
    original.find('.//note').set('print-object', 'no')
    output.find('.//note').set('print-object', 'no')
    model['notation_events'].pop(0)
    result = audit(ET.tostring(original, encoding='unicode'), ET.tostring(output, encoding='unicode'), model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    assert any(e['construct'] == 'written_notes' and e['source']['id'] == 'xml-p0-m0-e1'
               and e['boundary'] == 'original->native' and e['status'] == 'unsupported'
               for e in result['elements'])
    # The hidden written note is still an original performed attack.
    model['notes'].pop(0)
    assert bad_rows(audit(ET.tostring(original, encoding='unicode'),
                          ET.tostring(output, encoding='unicode'), model), 'source_attacks')
