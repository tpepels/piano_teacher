"""Export a real later-measure MIDI-Coda score model for Godot smoke tests.

This is a Python->Godot semantic boundary probe. It does not pretend
to launch the full app or to exercise physical MIDI hardware.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.music import load_midi
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.research.coda_midi_passage import project_midi_passage


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--cache",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    source=root/"tests/fixtures/musical_fidelity/midi_three_four.mid"
    piece=load_midi(source)
    chosen,stage=project_midi_passage(piece,2,2,
        family="tempo-shaping",slowdown_factor=2,revision=73)
    model=ScoreArtifacts(PreprocessingCache(args.cache)).source_model(
        stage.selection)
    required=sorted(chosen.original_source_ids)
    assert sorted(n["id"] for n in model["notes"])==required
    assert model["duration_beats"]==stage.tempo_map.duration_beats
    result={
        "schema":"coda-midi-godot-semantics-v1",
        "score_model":model,
        "source_first_bar":chosen.first_bar,
        "source_start_beat":chosen.source_start,
        "source_end_beat":chosen.source_end,
        "source_ids":required,
        "exercise_bpm":stage.tempo_map.bpm_at(0),
        "source_format":piece.source_format,
        "source_ppq":piece.midi_ticks_per_beat,
        "original_coordinates":chosen.original_coordinates(),
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True)+"\n")
    print(json.dumps({"source_first_bar":chosen.first_bar,
                      "score_notes":len(required),
                      "exercise_beats":model["duration_beats"],
                      "source_format":piece.source_format},sort_keys=True))


if __name__=="__main__":
    main()
