"""Selecting a non-first source bar preserves source attacks and context."""
from dataclasses import replace
from pathlib import Path

import pytest

from piano_teacher.music import load_midi, Piece, Note, Phrase
from piano_teacher.research.coda_midi_passage import (
    select_midi_passage,project_midi_passage,
)
from piano_teacher.practice import PlayedNote

ROOT=Path(__file__).parent/"fixtures/musical_fidelity"


def test_later_midi_passage_has_local_clock_and_absolute_source_provenance():
    piece=load_midi(ROOT/"midi_three_four.mid")
    chosen=select_midi_passage(piece,2,2)
    assert chosen.first_bar==2 and chosen.last_bar==2
    assert chosen.source_start==3
    assert chosen.piece.bar_boundaries==(0,3)
    assert chosen.piece.time_signatures[0]==(0,3,4)
    assert chosen.source_piece is piece
    assert chosen.variant.source_indices==chosen.source_indices
    assert chosen.original_coordinates()=={
        piece.notes[i].source_id:(piece.notes[i].start,piece.notes[i].end)
        for i in chosen.source_indices}
    assert chosen.piece.notes[0].start==0
    assert chosen.piece.notes[0].source_id==piece.notes[chosen.source_indices[0]].source_id
    assert piece.notes[chosen.source_indices[0]].start==3


@pytest.mark.parametrize(("family","options"),[
    ("tempo-shaping",{"slowdown_factor":2}),
    ("dotted-rhythms",{}),
    ("chordification",{"chord_beats":2}),
])
def test_later_bar_projects_same_note_ids_to_grading(family,options):
    piece=load_midi(ROOT/"midi_three_four.mid")
    chosen,stage=project_midi_passage(piece,2,2,family=family,**options)
    assert stage.original_piece is chosen.piece
    assert stage.original_piece.source_musicxml==""
    assert len(stage.variant.notes)==len(chosen.variant.notes)
    assert {n.source_id for n in stage.variant.notes}==chosen.original_source_ids
    assert stage.original_piece is not piece
    played=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                       stage.tempo_map.seconds_at(n.end))
            for n in stage.variant.notes]
    assert stage.grade(played).assessment.clean


def test_source_boundary_crossing_is_rejected_not_clipped():
    piece=load_midi(ROOT/"midi_three_four.mid")
    crossing=replace(piece.notes[0],end=3.5)
    altered=replace(piece,notes=(crossing,)+piece.notes[1:])
    with pytest.raises(ValueError,match="begins during"):
        select_midi_passage(altered,2,2)
    with pytest.raises(ValueError,match="ends during"):
        select_midi_passage(altered,1,1)


def test_invalid_and_empty_selection_fail_closed():
    piece=load_midi(ROOT/"midi_three_four.mid")
    for a,b in ((0,1),(3,3),(2,1),(1,9)):
        with pytest.raises(ValueError):
            select_midi_passage(piece,a,b)
    with pytest.raises(ValueError,match="genuine"):
        select_midi_passage(replace(piece,source_format=""),1,1)
