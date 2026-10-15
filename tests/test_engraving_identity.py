"""Real engraving retains each required attack through voices and tied glyphs."""
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest
import verovio

from piano_teacher.music import Note, Phrase
from piano_teacher.lesson_score import build_lesson_score, LessonScore
from piano_teacher.score import render_layout, _create_verovio_toolkit
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.feedback import project_assessment
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.score_geometry import locate_beat


def note(start, end, pitch=60, *, hand='right', identity='attack', voice='1', track=0):
    return Note(start, end, pitch, track, 0, hand, source_id=identity, voice=voice)


def engrave(notes, *, end=8, start=0, bars=2):
    phrase = Phrase(1, 1, bars, start, end, tuple(notes))
    lesson = build_lesson_score(phrase)
    score = render_layout(lesson, 1, bars, 'both', total_beats=end-start, bpm=80)
    require_lesson_alignment(phrase, score.layout, 'both')
    return phrase, lesson, score


def test_real_cross_hand_unison_feedback_uses_source_attack_instead_of_glyph_sort_order():
    right = note(0, 1, identity='z-right')
    left = note(0, 1, hand='left', identity='a-left', track=1)
    phrase, _, score = engrave([right, left])
    assessment = Assessment((NoteAssessment(right, 'correct'), NoteAssessment(left, 'missed')), 0)
    projected = project_assessment(assessment, phrase, 80, score.layout)
    by_id = {glyph['id']: glyph for glyph in score.layout['notes']}
    assert projected['unmapped'] == 0
    assert [by_id[mark['note_id']]['source_id'] for mark in projected['marks']] == ['z-right', 'a-left']
    assert [by_id[mark['note_id']]['hand'] for mark in projected['marks']] == ['right', 'left']
    assert projected['marks'][0]['y'] < projected['marks'][1]['y']


def test_overlapping_unison_ties_keep_the_same_source_voice_across_barline():
    _, lesson, score = engrave([note(0, 6, identity='A'), note(2, 5, identity='B')])
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.loadData(lesson.musicxml)
    mei = ET.fromstring(toolkit.getMEI())
    ties = [element for element in mei.iter() if element.tag.rsplit('}', 1)[-1] == 'tie']
    assert len(ties) == 2
    for tie in ties:
        first = lesson.note_bindings[tie.get('startid').removeprefix('#')]
        last = lesson.note_bindings[tie.get('endid').removeprefix('#')]
        assert first['source_id'] == last['source_id']
        assert first['is_attack'] and not last['is_attack']
    assert set(score.layout['attack_map']) == {'A', 'B'}
    assert len(score.layout['continuation_map']['A']) == 1
    assert len(score.layout['continuation_map']['B']) == 1


def test_compound_duration_continuations_do_not_become_required_attacks():
    phrase, lesson, score = engrave([note(0, .625, 72, identity='C')])
    assert len(score.layout['notes']) == 2
    assert len(score.layout['attack_map']) == 1
    first, second = sorted(score.layout['notes'], key=lambda glyph: glyph['beat'])
    assert (first['source_id'], first['is_attack'], first['segment_index'], first['source_beat']) == ('C', True, 0, 0)
    assert (second['source_id'], second['is_attack'], second['segment_index'], second['source_beat']) == ('C', False, 1, 0)
    assert second['beat'] == .5
    broken = deepcopy(score.layout)
    broken['notes'] = [second]
    broken['attack_map'] = {}
    with pytest.raises(ValueError, match='attack|omitted'):
        require_lesson_alignment(phrase, broken, 'both')


def test_source_attack_anchor_remains_exact_when_notation_rounds_to_divisions():
    onset = 1/11
    _, _, score = engrave([note(12+onset, 13, 72, identity='precise')], start=12, end=20)
    glyph = next(glyph for glyph in score.layout['notes'] if glyph['is_attack'])
    assert glyph['source_beat'] == pytest.approx(onset, abs=1e-14)
    assert glyph['beat'] != onset
    point = locate_beat(score.layout, glyph['source_beat'])
    assert point['page'] == glyph['page'] and point['x'] == pytest.approx(glyph['x'], abs=1e-12)


def test_renderer_rejects_missing_bound_note_instead_of_matching_another_pitch_or_continuation():
    phrase = Phrase(1, 1, 1, 0, 4, (note(0, 1, identity='required'),))
    lesson = build_lesson_score(phrase)
    root = ET.fromstring(lesson.musicxml)
    target = next(element for element in root.iter('note') if element.find('pitch') is not None)
    target.set('id', 'unmapped-replacement')
    modified = LessonScore(ET.tostring(root, encoding='unicode'), phrase,
                           lesson.note_bindings, lesson.staff_clefs)
    with pytest.raises(ValueError, match='mapped|mapping|bound|identity'):
        render_layout(modified, 1, 1, 'both', total_beats=4, bpm=80)


@pytest.mark.parametrize('field,value', [('pitch', 61), ('hand', 'left'), ('is_attack', False)])
def test_strict_validator_rejects_incorrect_attack_metadata(field, value):
    phrase, _, score = engrave([note(0, 1, identity='required')])
    corrupted = deepcopy(score.layout)
    attack = next(glyph for glyph in corrupted['notes'] if glyph['is_attack'])
    attack[field] = value
    with pytest.raises(ValueError, match='attack|pitch|hand|mapping'):
        require_lesson_alignment(phrase, corrupted, 'both')


def test_canonical_source_cannot_use_the_legacy_pitch_onset_validation_path():
    phrase = Phrase(1, 1, 1, 0, 4, (note(0, 1, identity='canonical'),))
    with pytest.raises(ValueError, match='identity|mapping'):
        require_lesson_alignment(phrase, {'notes': [{'pitch': 60, 'beat': 0}]}, 'both')


def test_unrepresentable_distinct_attacks_report_quantization_collision():
    phrase = Phrase(1, 1, 1, 0, 4,
                    (note(0, .1, identity='A'), note(.000001, .2, identity='B')))
    with pytest.raises(ValueError, match='quantiz|represent|resolution|collision'):
        build_lesson_score(phrase)


def test_xml_ids_are_reproducible_and_distinct_for_identical_source_unisons():
    notes = (note(0, 1, identity='A'), note(0, 1, identity='B'))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    one, two = build_lesson_score(phrase), build_lesson_score(phrase)
    assert one.note_bindings == two.note_bindings
    assert len(one.note_bindings) == 2
    assert len(set(one.note_bindings)) == 2


def test_duplicate_source_id_across_hands_is_rejected_before_emitting_false_continuation():
    phrase = Phrase(1, 1, 1, 0, 4,
                    (note(0, 1, identity='same'), note(0, 1, hand='left', identity='same')))
    with pytest.raises(ValueError, match='Duplicate.*identity'):
        build_lesson_score(phrase)
