"""Bounded 48-bar MIDI corpus and explicit repeated-note overlap constraints.

These are generated *SMF inputs*, not reconstructed MusicXML scores.
Long score and selected later passage use exactly the imported attacks;
unrepresentable repeated overlapping notes fail clearly.
"""
from pathlib import Path

import mido
import pytest

from piano_teacher.music import load_midi
from piano_teacher.practice import PlayedNote
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_midi_passage import (
    project_midi_passage, select_midi_passage,
)
from piano_teacher.research.coda_midi_grid import midi_coda_quantization
from piano_teacher.research.coda_reference_matrix import score_voice_matrices


def _track(events, name):
    track=mido.MidiTrack([mido.MetaMessage("track_name",name=name,time=0)])
    current=0
    for tick,kind,pitch,channel in sorted(
        events,key=lambda x:(x[0],0 if x[1]=="note_off" else 1,x[2])):
        track.append(mido.Message(kind,channel=channel,note=pitch,
            velocity=0 if kind=="note_off" else 88,time=tick-current))
        current=tick
    track.append(mido.MetaMessage("end_of_track",time=0))
    return track


def make_long_midi(path):
    ppq=960
    midi=mido.MidiFile(type=1,ticks_per_beat=ppq)
    right=[]
    left=[]
    for bar in range(48):
        start=bar*4*ppq
        # Every fifth bar has no right hand, but left-hand timing continues.
        if bar%5:
            pitch=60 if bar==17 else (72+bar%6)
            for offset in (0,2*ppq):
                right.extend([(start+offset,"note_on",pitch,0),
                              (start+offset+ppq//2,"note_off",pitch,0)])
        # Both hands may sound exactly the same pitch in different tracks.
        pitch=60 if bar==17 else (45+bar%5)
        left.extend([(start,"note_on",pitch,1),
                     (start+ppq*3,"note_off",pitch,1)])
    midi.tracks.append(_track(right,"Right Hand"))
    midi.tracks.append(_track(left,"Left Hand"))
    midi.save(path)
    return ppq


def test_48_bar_midi_selection_preserves_absolute_attacks_and_long_rests(tmp_path):
    filename=tmp_path/"two-hands-48.mid"
    make_long_midi(filename)
    piece=load_midi(filename,bars_per_phrase=2)
    assert len(piece.bar_boundaries)==49
    assert piece.notes and piece.source_format=="midi"
    assert piece.midi_ticks_per_beat==960
    assert {n.hand for n in piece.notes}=={"left","right"}
    assert any(n.pitch==60 and n.hand=="left" for n in piece.notes)
    assert any(n.pitch==60 and n.hand=="right" for n in piece.notes)
    passage=select_midi_passage(piece,17,24)
    assert passage.source_start==64
    assert passage.source_end==96
    assert passage.piece.bar_boundaries[0]==0
    assert len(passage.piece.bar_boundaries)==9
    assert {n.source_id for n in passage.piece.notes}==passage.original_source_ids
    q=midi_coda_quantization(passage.piece,passage.variant.phrase,compact=True)
    assert 0<q<=960
    matrix=MatrixScore.from_phrase(passage.variant.phrase,
                                  boundaries=passage.piece.bar_boundaries)
    matrices=score_voice_matrices(matrix,quantization=q)
    assert sum(len(m.owners) for m in matrices)==len(passage.variant.notes)
    originals=passage.original_coordinates()
    assert all(a>=64 and b<=96 for a,b in originals.values())
    assert all(a-64==pytest.approx(n.start,abs=1e-7)
               for n in passage.variant.notes
               for a,b in [originals[n.source_id]])
    assert len(piece.notes)>len(passage.variant.notes)
    assert piece.bar_boundaries[-1]==192


def test_long_midi_later_passage_slowdown_uses_one_grading_clock(tmp_path):
    filename=tmp_path/"two-hands-48.mid"
    make_long_midi(filename)
    piece=load_midi(filename)
    passage,stage=project_midi_passage(piece,17,24,
        family="tempo-shaping",slowdown_factor=2)
    assert stage.original_piece is passage.piece
    assert stage.timing.duration_beats==64
    assert stage.tempo_map.duration_beats==64
    assert len(stage.piece.bar_boundaries)==17
    assert stage.variant.phrase.start==0
    assert {n.source_id for n in stage.variant.notes}==passage.original_source_ids
    played=[PlayedNote(n.pitch,stage.tempo_map.seconds_at(n.start),
                       stage.tempo_map.seconds_at(n.end))
            for n in stage.variant.notes]
    assert stage.grade(played).assessment.clean


def test_overlapping_same_pitch_within_one_midi_track_is_explicitly_unsupported(tmp_path):
    mid=mido.MidiFile(type=1,ticks_per_beat=480)
    mid.tracks.append(_track([
        (0,"note_on",60,0),(240,"note_on",60,0),
        (480,"note_off",60,0),(720,"note_off",60,0)],"Right Hand"))
    filename=tmp_path/"overlap.mid"
    mid.save(filename)
    piece=load_midi(filename)
    assert len(piece.notes)==2
    assert any("Ambiguous overlapping MIDI notes" in w for w in piece.import_warnings)
    passage=select_midi_passage(piece,1,1)
    score=MatrixScore.from_phrase(
        passage.variant.phrase,boundaries=passage.piece.bar_boundaries)
    q=midi_coda_quantization(passage.piece,passage.variant.phrase,compact=True)
    with pytest.raises(ValueError,match="overlapping identical pitch"):
        score_voice_matrices(score,quantization=q)
