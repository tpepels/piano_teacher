"""Reference-guided Coda four-family checks from author backend.

Known differences from original code are explicitly guarded (never
silent source deletion or off-grid rounding); production stays unchanged.
"""
from pathlib import Path

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Note,Phrase
from piano_teacher.research.coda_reference_exercises import (
    original_coda_levels,CodaReferenceSlowdown,CodaReferenceDotted,
    CodaReferenceChordification)

SRC=Path(__file__).parent/"fixtures/research/coda_four_families.musicxml"


def _fixture():
    piece=load_musicxml(SRC,bpm=80)
    phrase=Phrase(1,1,2,0,8,piece.notes)
    return piece,ExerciseVariant("original",phrase,tuple(range(len(piece.notes))))


def test_part_splitting_is_hands_and_voices_not_measures():
    piece,variant=_fixture()
    levels=original_coda_levels(
        variant,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    assert [s.level for s in levels]==[
        "score","part","voice","part","voice"]
    assert len(levels[0].variant.notes)==16
    assert [len(s.variant.notes) for s in levels[1:]]==[8,8,8,8]
    assert {s.hand for s in levels[2::2]}=={"left","right"}
    assert all(s.variant.phrase.first_bar==1 and
               s.variant.phrase.last_bar==2 for s in levels)
    assert all(set(s.variant.source_indices).issubset(set(variant.source_indices))
               for s in levels)


def test_source_slowdown_expands_written_note_timing_not_tempo_map():
    _,variant=_fixture()
    for factor in (2,4):
        result=CodaReferenceSlowdown(factor).transform(variant)
        assert result.timing.duration_beats==8*factor
        assert len(result.timing.events)==16
        for note,event in zip(variant.notes,result.timing.events):
            assert event.exercise_start==pytest.approx(note.start*factor)
            assert event.exercise_end==pytest.approx(note.end*factor)
            assert event.source_start==note.start
        assert tuple(n.source_id for n in result.timing.exercise_phrase.notes)==tuple(
            n.source_id for n in variant.notes)
    with pytest.raises(ValueError,match="factors 2 and 4"):
        CodaReferenceSlowdown(3).transform(variant)


@pytest.mark.parametrize("long_first,first,second",[
    (True,1.5,.5),(False,.5,1.5)])
def test_full_two_hand_dotted_runs_preserve_every_attack(long_first,first,second):
    piece,variant=_fixture()
    result=CodaReferenceDotted(long_first).transform(
        variant,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml)
    assert len(result.groups)==8
    assert len(result.changed_sources)==16
    for note,event in zip(variant.notes,result.timing.events):
        # Each measure is four quarter notes, per independent source voice.
        local=int(note.start)%2
        if local==0:
            assert event.exercise_end-event.exercise_start==pytest.approx(first)
        else:
            assert event.exercise_end-event.exercise_start==pytest.approx(second)
    assert result.timing.duration_beats==8


def test_chord_groups_are_two_note_block_chords_with_original_source_mapping():
    piece,variant=_fixture()
    result=CodaReferenceChordification(8).transform(
        variant,boundaries=piece.bar_boundaries,quantization=4,
        source_musicxml=piece.source_musicxml)
    assert len(result.groups)==8
    assert len(result.changed_sources)==16
    for a,b in result.groups:
        positions={note.source_id:(note.start,note.end) for note in variant.notes}
        assert abs(positions[a][0]-positions[b][0])==1
    assert all(event.exercise_start in (0,2,4,6)
               for event in result.timing.events)
    assert all(event.exercise_end-event.exercise_start==2
               for event in result.timing.events)


def test_bad_chord_width_or_extra_wide_span_does_not_rewrite_sources():
    notes=(Note(0,1,48,0,0,"right","a","v"),
           Note(1,2,70,0,0,"right","b","v"))
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,notes),(0,1))
    with pytest.raises(ValueError,match="positive"):
        CodaReferenceChordification(0).transform(
            variant,boundaries=(0,4),quantization=4)
    result=CodaReferenceChordification(8).transform(
        variant,boundaries=(0,4),quantization=4)
    assert result.groups==()
    assert result.timing.exercise_phrase.notes==variant.notes


def test_reference_notation_id_owns_unchanged_original_mastery():
    piece,variant=_fixture()
    algorithms=[
        CodaReferenceSlowdown(2).transform(variant),
        CodaReferenceDotted(True).transform(
            variant,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml),
        CodaReferenceChordification(8).transform(
            variant,boundaries=piece.bar_boundaries,quantization=4,
            source_musicxml=piece.source_musicxml)]
    source=tuple(n.source_id for n in variant.notes)
    for result in algorithms:
        assert tuple(n.source_id for n in result.timing.exercise_phrase.notes)==source
        assert result.timing.original==variant
        assert tuple(e.source_index for e in result.timing.events)==variant.source_indices
    assert variant.notes==algorithms[0].timing.original.notes


def test_reference_chordification_keeps_silent_tail_after_equal_note_run():
    # Author Coda groups the two .5-beat notes into a 1-beat chord and
    # leaves beat [1,2) silent. A padded equal-duration range must not
    # be dropped because the NEXT duration is at beat 2.
    notes=(
        Note(0,.5,60,0,0,"right","a","v"),
        Note(.5,1,62,0,0,"right","b","v"),
        Note(2,3,64,0,0,"right","c","v"),
        Note(3,4,65,0,0,"right","d","v"))
    v=ExerciseVariant("original",Phrase(1,1,1,0,4,notes),(0,1,2,3))
    result=CodaReferenceChordification(16).transform(
        v,boundaries=(0,4),quantization=8)
    assert result.groups==(("a","b"),("c","d"))
    assert [(e.exercise_start,e.exercise_end)
            for e in result.timing.events]==[
        (0,1),(0,1),(2,4),(2,4)]
    assert result.changed_sources==("a","b","c","d")
    assert result.timing.duration_beats==4
    assert result.timing.original.notes==notes


@pytest.mark.parametrize("long_first,last_duration",[(True,1.5),(False,.5)])
def test_reference_dotted_odd_tail_matches_author_when_note_is_safe(
        long_first,last_duration):
    notes=tuple(Note(float(i),float(i+1),60+i,0,0,"right",
                     f"odd-{i}","v") for i in range(3))
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,notes),(0,1,2))
    result=CodaReferenceDotted(long_first).transform(
        variant,boundaries=(0,4),quantization=4)
    assert len(result.changed_sources)==3
    assert result.groups[-1]==("odd-2",)
    events=result.timing.events
    assert events[-1].exercise_start==2
    assert events[-1].exercise_end-events[-1].exercise_start==pytest.approx(last_duration)
    assert result.timing.duration_beats==4
    assert result.timing.original.notes==notes


def test_reference_dotted_cannot_extend_odd_tail_past_original_measure():
    notes=tuple(Note(float(i),float(i+1),60+i,0,0,"right",
                     f"end-{i}","v") for i in (1,2,3))
    variant=ExerciseVariant("original",Phrase(1,1,1,0,4,notes),(0,1,2))
    result=CodaReferenceDotted(True).transform(
        variant,boundaries=(0,4),quantization=4)
    assert result.timing.events[-1].exercise_start==3
    assert result.timing.events[-1].exercise_end==4
    assert "end-3" not in result.changed_sources
    assert all(e.exercise_end<=4 for e in result.timing.events)
