"""Short, source-backed Coda category experiments; no fidelity claims."""
from dataclasses import replace
from pathlib import Path

import pytest

from piano_teacher.exercise_contracts import OriginalTiming, assess_timed
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.research.coda_research_strategies import (
    ResearchPartSplitter, ResearchTempoShaper, ResearchPolyphonicDottedRhythm,
)


def sample():
    notes = tuple(
        Note(float(i), float(i+1), 60+i, 0, 0, "right", f"n{i}", "v1")
        for i in range(8))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    return ExerciseVariant("original", phrase, tuple(range(8)))


def test_passage_split_is_exact_reversible_source_partition():
    original = sample()
    chunks = ResearchPartSplitter().split(original, boundaries=(0,4,8))
    assert [(s.variant.phrase.first_bar, s.variant.phrase.last_bar,
             s.variant.source_indices) for s in chunks] == [
        (1,1,(0,1,2,3)), (2,2,(4,5,6,7))]
    assert sum((list(chunk.variant.notes) for chunk in chunks), []) == list(original.notes)
    assert all(chunk.matrix.verify_lossless() is None for chunk in chunks)


def test_part_split_refuses_sustained_note_across_cut():
    original = sample()
    phrase = replace(original.phrase,
                     notes=(replace(original.notes[3], end=4.5), *original.notes[4:]))
    source = ExerciseVariant("original", phrase, tuple(range(3,8)))
    with pytest.raises(ValueError, match="crosses passage boundary"):
        ResearchPartSplitter().split(source, boundaries=(0,4,8))


def test_tempo_shaping_matches_seconds_and_grader_on_two_measures():
    original = sample()
    timing = OriginalTiming().transform(original)
    tempo = ResearchTempoShaper(slow_fraction=.5).generate(
        timing, 60, boundaries=(0,4,8))
    assert [(s.start_beat,s.end_beat,s.bpm) for s in tempo.segments] == [
        (0,4,30),(4,8,60)]
    assert tempo.seconds_at(4) == pytest.approx(8)
    assert tempo.seconds_at(8) == pytest.approx(12)
    assert tempo.beat_at(10) == pytest.approx(6)
    played = [PlayedNote(n.pitch, tempo.seconds_at(n.start),
                         tempo.seconds_at(n.end))
              for n in timing.exercise_phrase.notes]
    assert assess_timed(timing, "right", 60, played, tempo_map=tempo).assessment.clean
    reversed_tempo = ResearchTempoShaper(slow_fraction=.5, reverse=True).generate(
        timing, 60, boundaries=(0,4,8))
    assert [s.bpm for s in reversed_tempo.segments] == [60,30]


@pytest.mark.parametrize("long_first,expected", [(True,1.5),(False,.5)])
def test_dotted_transform_retains_source_ids_and_total_span(long_first,expected):
    original = sample()
    result = ResearchPolyphonicDottedRhythm(long_first).transform(
        original, boundaries=(0,4,8))
    assert len(result.decisions) == 4
    assert result.timing.exercise_phrase.notes[1].start == expected
    assert result.timing.exercise_phrase.notes[1].end == 2
    assert [e.source_index for e in result.timing.events] == list(range(8))
    assert [e.source_start for e in result.timing.events] == list(range(8))
    assert tuple(n.source_id for n in result.timing.exercise_phrase.notes) == (
        tuple(n.source_id for n in original.notes))


def test_dotted_rhythm_keeps_polyphonic_voices_independent():
    source = sample()
    left = (
        Note(0,1,48,1,0,"left","l0","v2"),
        Note(1,2,50,1,0,"left","l1","v2"),
    )
    phrase = replace(source.phrase, notes=source.notes+left)
    variant = ExerciseVariant("original", phrase, tuple(range(10)))
    result = ResearchPolyphonicDottedRhythm().transform(
        variant, boundaries=(0,4,8))
    assert len(result.decisions) == 5
    assert result.timing.exercise_phrase.notes[9].start == pytest.approx(1.5)


def test_dotted_rhythm_respects_source_authored_beaming():
    fixture = Path(__file__).parent / "fixtures/connector_pixels/beam16/score.musicxml"
    piece = load_musicxml(fixture, bpm=80)
    phrase = piece.phrases[0]
    variant = ExerciseVariant("original", phrase, tuple(range(len(phrase.notes))))
    result = ResearchPolyphonicDottedRhythm().transform(
        variant, boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    from piano_teacher.notation.rhythm_safety import beamed_source_ids
    protected = beamed_source_ids(piece.source_musicxml)
    assert protected
    for event, note in zip(result.timing.events, variant.notes):
        if note.source_id in protected:
            assert event.exercise_start == pytest.approx(note.start - phrase.start)
            assert event.exercise_end == pytest.approx(note.end - phrase.start)


def test_source_rests_block_dotted_pair_but_other_voice_is_unchanged():
    # First two adjacent quarter notes; a written rest overlaps the
    # candidate in the *same* source voice.
    xml = """<score-partwise><part id="P"><measure number="1">
        <note><pitch><step>C</step><octave>4</octave></pitch>
          <duration>1</duration><voice>1</voice></note>
        <note><pitch><step>E</step><octave>4</octave></pitch>
          <duration>1</duration><voice>1</voice></note>
        <backup><duration>2</duration></backup>
        <note><rest/><duration>1</duration><voice>1</voice></note>
        </measure></part></score-partwise>"""
    notes = (Note(0,1,60,0,0,"right","xml-p0-m0-e0","xml-p0-s1-v1"),
             Note(1,2,64,0,0,"right","xml-p0-m0-e1","xml-p0-s1-v1"))
    variant = ExerciseVariant("original",Phrase(1,1,1,0,4,notes),(0,1))
    result = ResearchPolyphonicDottedRhythm().transform(
        variant, boundaries=(0,4),source_musicxml=xml)
    assert not result.decisions
    assert result.timing.exercise_phrase.notes == variant.notes
