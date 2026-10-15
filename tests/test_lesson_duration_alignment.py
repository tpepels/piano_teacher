"""Unusual durations must not silently shift later required note onsets."""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score, DIVISIONS
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.score import render_layout


def render(notes, *, bars=1):
    pytest.importorskip('verovio')
    pytest.importorskip('music21')
    phrase = Phrase(1, 1, bars, 0, bars * 4, tuple(notes))
    lesson = build_lesson_score(phrase)
    score = render_layout(lesson, 1, bars, total_beats=phrase.end)
    require_lesson_alignment(phrase, score.layout, 'both')
    return lesson, score


def test_two_and_half_beat_rest_keeps_next_attack_at_beat_three():
    _, score = render([Note(0, 4, 48, 0, 0, 'left'),
                       Note(0, .5, 72, 0, 0, 'right'),
                       Note(3, 3.5, 76, 0, 0, 'right')])
    assert next(n['beat'] for n in score.layout['notes'] if n['pitch'] == 76) == pytest.approx(3)


def test_compound_chord_duration_uses_ties_and_keeps_original_attacks_aligned():
    lesson, score = render([Note(0, .625, 72, 0, 0, 'right'),
                           Note(0, .625, 76, 0, 0, 'right'),
                           Note(.625, 1.25, 79, 0, 0, 'right')])
    assert [(n['pitch'], n['beat']) for n in score.layout['notes']
            if n['beat'] in (0, .625)] == [(72, 0), (76, 0), (79, .625)]
    root = ET.fromstring(lesson.musicxml)
    first = root.find('./part[@id="RH"]/measure')
    pitched = [n for n in first.findall('note') if n.find('pitch') is not None]
    assert [int(n.findtext('duration')) for n in pitched[:4]] == [DIVISIONS//2, DIVISIONS//2, DIVISIONS//8, DIVISIONS//8]
    assert all(n.find("tie[@type='start']") is not None for n in pitched[:2])
    assert all(n.find("tie[@type='stop']") is not None for n in pitched[2:4])
    assert sum(n.find('chord') is not None for n in pitched[:4]) == 2


def test_fractional_midi_onset_remains_aligned_after_precise_rest():
    _, score = render([Note(0, .5, 72, 0, 0, 'right'),
                       Note(2 + 1/3, 3, 76, 0, 0, 'right')])
    assert next(n['beat'] for n in score.layout['notes'] if n['pitch'] == 76) == pytest.approx(2 + 1/3, abs=.0001)
