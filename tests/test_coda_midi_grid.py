"""MIDI-origin, precise grid and provenance; no MusicXML source is needed."""
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from piano_teacher.music import Phrase, load_midi
from piano_teacher.research.coda_midi_grid import midi_coda_quantization

ROOT=Path(__file__).parent/"fixtures/musical_fidelity"


def _phrase(piece):
    return Phrase(1,1,len(piece.bar_boundaries)-1,0,
                  piece.bar_boundaries[-1],piece.notes)


@pytest.mark.parametrize("filename",[
    "midi_four_four.mid",
    "midi_three_four.mid",
    "midi_mixed_meter.mid",
    "midi_triplets.mid",
    "midi_raw_ppq997.mid",
    "midi_sparse_rests.mid",
])
def test_midi_grid_preserves_raw_ppq_and_attack_releases(filename):
    path=ROOT/filename
    piece=load_midi(path)
    assert piece.source_format=="midi"
    assert piece.source_musicxml==""
    assert piece.midi_ticks_per_beat==mido.MidiFile(path).ticks_per_beat
    phrase=_phrase(piece)
    q=midi_coda_quantization(piece,phrase)
    assert q==piece.midi_ticks_per_beat
    for note in phrase.notes:
        assert round(note.start*q)/q==pytest.approx(note.start,abs=1e-9)
        assert round(note.end*q)/q==pytest.approx(note.end,abs=1e-9)


def test_midi_dotted_grid_is_half_tick_exact():
    piece=load_midi(ROOT/"midi_four_four.mid")
    q=midi_coda_quantization(piece,_phrase(piece),dotted=True)
    assert q==2*piece.midi_ticks_per_beat


def test_unknown_or_fake_provenance_fails():
    piece=load_midi(ROOT/"midi_four_four.mid")
    for fake in (
        replace(piece,source_format=""),
        replace(piece,midi_ticks_per_beat=0),
        replace(piece,source_musicxml="<source/>"),
    ):
        with pytest.raises(ValueError,match="genuine MIDI"):
            midi_coda_quantization(fake,_phrase(fake))


def test_bounded_grid_rejects_capacity_not_rounded():
    piece=load_midi(ROOT/"midi_raw_ppq997.mid")
    with pytest.raises(ValueError,match="matrix capacity"):
        midi_coda_quantization(piece,_phrase(piece),max_cells=128)


def test_rejects_duration_with_unbacked_midi_tick():
    piece=load_midi(ROOT/"midi_four_four.mid")
    notes=list(piece.notes)
    notes[0]=replace(notes[0],end=notes[0].end+.01)
    phrase=replace(_phrase(piece),notes=tuple(notes))
    with pytest.raises(ValueError,match="original PPQ"):
        midi_coda_quantization(piece,phrase)


def test_compact_grid_preserves_source_ticks_without_large_ppq_matrix():
    from piano_teacher.research.coda_reference_matrix import score_voice_matrices
    from piano_teacher.research.coda_matrix import MatrixScore
    piece=load_midi(ROOT/"midi_four_four.mid")
    phrase=_phrase(piece)
    raw=midi_coda_quantization(piece,phrase)
    compact=midi_coda_quantization(piece,phrase,compact=True)
    assert compact<raw
    assert compact>=1
    assert midi_coda_quantization(piece,phrase,compact=True,dotted=True)==compact*2
    score=MatrixScore.from_phrase(phrase,boundaries=piece.bar_boundaries)
    matrices=score_voice_matrices(score,quantization=compact)
    assert sum(len(m.owners) for m in matrices)==len(piece.notes)


def test_compact_grid_preserves_unusual_ppq_when_required():
    piece=load_midi(ROOT/"midi_raw_ppq997.mid")
    phrase=_phrase(piece)
    grid=midi_coda_quantization(piece,phrase,compact=True)
    assert piece.midi_ticks_per_beat % grid == 0
    for note in piece.notes:
        assert note.start*grid==pytest.approx(round(note.start*grid),abs=1e-7)
        assert note.end*grid==pytest.approx(round(note.end*grid),abs=1e-7)
