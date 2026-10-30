"""One non-vacuous source MusicXML exercise through all four Coda categories.

These are research-only semantic contracts. They test source identity,
polyphony, notation context, transformation timing and reversible mapping;
they are not parity checks against the unavailable Coda implementation.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.exercise_contracts import OriginalTiming, assess_timed
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_polyphony import PolyphonicChordifier
from piano_teacher.research.coda_research_strategies import (
    ResearchPartSplitter, ResearchPolyphonicDottedRhythm, ResearchTempoShaper,
)

SOURCE = Path(__file__).parent / "fixtures/research/coda_four_families.musicxml"


def scenario():
    piece = load_musicxml(SOURCE,bpm=80)
    assert piece.bar_boundaries == (0,4,8)
    phrase = Phrase(1,1,2,0,8,piece.notes)
    return piece,ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))


def test_coda_four_families_share_one_source_backed_matrix():
    piece, original = scenario()
    matrix=MatrixScore.from_phrase(
        original.phrase,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    assert len(original.notes) == 16
    assert matrix.note_count == 16
    assert matrix.written_rest_count == 1
    assert len(matrix.notation_parts) == 2
    assert [len(p.voices) for p in matrix.notation_parts] == [2,1]
    assert matrix.notation_parts[0].measures[1].context.at_entry("clef") is not None
    inherited=matrix.notation_parts[0].measures[1].context.at_entry("time")
    assert ET.fromstring(inherited.xml).findtext("beats")=="4"
    matrix.verify_lossless()

    split=ResearchPartSplitter(measures_per_passage=1).split(
        original,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    assert len(split)==2
    assert [item.variant.phrase.first_bar for item in split] == [1,2]
    assert tuple(i for item in split for i in item.variant.source_indices) == (
        original.source_indices)
    assert sum(item.matrix.written_rest_count for item in split) == 1
    assert all(item.matrix.original_musicxml == piece.source_musicxml for item in split)

    chords=PolyphonicChordifier().transform(
        original,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    dotted=ResearchPolyphonicDottedRhythm().transform(
        original,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    assert len(chords.decisions) >= 4
    assert len(dotted.decisions) >= 4
    assert {decision.hand for decision in chords.decisions} == {"left","right"}
    assert len({decision.voice for decision in dotted.decisions}) == 2

    baseline=OriginalTiming().transform(original)
    tempo=ResearchTempoShaper(slow_fraction=.5).generate(
        baseline,80,boundaries=piece.bar_boundaries)
    assert [(seg.start_beat,seg.end_beat,seg.bpm)
            for seg in tempo.segments] == [(0,4,40),(4,8,80)]
    assert tempo.seconds_at(8) == pytest.approx(9)
    assert tempo.beat_at(tempo.seconds_at(6)) == pytest.approx(6)

    expected_ids=tuple(note.source_id for note in original.notes)
    for changed in (chords.timing,dotted.timing,baseline):
        assert tuple(note.source_id for note in changed.exercise_phrase.notes) == expected_ids
        assert len(changed.events) == 16
        assert {event.source_index for event in changed.events} == set(range(16))
        assert all(event.exercise_end > event.exercise_start for event in changed.events)
        assert changed.duration_beats == pytest.approx(8)
    assert original.phrase.notes == baseline.exercise_phrase.notes
    assert chords.timing.exercise_phrase.notes != original.phrase.notes
    assert dotted.timing.exercise_phrase.notes != original.phrase.notes

    performed=[PlayedNote(note.pitch,tempo.seconds_at(note.start),
                          tempo.seconds_at(note.end))
               for note in baseline.exercise_phrase.notes]
    assert assess_timed(baseline,"both",80,performed,tempo_map=tempo).assessment.clean
    matrix.verify_lossless()


def test_four_family_fixture_retains_all_original_source_notation():
    piece,_=scenario()
    root=ET.fromstring(piece.source_musicxml)
    assert len(root.findall("part"))==2
    assert len(root.findall(".//backup"))==1
    assert len(root.findall(".//rest"))==1
    assert len(root.findall(".//attributes/key"))==2
