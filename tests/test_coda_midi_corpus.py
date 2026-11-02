"""All supported MIDI fixtures have lossless Coda input matrices.

This is independent of authored MusicXML and the original Coda backend.
Source attack/release timing is kept at raw SMF PPQ precision. Failure must
report the exact MIDI file rather than silently skipping it.
"""
from pathlib import Path
import json

import pytest

from piano_teacher.music import Phrase, load_midi
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_midi_grid import midi_coda_quantization
from piano_teacher.research.coda_reference_matrix import score_voice_matrices

ROOT=Path(__file__).parent/"fixtures/musical_fidelity"
MANIFEST=json.loads((ROOT/"manifest.json").read_text())
SUPPORTED=tuple(
    sorted(item["file"] for item in MANIFEST["supported"]
           if item["file"].lower().endswith((".mid",".midi"))))


def test_independent_corpus_has_sixteen_real_smf_files():
    assert len(SUPPORTED)==16
    assert len(set(SUPPORTED))==16
    assert all((ROOT/name).is_file() for name in SUPPORTED)


@pytest.mark.parametrize("filename",SUPPORTED)
def test_imported_midi_attacks_and_source_voice_matrices_remain_exact(filename):
    piece=load_midi(ROOT/filename)
    assert piece.source_format=="midi"
    assert piece.source_musicxml==""
    assert piece.midi_ticks_per_beat>0
    assert piece.bar_boundaries[0]==0
    assert len({n.source_id for n in piece.notes})==len(piece.notes)
    phrase=Phrase(1,1,len(piece.bar_boundaries)-1,0,
                  piece.bar_boundaries[-1],piece.notes)
    q=midi_coda_quantization(piece,phrase)
    score=MatrixScore.from_phrase(
        phrase,boundaries=piece.bar_boundaries,source_musicxml="")
    score.verify_lossless()
    matrices=score_voice_matrices(score,quantization=q)
    assert len(matrices)>0
    assert sum(len(matrix.owners) for matrix in matrices)==len(piece.notes)
    assert {sid for matrix in matrices for _,_,_,sid in matrix.owners}=={
        n.source_id for n in piece.notes}
    by_id={n.source_id:n for n in piece.notes}
    for matrix in matrices:
        for pitch,tick,index,sid in matrix.owners:
            source=by_id[sid]
            assert source.pitch==pitch
            assert tick/q==pytest.approx(source.start,abs=1e-8)
            duration=int(matrix.durations_matrix[pitch,tick])
            assert (tick+duration)/q==pytest.approx(source.end,abs=1e-8)
