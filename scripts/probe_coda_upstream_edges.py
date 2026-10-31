"""Bounded original-Coda differential on source rhythm edge cases.

The actual author's ExerciseLine and MusicMatrixRepresentation run unchanged
from a pinned checkout. This writes one report with exact outcomes including
mismatches, rejected inputs and original exceptions. Only a declared 'parity'
case is gated; exploratory counterexamples can never receive a pass label.
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_reference_matrix import (
    reference_quantization, score_voice_matrices,
)
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceSlowdown, CodaReferenceDotted, CodaReferenceChordification,
)

# All fixtures are exactly one 4/4 measure, in quarter-note coordinates.
# Pitch groups at an onset have equal durations unless designated otherwise.
CASES=(
    ("even-mixed", "parity", (
        (0,.5,(60,)),(.5,.5,(62,)),(1,.5,(64,)),(1.5,.5,(65,)),
        (2,1,(67,)),(3,1,(69,)))),
    ("odd-equal-run", "diagnostic", (
        (0,1,(60,)),(1,1,(62,)),(2,1,(64,)))),
    ("block-chords", "parity", (
        (0,1,(60,64)),(1,1,(62,65)),(2,1,(64,67)),(3,1,(65,69)))),
    ("mixed-with-gap", "parity", (
        (0,.5,(60,)),(.5,.5,(62,)),(2,1,(64,)),(3,1,(65,)))),
)


def _events(part):
    from music21 import chord
    result=[]
    for n in part.recurse().notes:
        pitches=n.pitches if isinstance(n,chord.Chord) else (n.pitch,)
        for p in pitches:
            result.append((
                round(float(n.getOffsetInHierarchy(part)),6),
                int(p.midi),round(float(n.quarterLength),6)))
    return sorted(result)


def _ours(plan):
    return sorted((
        round(float(e.exercise_start),6),n.pitch,
        round(float(e.exercise_end-e.exercise_start),6))
        for e,n in zip(plan.events,plan.original.notes))


def _build(case, music21):
    from music21 import stream,note,chord,key,meter
    measure=stream.Measure(number=1)
    measure.insert(0,key.KeySignature(0))
    measure.insert(0,meter.TimeSignature("4/4"))
    notes=[]
    i=0
    for start,duration,pitches in case:
        entry=(chord.Chord(pitches) if len(pitches)>1 else note.Note(pitches[0]))
        entry.quarterLength=duration
        measure.insert(start,entry)
        for pitch in pitches:
            notes.append(Note(start,start+duration,pitch,0,0,
                              "right",f"case-note-{i}","source-voice-1"))
            i+=1
    part=stream.Part()
    part.append(measure)
    phrase=Phrase(1,1,1,0,4,tuple(notes))
    variant=ExerciseVariant("original",phrase,tuple(range(len(notes))))
    return part,variant


def compare(upstream):
    database=types.ModuleType("services.database")
    database.MongoDatabase=type("UnusedMongo",(),{"__init__":lambda self:None})
    sys.modules["services.database"]=database
    sys.path.insert(0,str(upstream))
    from music21 import key,meter
    from music.exercise import ExerciseLine,MusicMatrixRepresentation

    rows=[]
    for name,policy,notes in CASES:
        part,variant=_build(notes,None)
        shortest=min(duration for _,duration,_ in notes)
        q=reference_quantization(shortest,4)
        line=ExerciseLine.__new__(ExerciseLine)
        line.original_stream=part
        line.key_signature=key.KeySignature(0)
        line.time_signature=meter.TimeSignature("4/4")
        line.quantization=q
        row={"case":name,"policy":policy,"quantization":q,
             "source_notes":len(variant.notes),"matrix":{},"algorithms":{}}
        try:
            roll,onsets,durations=line._create_matrices()
            line.music_matrix_representation=MusicMatrixRepresentation(
                line.key_signature,line.time_signature,q,roll,onsets,durations)
            (ours,)=score_voice_matrices(
                MatrixScore.from_phrase(variant.phrase,boundaries=(0,4)),
                quantization=q)
            for label,a,b in (
                ("piano_roll",roll,ours.piano_roll),
                ("onset_map",onsets,ours.onset_map),
                ("durations_matrix",durations,ours.durations_matrix)):
                row["matrix"][label]={
                    "match":bool(np.array_equal(a,b)),
                    "reference_shape":list(a.shape),
                    "ours_shape":list(b.shape)}
            operations=(
                ("slow-x2",lambda:line.generate_slowed_down_exercise(2),
                 lambda:CodaReferenceSlowdown(2).transform(variant).timing),
                ("slow-x4",lambda:line.generate_slowed_down_exercise(4),
                 lambda:CodaReferenceSlowdown(4).transform(variant).timing),
                ("dotted-3:1",lambda:line.generate_dotted_exercise([1.5,.5]),
                 lambda:CodaReferenceDotted(True).transform(
                     variant,boundaries=(0,4),quantization=q).timing),
                ("dotted-1:3",lambda:line.generate_dotted_exercise([.5,1.5]),
                 lambda:CodaReferenceDotted(False).transform(
                     variant,boundaries=(0,4),quantization=q).timing),
                ("chord-2-beat",lambda:line.generate_chordify_exercise(2*q),
                 lambda:CodaReferenceChordification(2*q).transform(
                     variant,boundaries=(0,4),quantization=q).timing),
            )
            for label,ref_fn,ours_fn in operations:
                try:
                    ref=ref_fn()
                    target=ours_fn()
                    if ref is None:
                        row["algorithms"][label]={"status":"upstream-none"}
                        continue
                    observed=_events(ref)
                    expected=_ours(target)
                    row["algorithms"][label]={
                        "status":"match" if observed==expected else "mismatch",
                        "author":observed if observed!=expected else None,
                        "ours":expected if observed!=expected else None}
                except Exception as e:
                    row["algorithms"][label]={
                        "status":"upstream-or-adapter-exception",
                        "exception":type(e).__name__,"detail":str(e)[:500]}
        except Exception as e:
            row["matrix_error"]={"type":type(e).__name__,"detail":str(e)}
        mismatches=[label for label,result in row["matrix"].items()
                    if not result["match"]]
        mismatches.extend(label for label,result in row["algorithms"].items()
                          if result["status"]!="match")
        if "matrix_error" in row:
            mismatches.append("matrix-error")
        row["mismatches"]=mismatches
        row["verified_parity"]=not mismatches and policy=="parity"
        rows.append(row)
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    if not (args.upstream/"music/exercise.py").is_file():
        raise ValueError("Missing original backend checkout")
    rows=compare(args.upstream)
    report={"reference_revision":"a4eb85dfc2bd418818ca9ff775c0a11ccccb3530",
            "status":"exploratory-with-declared-parity-gates",
            "parity_cases":sum(r["policy"]=="parity" for r in rows),
            "verified_parity_cases":sum(r["verified_parity"] for r in rows),
            "nonparity_cases":sum(r["policy"]!="parity" for r in rows),
            "rows":rows}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},sort_keys=True))
    for r in rows:
        print(r["case"],r["policy"],r["mismatches"])
    if report["verified_parity_cases"] != report["parity_cases"]:
        raise AssertionError("Declared source parity case diverged from author")


if __name__=="__main__":
    main()
