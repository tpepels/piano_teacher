"""Sounding alterations must also be visible to the pianist reading the score."""
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.score import render_layout


def test_lesson_accidentals_follow_measure_context_across_voices():
    notes = (Note(0, 1, 66, 0, 0, 'right'),
             Note(1, 2, 66, 0, 0, 'right'),
             Note(2, 3, 65, 0, 0, 'right'),
             Note(3, 4, 66, 0, 0, 'right'),
             Note(4, 5, 66, 0, 0, 'right'),
             # A second voice begins after the first voice's cancellation.
             Note(2.5, 3.5, 66, 0, 0, 'right'))
    score = build_lesson_score(Phrase(1, 1, 2, 0, 8, notes), boundaries=(0, 4, 8))
    root = ET.fromstring(score.musicxml)
    first, second = root.find("part").findall("measure")
    # Document voice order differs from onset order: the 2.5-beat sharp
    # restores the context before the first voice's 3-beat F sharp.
    assert [n.findtext('accidental') for n in first.findall('note') if n.find('pitch') is not None] == [
        'sharp', None, 'natural', None, 'sharp']
    assert second.find('note').findtext('accidental') == 'sharp'


def test_real_engraving_keeps_visible_sharp_and_ledger_ink_bounds():
    pytest.importorskip('verovio')
    notes = (Note(0, 1, 85, 0, 0, 'right'), Note(0, 1, 66, 0, 0, 'right'),
             Note(1, 2, 84, 0, 0, 'right'), Note(2, 3, 65, 0, 0, 'right'))
    score = render_layout(build_lesson_score(Phrase(1, 1, 1, 0, 4, notes), boundaries=(0, 4)),
                          1, 1, 'right', total_beats=4)
    root = ET.fromstring(score.pages[0])
    accidentals = [g for g in root.iter() if 'accid' in g.get('class', '').split()
                   and any(e.tag.endswith('use') for e in g.iter())]
    assert len(accidentals) == 4  # C sharp, F sharp, C natural, F natural.
    first, ledger = score.layout['anchors'][:2]
    assert first['ink_left'] < first['x']
    assert ledger['ink_left'] < ledger['x']
    assert not any('bounding-box' in e.get('class', '') for e in root.iter())
