"""Independent written tie/tuplet facts, including absent and corrupted attributes."""
from copy import deepcopy
import json
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import LessonScore
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation import semantic_contract as contract


def example():
    # Four beats: a quintuplet, two tied quarters, then a quarter rest.
    # Expectations are hand-calculated; no production parser builds this model.
    specs = [
        ('C', 72, 0., .2, '16th'), ('D', 74, .2, .2, '16th'),
        ('E', 76, .4, .2, '16th'), ('F', 77, .6, .2, '16th'),
        ('G', 79, .8, .2, '16th'), ('A', 81, 1., 1., 'quarter'),
        ('A', 81, 2., 1., 'quarter'),
    ]
    events, notes, xml_notes = [], [], []
    for i, (step, pitch, beat, duration, typ) in enumerate(specs):
        start, stop = i == 5, i == 6
        tied_marks = ([[['line-type', 'dashed'], ['orientation', 'over'],
                        ['placement', 'above'], ['type', 'start']]] if start else
                      [[['type', 'stop']]] if stop else [])
        tuplet_marks = ([dict(type='start', number='2', bracket='yes', show_number='actual')]
                        if i == 0 else [dict(type='stop', number='2', bracket='no',
                                            show_number='actual')] if i == 4 else [])
        tuplet_extras = ([[['line-shape', 'straight'], ['placement', 'above'],
                           ['show-type', 'both']]] if i == 0 else [[]] if i == 4 else [])
        limits = ('<tuplet type="start" number="2" bracket="yes" show-number="actual" '
                  'show-type="both" placement="above" line-shape="straight"/>' if i == 0 else
                  '<tuplet type="stop" number="2"/>' if i == 4 else '')
        tied_xml = ('<tied type="start" placement="above" orientation="over" line-type="dashed"/>'
                    if start else '<tied type="stop"/>' if stop else '')
        notations = f'<notations>{limits}{tied_xml}</notations>' if limits or tied_xml else ''
        sound_tie = '<tie type="start"/>' if start else '<tie type="stop"/>' if stop else ''
        ratio = ('<time-modification><actual-notes>5</actual-notes><normal-notes>4</normal-notes>'
                 '</time-modification>') if i < 5 else ''
        xml_notes.append(f'<note id="g{i}"><pitch><step>{step}</step><octave>5</octave></pitch>'
                         f'<duration>{round(duration*10080)}</duration>{sound_tie}<voice>7</voice>'
                         f'<type>{typ}</type>{ratio}{notations}</note>')
        source_id = f'xml-p0-m0-e{6 if stop else i+1}'
        events.append(dict(id=f'g{i}', source_id=source_id, staff='right', voice='1',
                           measure=1, beat=beat, duration_beats=duration, kind='note',
                           midi_pitch=pitch, spelling=dict(step=step, alter=0, octave=5),
                           note_type=typ, dots=0, chord=False, tie_start=start, tie_stop=stop,
                           is_attack=not stop, accidental=None, beams=[],
                           time_modification=dict(actual=5, normal=4) if i < 5 else None,
                           tuplet_marks=tuplet_marks, tied_marks=tied_marks,
                           tuplet_extras=tuplet_extras))
        if not stop:
            notes.append(dict(id=source_id, onset_beats=beat,
                              duration_beats=2. if start else duration, midi_pitch=pitch,
                              spelling=[step, 0, 5], velocity=85, hand='right',
                              voice='xml-p0-s1-v7', track=0, channel=0))
    for hand, beat, duration, typ in [('right', 3., 1., 'quarter'), ('left', 0., 4., 'whole')]:
        events.append(dict(id=f'rest:{hand}:1:{len(events)}', source_id=None, staff=hand,
                           voice='1', measure=1, beat=beat, duration_beats=duration, kind='rest',
                           midi_pitch=None, spelling=None, note_type=typ, dots=0, chord=False,
                           tie_start=False, tie_stop=False, is_attack=False, accidental=None,
                           time_modification=None, tuplet_marks=[], beams=[], tied_marks=[],
                           tuplet_extras=[]))
    attributes = ('<attributes><divisions>10080</divisions><key><fifths>0</fifths></key>'
                  '<time><beats>4</beats><beat-type>4</beat-type></time>'
                  '<clef><sign>{sign}</sign><line>{line}</line></clef></attributes>')
    original = ('<score-partwise><part-list>'
                '<score-part id="RH"><part-name>Right Hand</part-name></score-part>'
                '<score-part id="LH"><part-name>Left Hand</part-name></score-part></part-list>'
                '<part id="RH"><measure number="1">' + attributes.format(sign='G', line=2) +
                ''.join(xml_notes) + '<note><rest/><duration>10080</duration><voice>7</voice>'
                '<type>quarter</type></note></measure></part>'
                '<part id="LH"><measure number="1">' + attributes.format(sign='F', line=4) +
                '<note><rest/><duration>40320</duration><voice>9</voice><type>whole</type>'
                '</note></measure></part></score-partwise>')
    generated = original.replace('<voice>7</voice>', '<voice>1</voice>').replace(
        '<voice>9</voice>', '<voice>1</voice>')
    model = dict(notes=notes, notation_events=events, active_hand='both',
                 active_note_ids=[n['id'] for n in notes], measures=[dict(
                     number=1, start_beat=0., end_beat=4., meter=[4, 4],
                     keys=dict(right=0, left=0), clefs=dict(
                         right=dict(sign='G', line=2, octave_change=0),
                         left=dict(sign='F', line=4, octave_change=0)))])
    return original, generated, model


def rows(report, construct, boundary):
    return [r for r in report['elements'] if r['construct'] == construct
            and r['boundary'] == boundary]


def model_for_xml(xml, handmade):
    phrase = Phrase(1, 1, 1, 0., 4., tuple(
        Note(n['onset_beats'], n['onset_beats'] + n['duration_beats'], n['midi_pitch'],
             0, 0, 'right', n['id'], voice=n['voice'], spelling=tuple(n['spelling']))
        for n in handmade['notes']))
    bindings = {e['id']: dict(source_id=e['source_id'], pitch=e['midi_pitch'],
                             hand='right', display_beat=e['beat'],
                             source_beat=1. if e['tie_stop'] else e['beat'],
                             is_attack=e['is_attack'])
                for e in handmade['notation_events'] if e['kind'] == 'note'}
    return build_score_model(LessonScore(xml, phrase, bindings), boundaries=(0., 4.))


def test_model_preserves_written_attributes_and_empty_bags_as_json():
    original, generated, handmade = example()
    model = model_for_xml(generated, handmade)
    for field in ('tied_marks', 'tuplet_extras'):
        assert [e.get(field) for e in model['notation_events']] == [
            e[field] for e in handmade['notation_events']]
    assert json.loads(json.dumps(model)) == model
    result = contract.verify_musicxml_contract(original, generated, model)
    assert result['complete'], result


def test_multiple_marks_preserve_order_and_each_tuplets_empty_attribute_bag():
    _, generated, handmade = example()
    root = ET.fromstring(generated)
    root.find('.//notations').append(ET.fromstring('<tuplet type="stop" number="3"/>'))
    root.findall('.//notations')[2].append(ET.fromstring(
        '<tied type="start" number="3" color="#123456"/>'))
    model = model_for_xml(ET.tostring(root, encoding='unicode'), handmade)
    assert model['notation_events'][0].get('tuplet_extras') == [
        [['line-shape', 'straight'], ['placement', 'above'], ['show-type', 'both']], []]
    assert model['notation_events'][5].get('tied_marks') == [
        [['line-type', 'dashed'], ['orientation', 'over'], ['placement', 'above'], ['type', 'start']],
        [['color', '#123456'], ['number', '3'], ['type', 'start']]]


def test_written_metadata_and_absence_are_verified_at_all_three_boundaries():
    result = contract.verify_musicxml_contract(*example())
    assert result['complete'], result
    for construct in ('written_tie_attributes', 'tuplet_attributes'):
        for boundary in ('original->generated', 'original->native', 'generated->native'):
            checked = rows(result, construct, boundary)
            assert len(checked) == 9
            assert {r['status'] for r in checked} == {'verified'}
            assert checked[-1]['expected'] == checked[-1]['actual'] == []


@pytest.mark.parametrize('field,construct,index,tag,attribute', [
    ('tied_marks', 'written_tie_attributes', 5, 'tied', 'orientation'),
    ('tuplet_extras', 'tuplet_attributes', 0, 'tuplet', 'show-type'),
])
@pytest.mark.parametrize('mutation', ['change', 'remove', 'add', 'remove_mark'])
@pytest.mark.parametrize('shared_generated', [False, True])
def test_original_catches_changed_removed_and_added_attributes_even_when_generated_agrees(
        field, construct, index, tag, attribute, mutation, shared_generated):
    original, generated, model = example()
    root = ET.fromstring(generated)
    notations = root.findall('.//note')[index].find('notations')
    node = notations.find(tag)
    if mutation == 'change':
        value = 'under' if tag == 'tied' else 'actual'
        node.set(attribute, value)
        for pair in model['notation_events'][index][field][0]:
            if pair[0] == attribute:
                pair[1] = value
    elif mutation == 'remove':
        del node.attrib[attribute]
        model['notation_events'][index][field][0] = [
            p for p in model['notation_events'][index][field][0] if p[0] != attribute]
    elif mutation == 'add':
        node.set('default-x', '17')
        model['notation_events'][index][field][0].insert(0, ['default-x', '17'])
    else:
        notations.remove(node)
        model['notation_events'][index][field] = []
        if tag == 'tuplet':
            model['notation_events'][index]['tuplet_marks'] = []
    if shared_generated:
        generated = ET.tostring(root, encoding='unicode')
    result = contract.verify_musicxml_contract(original, generated, model)
    assert any(r['status'] == 'mismatch' for r in rows(result, construct, 'original->native'))
    direct = contract.verify_generated_contract(generated, model)
    assert bool([r for r in rows(direct, construct, 'generated->native')
                 if r['status'] == 'mismatch']) is not shared_generated


@pytest.mark.parametrize('field,construct,index,tag', [
    ('tied_marks', 'written_tie_attributes', 6, 'tied'),
    ('tuplet_extras', 'tuplet_attributes', 4, 'tuplet'),
])
def test_original_attribute_absence_catches_shared_invented_attribute(field, construct, index, tag):
    original, generated, model = example()
    root = ET.fromstring(generated)
    root.findall('.//note')[index].find(f'notations/{tag}').set('placement', 'below')
    model['notation_events'][index][field][0].insert(0, ['placement', 'below'])
    result = contract.verify_musicxml_contract(original, ET.tostring(root, encoding='unicode'), model)
    assert any(r['status'] == 'mismatch' for r in rows(result, construct, 'original->native'))
    assert {r['status'] for r in rows(result, construct, 'generated->native')} == {'verified'}


@pytest.mark.parametrize('field,construct', [('tied_marks', 'written_tie_attributes'),
                                            ('tuplet_extras', 'tuplet_attributes')])
@pytest.mark.parametrize('index', [0, 5, 7, 8])
def test_missing_field_is_unsupported_even_when_other_facts_or_absence_match(field, construct, index):
    original, generated, model = example()
    del model['notation_events'][index][field]
    result = contract.verify_musicxml_contract(original, generated, model)
    assert result['passed'], result['discrepancies']
    for boundary in ('original->native', 'generated->native'):
        checked = rows(result, construct, boundary)
        assert len(checked) == 9
        assert checked[index]['status'] == 'unsupported'
    direct = contract.verify_generated_contract(generated, model)
    assert rows(direct, construct, 'generated->native')[index]['status'] == 'unsupported'


@pytest.mark.parametrize('field,construct,index', [
    ('tied_marks', 'written_tie_attributes', 5), ('tuplet_extras', 'tuplet_attributes', 0)])
@pytest.mark.parametrize('value', [None, True, {}, 'above', [[['placement']]],
                                  [[['placement', True]]], [[['placement', 'above'], ['placement', 'below']]]])
def test_supplied_wrong_metadata_mismatches_but_unknown_metadata_is_unsupported(field, construct, index, value):
    original, generated, model = example()
    model['notation_events'][index][field] = deepcopy(value)
    result = contract.verify_musicxml_contract(original, generated, model)
    for boundary in ('original->native', 'generated->native'):
        checked = rows(result, construct, boundary)
        assert len(checked) == 9
        assert checked[index]['status'] == (
            'unsupported' if value is None else 'mismatch')


def test_standard_tie_and_tuplet_comparisons_remain_independent_of_new_metadata():
    original, generated, model = example()
    model['notation_events'][5]['tie_start'] = False
    model['notation_events'][0]['time_modification']['actual'] = 7
    model['notation_events'][0]['tuplet_marks'][0]['bracket'] = 'no'
    result = contract.verify_musicxml_contract(original, generated, model)
    for construct in ('ties', 'tuplets'):
        assert any(r['status'] == 'mismatch' for r in rows(result, construct, 'original->native'))


def test_extra_attributes_cannot_be_attached_to_a_missing_native_tuplet_mark():
    original, generated, model = example()
    model['notation_events'][0]['tuplet_marks'] = []
    result = contract.verify_musicxml_contract(original, generated, model)
    for boundary in ('original->native', 'generated->native'):
        assert rows(result, 'tuplet_attributes', boundary)[0]['status'] == 'mismatch'


def test_empty_tied_attribute_bag_cannot_verify_even_if_all_three_inventories_agree():
    original, generated, model = example()
    roots = [ET.fromstring(original), ET.fromstring(generated)]
    for root in roots:
        rest = root.findall('.//note')[7]
        ET.SubElement(ET.SubElement(rest, 'notations'), 'tied')
    model['notation_events'][7]['tied_marks'] = [[]]
    result = contract.verify_musicxml_contract(
        *(ET.tostring(root, encoding='unicode') for root in roots), model)
    for boundary in ('original->native', 'generated->native'):
        assert rows(result, 'written_tie_attributes', boundary)[7]['status'] == 'mismatch'


def test_source_inventory_requires_attributes_and_authored_absence_rows(tmp_path):
    original, generated, model = example()
    path = tmp_path / 'written.musicxml'
    path.write_text(original)
    required = {r['id'] for r in contract.source_inventory(path)}
    assert 'original->native:xml-p0-m0-e7:written_tie_attributes' in required
    assert 'original->native:xml-p0-m0-e5:tuplet_attributes' in required
    assert 'original->generated:xml-p0-m0-e8:written_tie_attributes' in required
    assert 'original->generated:xml-p1-m0-e1:tuplet_attributes' in required
    assert required <= {r['id'] for r in contract.verify_musicxml_contract(
        original, generated, model)['elements']}


def test_unhandled_source_notation_does_not_become_verified_with_new_metadata():
    original, generated, model = example()
    root = ET.fromstring(original)
    root.find('.//notations').append(ET.fromstring('<articulations><staccato/></articulations>'))
    result = contract.verify_musicxml_contract(ET.tostring(root, encoding='unicode'), generated, model)
    assert not result['complete']
    assert any(r['construct'] == 'articulations' and r['boundary'] == 'original'
               and r['status'] == 'unsupported' for r in result['elements'])


def test_historical_model_with_neither_metadata_field_cannot_verify_authored_attributes():
    original, generated, model = example()
    for event in model['notation_events']:
        del event['tied_marks'], event['tuplet_extras']
    result = contract.verify_musicxml_contract(original, generated, model)
    assert result['passed'], result['discrepancies']
    for construct in ('written_tie_attributes', 'tuplet_attributes'):
        for boundary in ('original->native', 'generated->native'):
            checked = rows(result, construct, boundary)
            assert checked
            assert {r['status'] for r in checked} == {'unsupported'}


def test_ratio_only_source_cannot_author_generated_graphical_tuplet_attributes():
    original, generated, model = example()
    root = ET.fromstring(original)
    for notations in root.findall('.//notations'):
        for mark in list(notations.findall('tuplet')):
            notations.remove(mark)
    result = contract.verify_musicxml_contract(ET.tostring(root, encoding='unicode'), generated, model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    for boundary in ('original->generated', 'original->native'):
        checked = rows(result, 'tuplet_attributes', boundary)
        assert {r['status'] for r in checked[:5]} == {'unsupported'}
        assert rows(result, 'tuplet_grouping', boundary)


def test_sound_ties_do_not_certify_inferred_written_tie_attributes():
    original, generated, model = example()
    root = ET.fromstring(original)
    for notations in root.findall('.//notations'):
        for mark in list(notations.findall('tied')):
            notations.remove(mark)
    result = contract.verify_musicxml_contract(ET.tostring(root, encoding='unicode'), generated, model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    for boundary in ('original->generated', 'original->native'):
        assert {r['status'] for r in rows(result, 'written_tie_attributes', boundary)[5:7]} == {'unsupported'}
    assert {r['status'] for r in rows(result, 'written_tie_attributes', 'generated->native')} == {'verified'}


@pytest.mark.parametrize('missing', [('tied_marks',), ('tuplet_extras',),
                                    ('tied_marks', 'tuplet_extras')])
def test_unmarked_historical_model_must_report_every_missing_absence_field(missing, tmp_path):
    from test_phase5_beam_metadata import example as unmarked_example

    original, generated, model = unmarked_example()
    # A complete positive fixture must carry explicit absence. Removing all
    # instances of a field must not remove its obligations from either audit.
    for event in model['notation_events']:
        event.update(tied_marks=[], tuplet_extras=[])
        for field in missing:
            del event[field]
    result = contract.verify_musicxml_contract(original, generated, model)
    direct = contract.verify_generated_contract(generated, model)
    assert result['passed'] and direct['passed']
    assert not result['complete']
    assert not direct['complete']
    for field, construct in [('tied_marks', 'written_tie_attributes'),
                             ('tuplet_extras', 'tuplet_attributes')]:
        want = 'unsupported' if field in missing else 'verified'
        for report, boundary in [(result, 'original->native'), (result, 'generated->native'),
                                 (direct, 'generated->native')]:
            checked = rows(report, construct, boundary)
            assert len(checked) == 6
            assert {r['status'] for r in checked} == {want}
    source = tmp_path / 'unmarked.musicxml'
    source.write_text(original)
    inventory = {r['id'] for r in contract.source_inventory(source)}
    for construct in ('written_tie_attributes', 'tuplet_attributes'):
        assert f'original->native:xml-p0-m0-e5:{construct}' in inventory
        assert f'original->native:xml-p1-m0-e1:{construct}' in inventory
    assert inventory <= {r['id'] for r in result['elements']}


@pytest.mark.parametrize('xml,tag,number,typ,dots', [
    ('<tuplet-actual><tuplet-number>7</tuplet-number><tuplet-type>32nd</tuplet-type>'
     '<tuplet-dot/></tuplet-actual>', 'tuplet-actual', '7', '32nd', 1),
    ('<tuplet-actual><tuplet-number>9</tuplet-number><tuplet-type>64th</tuplet-type>'
     '</tuplet-actual>', 'tuplet-actual', '9', '64th', 0),
    ('<tuplet-normal><tuplet-number>4</tuplet-number><tuplet-type>eighth</tuplet-type>'
     '<tuplet-dot/><tuplet-dot/></tuplet-normal>', 'tuplet-normal', '4', 'eighth', 2),
])
@pytest.mark.parametrize('shared_generated', [False, True])
def test_nested_tuplet_content_blocks_complete_and_preserves_raw_source_evidence(
        xml, tag, number, typ, dots, shared_generated, tmp_path):
    original, generated, model = example()
    root = ET.fromstring(original)
    root.find('.//notations/tuplet').append(ET.fromstring(xml))
    original = ET.tostring(root, encoding='unicode')
    if shared_generated:
        root = ET.fromstring(generated)
        root.find('.//notations/tuplet').append(ET.fromstring(xml))
        generated = ET.tostring(root, encoding='unicode')
    result = contract.verify_musicxml_contract(original, generated, model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    checked = rows(result, 'tuplet_children', 'original')
    assert len(checked) == 1
    row = checked[0]
    assert row['status'] == 'unsupported'
    assert row['source']['measure'] == '1'
    assert row['source']['voice'] == '7'
    raw = ET.fromstring(row['evidence']['xml'])
    assert (raw.tag, raw.findtext('tuplet-number'), raw.findtext('tuplet-type'),
            len(raw.findall('tuplet-dot'))) == (tag, number, typ, dots)
    assert row['expected'] is row['actual'] is None
    path = tmp_path / 'nested.musicxml'
    path.write_text(original)
    required = [r for r in contract.source_inventory(path) if r['construct'] == 'tuplet_children']
    assert len(required) == 1
    assert required[0]['id'] == row['id']
    assert ET.tostring(ET.fromstring(required[0]['evidence']['xml'])) == ET.tostring(raw)
    if shared_generated:
        direct = contract.verify_generated_contract(generated, model)
        assert not direct['complete']
        assert len(rows(direct, 'tuplet_children', 'generated')) == 1
        assert rows(direct, 'tuplet_children', 'generated')[0]['status'] == 'unsupported'
        assert ET.fromstring(rows(direct, 'tuplet_children', 'generated')[0]['evidence']['xml']).tag == tag


def test_each_nested_tuplet_child_and_mark_has_a_distinct_required_obligation(tmp_path):
    original, generated, model = example()
    root = ET.fromstring(original)
    notations = root.find('.//notations')
    mark = notations.find('tuplet')
    mark.append(ET.fromstring('<tuplet-actual><tuplet-number>7</tuplet-number></tuplet-actual>'))
    mark.append(ET.fromstring('<tuplet-normal><tuplet-type>32nd</tuplet-type><tuplet-dot/></tuplet-normal>'))
    another = ET.SubElement(notations, 'tuplet', type='start', number='3')
    another.append(ET.fromstring('<tuplet-actual><tuplet-number>9</tuplet-number></tuplet-actual>'))
    original = ET.tostring(root, encoding='unicode')
    path = tmp_path / 'multiple-nested.musicxml'
    path.write_text(original)
    inventory = [r for r in contract.source_inventory(path) if r['construct'] == 'tuplet_children']
    result = contract.verify_musicxml_contract(original, generated, model)
    actual = rows(result, 'tuplet_children', 'original')
    assert len(inventory) == len(actual) == 3
    assert len({r['id'] for r in inventory}) == 3
    assert {r['id'] for r in inventory} == {r['id'] for r in actual}
    assert {r['status'] for r in actual} == {'unsupported'}
    assert [ET.fromstring(r['evidence']['xml']).tag for r in actual] == [
        'tuplet-actual', 'tuplet-normal', 'tuplet-actual']


@pytest.mark.parametrize('xml,construct,raw_tags', [
    ('<rest measure="yes"/>', 'rest_attributes', ['rest']),
    ('<rest display="no"/>', 'rest_attributes', ['rest']),
    ('<rest><display-step>F</display-step><display-octave>3</display-octave></rest>',
     'rest_display', ['display-step', 'display-octave']),
])
@pytest.mark.parametrize('shared_generated', [False, True])
def test_unrepresented_rest_attributes_and_display_are_explicit_source_blockers(
        xml, construct, raw_tags, shared_generated, tmp_path):
    original, generated, model = example()
    root = ET.fromstring(original)
    note = root.findall('.//note')[-1]
    note.remove(note.find('rest'))
    note.insert(0, ET.fromstring(xml))
    original = ET.tostring(root, encoding='unicode')
    if shared_generated:
        root = ET.fromstring(generated)
        note = root.findall('.//note')[-1]
        note.remove(note.find('rest'))
        note.insert(0, ET.fromstring(xml))
        generated = ET.tostring(root, encoding='unicode')
    result = contract.verify_musicxml_contract(original, generated, model)
    assert result['passed'], result['discrepancies']
    assert not result['complete']
    checked = rows(result, construct, 'original')
    assert len(checked) == len(raw_tags)
    assert {r['status'] for r in checked} == {'unsupported'}
    assert {r['source']['staff'] for r in checked} == {'1'}
    raw = [ET.fromstring(r['evidence']['xml']) for r in checked]
    assert [r.tag for r in raw] == raw_tags
    if construct == 'rest_attributes':
        assert raw[0].attrib == ET.fromstring(xml).attrib
    else:
        assert [r.text for r in raw] == ['F', '3']
    path = tmp_path / 'rest-metadata.musicxml'
    path.write_text(original)
    required = [r for r in contract.source_inventory(path) if r['construct'] == construct]
    assert {r['id'] for r in required} == {r['id'] for r in checked}
    assert len({r['id'] for r in required}) == len(checked)
    assert [ET.fromstring(r['evidence']['xml']).tag for r in required] == raw_tags
    if shared_generated:
        direct = contract.verify_generated_contract(generated, model)
        assert direct['passed']
        assert not direct['complete']
        generated_rows = rows(direct, construct, 'generated')
        assert len(generated_rows) == len(raw_tags)
        assert {r['status'] for r in generated_rows} == {'unsupported'}
        assert [ET.fromstring(r['evidence']['xml']).tag for r in generated_rows] == raw_tags
