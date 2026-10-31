"""Small executable comparison with Annie Tang's pinned, unmodified backend.

Source checkout is supplied by the separate explicit GitHub Action. The
repository does not vendor upstream copyrighted code. Stub only the unused
MongoDB service imported at module initialization; original music21/Matrices
and all transformation methods execute unchanged.
"""
import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_reference_matrix import score_voice_matrices
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceSlowdown, CodaReferenceDotted, CodaReferenceChordification,
)

FIXTURE=Path(__file__).resolve().parents[1]/"tests/fixtures/research/coda_four_families.musicxml"
REFERENCE_SHA="a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"


def _notation_events(part):
    from music21 import chord
    values=[]
    for note in part.recurse().notes:
        pitches=note.pitches if isinstance(note,chord.Chord) else (note.pitch,)
        for p in pitches:
            values.append((round(float(note.getOffsetInHierarchy(part)),6),
                           int(p.midi),round(float(note.quarterLength),6)))
    return sorted(values)


def _plan_events(plan,indices):
    return sorted((round(plan.events[i].exercise_start,6),
                   plan.original.notes[i].pitch,
                   round(plan.events[i].exercise_end-plan.events[i].exercise_start,6))
                  for i in indices)


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--upstream",type=Path,required=True)
    cli.add_argument("--report",type=Path,required=True)
    opts=cli.parse_args()
    ref=opts.upstream.resolve()
    if not (ref/"music/exercise.py").is_file():
        raise ValueError("Pinned upstream source not found")
    module=types.ModuleType("services.database")
    module.MongoDatabase=type("NoDatabase",(),{"__init__":lambda self:None})
    sys.modules["services.database"]=module
    sys.path.insert(0,str(ref))
    from music21 import converter,key,meter
    from music.exercise import ExerciseLine,MusicMatrixRepresentation

    piece=load_musicxml(FIXTURE,bpm=80)
    variant=ExerciseVariant("original",Phrase(1,1,2,0,8,piece.notes),
                            tuple(range(len(piece.notes))))
    score=MatrixScore.from_phrase(
        variant.phrase,boundaries=piece.bar_boundaries,
        source_musicxml=piece.source_musicxml)
    matrices=score_voice_matrices(score,quantization=4)
    original=converter.parse(str(FIXTURE))
    output=[]
    for pi,part in enumerate(original.parts):
        hand=("right","left")[pi]
        for line_stream in part.voicesToParts().parts:
            if not tuple(line_stream.recurse().notes):
                continue
            line=ExerciseLine.__new__(ExerciseLine)
            line.original_stream=line_stream
            line.quantization=4
            line.time_signature=meter.TimeSignature("4/4")
            line.key_signature=key.KeySignature(0)
            roll,onsets,durations=line._create_matrices()
            line.music_matrix_representation=MusicMatrixRepresentation(
                line.key_signature,line.time_signature,4,roll,onsets,durations)
            match=next(m for m in matrices if m.hand==hand)
            for name,actual,expected in (
                ("piano_roll",roll,match.piano_roll),
                ("onset_map",onsets,match.onset_map),
                ("durations_matrix",durations,match.durations_matrix)):
                if not np.array_equal(actual,expected):
                    raise AssertionError(
                        f"{hand} upstream {name} differs: {actual.shape} vs {expected.shape}")
            owner_indices={i for _,_,i,_ in match.owners}
            plans=(
                ("slow-x2",line.generate_slowed_down_exercise(2),
                 CodaReferenceSlowdown(2).transform(variant).timing),
                ("slow-x4",line.generate_slowed_down_exercise(4),
                 CodaReferenceSlowdown(4).transform(variant).timing),
                ("dotted-3-to-1",line.generate_dotted_exercise([1.5,.5]),
                 CodaReferenceDotted(True).transform(
                     variant,boundaries=piece.bar_boundaries,quantization=4,
                     source_musicxml=piece.source_musicxml).timing),
                ("dotted-1-to-3",line.generate_dotted_exercise([.5,1.5]),
                 CodaReferenceDotted(False).transform(
                     variant,boundaries=piece.bar_boundaries,quantization=4,
                     source_musicxml=piece.source_musicxml).timing),
                ("chord-level-8",line.generate_chordify_exercise(8),
                 CodaReferenceChordification(8).transform(
                     variant,boundaries=piece.bar_boundaries,quantization=4,
                     source_musicxml=piece.source_musicxml).timing),
            )
            compared=[]
            for name,reference,ours in plans:
                if reference is None:
                    raise AssertionError(f"Upstream emitted no {name} for {hand}")
                actual=_notation_events(reference)
                expected=_plan_events(ours,owner_indices)
                if actual!=expected:
                    raise AssertionError(f"{hand} {name} differs: reference={actual}; ours={expected}")
                compared.append(name)
            output.append({"hand":hand,"pitch_rows":roll.shape[0],
                           "ticks":roll.shape[1],"matched":compared})
    if len(output)!=2:
        raise AssertionError("Unexpected source voice count: "+str(len(output)))
    report={"upstream_revision":REFERENCE_SHA,
            "reference_comparisons":10,
            "piano_voices":len(output),
            "exact_match":True,"rows":output}
    opts.report.parent.mkdir(parents=True,exist_ok=True)
    opts.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
