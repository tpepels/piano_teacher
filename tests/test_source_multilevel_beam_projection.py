"""Real importer -> lesson -> model regression for layered source beams."""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.source_annotations import project_annotations


def _piece(tmp_path, secondary, *, split_primary=False):
    primary = ('begin', 'end', 'begin', 'end') if split_primary else (
        'begin', 'continue', 'continue', 'end')
    notes = []
    for i, (step, first, second) in enumerate(zip('CDEF', primary, secondary)):
        notes.append(f'''<note id="original-{i}"><pitch><step>{step}</step><octave>4</octave></pitch>
          <duration>2</duration><voice>1</voice><type>16th</type>
          <beam number="1" fan="accel">{first}</beam>
          <beam number="2" repeater="yes" color="#202020">{second}</beam></note>''')
    xml = '''<score-partwise version="4.0"><part-list>
      <score-part id="RH"><part-name>Right Hand</part-name></score-part>
      <score-part id="LH"><part-name>Left Hand</part-name></score-part></part-list>
      <part id="RH"><measure number="1"><attributes><divisions>8</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>''' + ''.join(notes) + '''
      <note><rest/><duration>24</duration><voice>1</voice><type>half</type><dot/></note>
      </measure></part><part id="LH"><measure number="1"><attributes><divisions>8</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef>
      </attributes><note><pitch><step>C</step><octave>3</octave></pitch><duration>32</duration>
      <voice>1</voice><type>whole</type></note></measure></part></score-partwise>'''
    path = tmp_path/'multilevel.musicxml'
    path.write_text(xml)
    return load_musicxml(path, bpm=80)


def _lesson(piece, indices=None, *, annotated=True):
    right = [n for n in piece.notes if n.hand == 'right']
    notes = piece.notes if indices is None else tuple(right[i] for i in indices)
    phrase = Phrase(1, 1, 1, 0., 4., tuple(notes))
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml if annotated else '')
    return score


@pytest.mark.parametrize('secondary', [
    ('begin', 'continue', 'continue', 'end'),
    ('begin', 'end', 'begin', 'end'),
    ('begin', 'end', 'forward hook', 'backward hook'),
])
def test_all_levels_hooks_and_attributes_survive_original_to_model(tmp_path, secondary):
    piece = _piece(tmp_path, secondary)
    original = piece.source_musicxml
    score = _lesson(piece)
    root = ET.fromstring(score.musicxml)
    actual = [[(b.get('number'), b.text, dict(b.attrib)) for b in n.findall('beam')]
              for n in root.findall("part[@id='RH']/measure/note") if n.find('pitch') is not None]
    expected = [[('1', first, {'number': '1', 'fan': 'accel'}),
                 ('2', second, {'number': '2', 'repeater': 'yes', 'color': '#202020'})]
                for first, second in zip(('begin', 'continue', 'continue', 'end'), secondary)]
    assert actual == expected  # Exactly once per mark, in original XML order.
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    right = [e for e in model['notation_events'] if e['staff'] == 'right' and e['kind'] == 'note']
    assert [e['beams'] for e in right] == [
        [['1', first, [['fan', 'accel']]],
         ['2', second, [['color', '#202020'], ['repeater', 'yes']]]]
        for first, second in zip(('begin', 'continue', 'continue', 'end'), secondary)]
    assert len(model['notes']) == len(piece.notes) == 5
    assert piece.source_musicxml == original


@pytest.mark.parametrize('indices', [(0, 1), (1, 2), (2, 3), (0, 2, 3)])
def test_partial_primary_group_does_not_leak_complete_secondary_groups(tmp_path, indices):
    piece = _piece(tmp_path, ('begin', 'end', 'begin', 'end'))
    score = _lesson(piece, indices)
    assert not ET.fromstring(score.musicxml).findall('.//beam')
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert len(model['notes']) == len(indices)
    assert all(not e['beams'] for e in model['notation_events'])


def test_variant_retains_a_complete_primary_group_and_all_its_levels(tmp_path):
    piece = _piece(tmp_path, ('begin', 'end', 'begin', 'end'), split_primary=True)
    score = _lesson(piece, (0, 1))
    root = ET.fromstring(score.musicxml)
    assert [(b.get('number'), b.text) for b in root.findall('.//beam')] == [
        ('1', 'begin'), ('2', 'begin'), ('1', 'end'), ('2', 'end')]
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert len(model['notes']) == 2
    assert sum(len(e['beams']) for e in model['notation_events']) == 4


def test_preexisting_generated_beam_conflicts_are_still_rejected(tmp_path):
    piece = _piece(tmp_path, ('begin', 'continue', 'continue', 'end'))
    score = _lesson(piece, annotated=False)
    root = ET.fromstring(score.musicxml)
    first = root.find("part[@id='RH']/measure/note[pitch]")
    ET.SubElement(first, 'beam', number='1').text = 'end'
    with pytest.raises(ValueError, match='Conflicting source beam marks'):
        project_annotations(piece.source_musicxml, ET.tostring(root, encoding='unicode'),
            score.note_bindings, score.phrase, boundaries=piece.bar_boundaries)
