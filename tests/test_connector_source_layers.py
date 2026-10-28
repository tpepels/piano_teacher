"""Anonymous connector rests bind to complete, uniquely anchored source voices."""
from copy import deepcopy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.captured_frames import CapturedFrames
from piano_teacher.notation.connector_pixels import _classes, _inventory, _pages
from piano_teacher.notation.proof import read_written_score
from piano_teacher.notation.assets.tuplets import extract_tuplets


FIXTURE = Path(__file__).parent/'fixtures/connector_pixels/moonlight-rest-voices'
REST = 'd136ubua'
FIRST_NOTE = 'ptd3008fcebe8d7aa2a3fd348cc7e9a0eas0'
SECOND_NOTE = 'pta8a78123b2ef55ec1b74100c266d7194s0'
GROUP = 'cjpg4u4'


def documents():
    return (FIXTURE/'score.musicxml').read_text(), (FIXTURE/'verovio-0.svg').read_text()


def test_actual_polyphonic_tuplet_rest_has_one_complete_source_voice_binding():
    xml, svg = documents()
    written = read_written_score(xml)
    _, aliases = _pages(written, [svg])
    assert (0, REST) in aliases, 'The visible rest must survive hidden secondary-voice padding'
    event = aliases[0, REST]
    assert (event['source']['id'], event['voice'], event['visible']) == ('xml-p0-m0-e1', '1', True)
    rows = _inventory(written, [svg], 'tuplet', 'right')
    bound = next(row for row in rows if row.get('group') == GROUP)
    assert bound['error'] is None, bound.get('error')
    assert [e['source']['id'] for e in bound['leaders']] == [
        'xml-p0-m0-e1', 'xml-p0-m0-e2', 'xml-p0-m0-e3']
    assert bound['ids'] == [REST, FIRST_NOTE, SECOND_NOTE]
    assert bound['number'] and bound['bracket']


def test_hidden_padding_cannot_make_a_unique_actual_rest_anchor_ambiguous():
    xml, _ = documents()
    written = read_written_score(xml)
    rest = next(e for e in written.symbols if e['source']['id'] == 'xml-p0-m0-e1')
    anchor = CapturedFrames(FIXTURE, written).rest(rest)
    assert anchor['score'] >= .79
    assert 625 < anchor['x'] < 665


def test_printed_layer_order_cannot_change_preserved_source_voice_identity():
    xml, svg = documents()
    root = ET.fromstring(svg)
    staff = next(n for n in root.iter() if 'staff' in _classes(n)
                 and any(child.get('id') == REST for child in n.iter()))
    layers = [n for n in staff if 'layer' in _classes(n)]
    for layer in layers:
        staff.remove(layer)
    staff.extend(reversed(layers))
    _, aliases = _pages(read_written_score(xml), [ET.tostring(root, encoding='unicode')])
    assert aliases[0, REST]['source']['id'] == 'xml-p0-m0-e1'


@pytest.mark.parametrize('damage', ['svg-note-id', 'svg-remote-note-id', 'xml-note-id', 'source-voice',
                                  'visible-extra-rest', 'duplicate-layer'])
def test_source_layer_binding_rejects_bad_identity_and_ambiguous_real_layers(damage):
    xml, svg = documents()
    source, root = ET.fromstring(xml), ET.fromstring(svg)
    if damage == 'svg-note-id':
        next(n for n in root.iter() if n.get('id') == FIRST_NOTE).set('id', 'wrong-source-note')
    elif damage == 'svg-remote-note-id':
        next(n for n in root.iter() if n.get('id') == 'pta5d8a5fb09fa888ea263d23692a76830s0').set(
            'id', 'wrong-note-outside-the-tuplet')
    elif damage == 'xml-note-id':
        next(n for n in source.iter('note') if n.get('id') == FIRST_NOTE).set('id', 'wrong-source-note')
    elif damage == 'source-voice':
        next(n for n in source.iter('note') if n.get('id') == FIRST_NOTE).find('voice').text = '2'
    elif damage == 'visible-extra-rest':
        next(n for n in source.iter('note') if n.get('print-object') == 'no').attrib.pop('print-object')
    else:
        parents = {child: parent for parent in root.iter() for child in parent}
        layer = next(n for n in root.iter() if 'layer' in _classes(n)
                     and any(child.get('id') == REST for child in n.iter()))
        duplicate = deepcopy(layer)
        duplicate.set('id', 'second-real-layer-with-the-same-source-events')
        parents[layer].append(duplicate)
    written = read_written_score(ET.tostring(source, encoding='unicode'))
    changed = ET.tostring(root, encoding='unicode')
    _, aliases = _pages(written, [changed])
    assert (0, REST) not in aliases
    rows = _inventory(written, [changed], 'tuplet', 'right')
    assert any(row.get('group') == GROUP and row.get('error') for row in rows)


def test_genuinely_visible_simultaneous_rests_still_cannot_share_a_pixel_anchor():
    xml, _ = documents()
    root = ET.fromstring(xml)
    rest = next(n for n in root.iter('note') if n.findtext('voice') == '2'
                and n.find('rest') is not None)
    rest.attrib.pop('print-object')
    written = read_written_score(ET.tostring(root, encoding='unicode'))
    event = next(e for e in written.symbols if e['source']['id'] == 'xml-p0-m0-e1')
    with pytest.raises(ValueError, match='Simultaneous anonymous rest anchors'):
        CapturedFrames(FIXTURE, written).rest(event)


def test_hidden_source_rest_cannot_borrow_a_visible_rests_pixels():
    xml, _ = documents()
    written = read_written_score(xml)
    hidden = next(e for e in written.symbols if e['kind'] == 'rest' and not e['visible']
                  and e['voice'] == '2')
    # Even a hidden padding rest with the visible rest's exact contour type
    # must never acquire its pixels after hidden events leave the candidate set.
    hidden['note_type'] = 'eighth'
    with pytest.raises(ValueError, match='Hidden source rest'):
        CapturedFrames(FIXTURE, written).rest(hidden)


def test_existing_native_asset_binding_agrees_without_borrowing_model_aliases():
    _, svg = documents()
    model = json.loads((FIXTURE/'model.json').read_text())
    fragments = extract_tuplets([svg], model)
    key = '|'.join(['rest:right:29:0', FIRST_NOTE, SECOND_NOTE])
    assert key in fragments
    assert fragments[key]['note_ids'] == ['rest:right:29:0', FIRST_NOTE, SECOND_NOTE]
