"""Pinned Coda MMR shape and source-identity tests from thesis §2.2.

Reference code: annieetang/coda_backend (music/matrix.py, music/exercise.py)
at a4eb85dfc2bd418818ca9ff775c0a11ccccb3530.
"""
import numpy as np
import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note,Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_reference_matrix import (
    reference_quantization,score_voice_matrices,CodaVoiceMatrix)


def test_reference_quantization_matches_author_formula():
    assert reference_quantization(.25,4)==16
    assert reference_quantization(.5,3)==6
    assert reference_quantization(1,4)==4
    assert reference_quantization(2,4)==4


def test_three_reference_matrices_preserve_two_independent_piano_voices():
    notes=(Note(0,1,60,0,0,"right","n0","r"),
           Note(1,2,62,0,0,"right","n1","r"),
           Note(2,3,64,0,0,"right","n2","r"),
           Note(3,4,65,0,0,"right","n3","r"),
           Note(0,2,48,1,0,"left","n4","l"),
           Note(2,4,50,1,0,"left","n5","l"))
    phrase=Phrase(1,1,1,0,4,notes)
    score=MatrixScore.from_phrase(phrase,boundaries=(0,4))
    right,left=score_voice_matrices(score,quantization=4)
    assert right.piano_roll.shape==(128,16)
    assert right.onset_map.shape==(128,16)
    assert right.durations_matrix.shape==(128,16)
    assert right.onset_map[60,0]==1
    assert right.durations_matrix[60,0]==4
    assert right.piano_roll[60,:4].tolist()==[1]*4
    assert right.piano_roll[60,4]==0
    assert right.onset_map[62,4]==1
    assert right.equal_duration_ranges()==((0,16,4),)
    assert left.equal_duration_ranges()==((0,16,2),)
    assert left.onset_map[48,0]==1
    assert left.onset_map[50,8]==1
    assert sum(int(np.count_nonzero(a.onset_map))
               for a in (right,left))==len(notes)
    assert {id for matrix in (right,left) for *_,id in matrix.owners}=={
        n.source_id for n in notes}


def test_simultaneous_block_chord_has_one_onset_per_pitch():
    notes=(Note(0,1,60,0,0,"right","c","r"),
           Note(0,1,64,0,0,"right","e","r"),
           Note(1,2,67,0,0,"right","g","r"))
    score=MatrixScore.from_phrase(Phrase(1,1,1,0,4,notes),boundaries=(0,4))
    (m,)=score_voice_matrices(score,quantization=4)
    assert m.flatten()[0]==(4,0,0,0,4,0,0,0)
    assert m.flatten()[1][0]==(60,64)
    assert m.equal_duration_ranges()==((0,8,2),)


def test_unrepresentable_source_rhythm_refuses_approximate_timing():
    note=Note(.1,.6,60,0,0,"right","x","v")
    score=MatrixScore.from_phrase(Phrase(1,1,1,0,4,(note,)),boundaries=(0,4))
    with pytest.raises(ValueError,match="exactly representable"):
        score_voice_matrices(score,quantization=4)


def test_overlapping_same_pitch_voice_is_not_silently_overwritten():
    notes=(Note(0,2,60,0,0,"right","a","v"),
           Note(1,3,60,0,0,"right","b","v"))
    score=MatrixScore.from_phrase(Phrase(1,1,1,0,4,notes),boundaries=(0,4))
    with pytest.raises(ValueError,match="overlapping identical pitch"):
        score_voice_matrices(score,quantization=4)


def test_unequal_simultaneous_voice_durations_fail_before_flattening():
    notes=(Note(0,1,60,0,0,"right","c","r"),
           Note(0,2,64,0,0,"right","e","r"))
    score=MatrixScore.from_phrase(Phrase(1,1,1,0,4,notes),boundaries=(0,4))
    (m,)=score_voice_matrices(score,quantization=4)
    with pytest.raises(ValueError,match="unequal simultaneous durations"):
        m.flatten()
