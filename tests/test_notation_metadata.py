"""Notation keeps explicit source spelling/context and readable registers."""
from xml.etree import ElementTree as ET
import pytest

from piano_teacher.music import Note, Phrase, KeySignature, ClefChange
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.score import render_layout


def test_explicit_flat_key_spelling_and_readable_treble_left_hand_are_preserved():
    notes = (Note(0, 4, 82, 1, 0, 'left', source_id='left-bb', spelling=('B', -1, 5)),
             Note(0, 4, 94, 0, 0, 'right', source_id='right-bb', spelling=('B', -1, 6)))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    lesson = build_lesson_score(phrase, key_signatures=(KeySignature(0, -1),),
                                clef_changes=(ClefChange(0, 'G', 2, hand='left'),))
    xml = ET.fromstring(lesson.musicxml)
    for part in xml.findall('part'):
        assert part.findtext('measure/attributes/key/fifths') == '-1'
        assert part.findtext('measure/note/pitch/step') == 'B'
        assert part.findtext('measure/note/pitch/alter') == '-1'
        assert part.findtext('measure/attributes/clef/sign') == 'G'
        assert not part.findall('.//accidental')  # The key signature already supplies B-flat.
    score = render_layout(lesson, 1, 1, 'both', total_beats=4, bpm=80)
    assert score.layout['staff_clefs']['left']['sign'] == 'G'


def test_midi_without_key_metadata_does_not_claim_an_explicit_c_major_key():
    phrase = Phrase(1, 1, 1, 0, 4, (Note(0, 1, 61, 0, 0, 'right'),))
    xml = ET.fromstring(build_lesson_score(phrase).musicxml)
    assert not xml.findall('.//key')
    assert xml.findtext('./part[@id="RH"]/measure/note/accidental') == 'sharp'


def test_key_and_clef_context_at_excerpt_start_and_later_changes_are_retained():
    notes = (Note(8, 9, 61, 0, 0, 'right', spelling=('D', -1, 4)),
             Note(12, 13, 60, 0, 0, 'right', spelling=('C', 0, 4)))
    phrase = Phrase(2, 3, 4, 8, 16, notes)
    lesson = build_lesson_score(phrase, boundaries=(0, 4, 8, 12, 16),
        key_signatures=(KeySignature(0, 0), KeySignature(4, -5), KeySignature(12, 0)),
        clef_changes=(ClefChange(0, 'F', 4, hand='right'), ClefChange(4, 'G', 2, hand='right')))
    measures = ET.fromstring(lesson.musicxml).findall('./part[@id="RH"]/measure')
    assert [m.findtext('attributes/key/fifths') for m in measures] == ['-5', '0']
    assert measures[0].findtext('attributes/clef/sign') == 'G'
    assert lesson.staff_clefs['right'] == {'sign': 'G', 'line': 2, 'octave_change': 0}


def test_high_left_and_low_right_without_source_clefs_choose_readable_staves():
    phrase = Phrase(1, 1, 1, 0, 4,
                    (Note(0, 1, 84, 0, 0, 'left'), Note(0, 1, 36, 1, 0, 'right')))
    lesson = build_lesson_score(phrase)
    assert lesson.staff_clefs['left']['sign'] == 'G'
    assert lesson.staff_clefs['right']['sign'] == 'F'
    assert {binding['pitch'] for binding in lesson.note_bindings.values()} == {36, 84}


def test_midi_tied_pitch_keeps_attack_spelling_across_an_enharmonic_key_change():
    phrase = Phrase(1, 1, 2, 0, 8, (Note(0, 6, 66, 0, 0, 'right', source_id='held-f-sharp'),))
    lesson = build_lesson_score(phrase, key_signatures=(KeySignature(0, 1), KeySignature(4, -6)))
    pitched = ET.fromstring(lesson.musicxml).findall('./part[@id="RH"]/measure/note/pitch')
    assert [(pitch.findtext('step'), pitch.findtext('alter')) for pitch in pitched] == [('F', '1'), ('F', '1')]


def test_explicit_octave_clef_keeps_sounding_pitch_and_opening_metadata():
    phrase = Phrase(1, 1, 1, 0, 4, (Note(0, 1, 84, 0, 0, 'right', source_id='high-c'),))
    lesson = build_lesson_score(phrase, clef_changes=(ClefChange(0, 'G', 2, 1, 'right'),))
    score = render_layout(lesson, 1, 1, 'both', total_beats=4, bpm=80)
    assert score.layout['staff_clefs']['right']['octave_change'] == 1
    assert score.layout['notes'][0]['pitch'] == 84


@pytest.mark.parametrize('count,note_type,normal', [(3,'eighth',2), (5,'16th',4), (7,'16th',4)])
def test_standard_tuplets_use_one_conventional_note_per_attack_and_one_group(count, note_type, normal):
    notes = tuple(Note(i/count, (i+1)/count, 60+i, 0, 0, 'right', source_id=f'tuplet-{i}')
                  for i in range(count))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    lesson = build_lesson_score(phrase)
    xml = ET.fromstring(lesson.musicxml)
    pitched = [note for note in xml.findall('./part[@id="RH"]/measure/note') if note.find('pitch') is not None]
    assert len(pitched) == count and not xml.findall('.//tie')
    assert all(note.findtext('type') == note_type for note in pitched)
    assert all(note.findtext('time-modification/actual-notes') == str(count) for note in pitched)
    assert all(note.findtext('time-modification/normal-notes') == str(normal) for note in pitched)
    assert sum(len(note.findall('./notations/tuplet[@type="start"]')) for note in pitched) == 1
    assert sum(len(note.findall('./notations/tuplet[@type="stop"]')) for note in pitched) == 1
    score = render_layout(lesson, 1, 1, 'right', total_beats=4, bpm=80)
    assert len(score.layout['attack_map']) == count and not score.layout['continuation_map']
