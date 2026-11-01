"""Wider, diagnostic-only original Coda exercise differential.

Exercises ALL chordification levels automatically chosen by the original
backend, not one hand-picked chord width. Also samples both dotted patterns
and slowdown x2/x4 on additional authored MusicXML; author errors, unsupported
matrix inputs and adapter safeguards remain visible, never counted as parity.

Original author sources are obtained by a separately bounded GitHub Action.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import types

import numpy as np

from piano_teacher.exercise_contracts import OriginalTiming
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.research.coda_auto_chord_levels import original_chord_levels
from piano_teacher.research.coda_differential import (
    written_from_musicxml, sounding_from_written, sounding_from_plan,
)
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceSlowdown, CodaReferenceDotted, CodaReferenceChordification,
)
from piano_teacher.research.coda_reference_matrix import score_voice_matrices
from scripts.probe_coda_upstream_scores import _native_written

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SHA = "a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"

# Existing checked-in independent MusicXML sources: chords, two-staff
# polyphony, quintuplets, rests, meter changes, sixteenths, and 5:4/7:4.
# Two real repertoire excerpts exercise cases beyond synthesized fixtures.
SOURCES = (
    ("chord-ties", "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml", 1, 2),
    ("grandstaff-voices", "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml", 1, 1),
    ("source-quintuplets", "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml", 1, 1),
    ("trailing-rests", "tests/fixtures/musical_fidelity/xml_trailing_rests.musicxml", 1, 2),
    ("source-mixed-meter", "tests/fixtures/musical_fidelity/xml_mixed_meter.musicxml", 1, 2),
    ("source-sixteenth-beams", "tests/fixtures/connector_pixels/beam16/score.musicxml", 1, 1),
    ("source-five-to-four", "tests/fixtures/research/coda_group_5_4.musicxml", 1, 1),
    ("source-seven-to-four", "tests/fixtures/research/coda_group_7_4.musicxml", 1, 1),
    ("autumn-leaves-excerpt", "docs/evidence/native-audit-2026-10-26/autumn-source.musicxml", 37, 38),
    ("danny-boy-excerpt", "tests/fixtures/extra_shard_pixels/danny-stripe.musicxml", 1, 2),
)


def _operation(name, level=None):
    """Return independent original/adapter operations to classify failures."""
    if name in ("slow-x2", "slow-x4"):
        factor=int(name[-1])
        return (
            lambda line: line.generate_slowed_down_exercise(factor),
            lambda variant,piece,boundaries,q:
                CodaReferenceSlowdown(factor).transform(variant).timing,
            factor)
    if name in ("dotted-3-to-1", "dotted-1-to-3"):
        first=name=="dotted-3-to-1"
        return (
            lambda line: line.generate_dotted_exercise(
                [1.5,.5] if first else [.5,1.5]),
            lambda variant,piece,boundaries,q:
                CodaReferenceDotted(first).transform(
                    variant,boundaries=boundaries,quantization=q,
                    source_musicxml=piece.source_musicxml).timing,
            1)
    if level is not None:
        return (
            lambda line: line.generate_chordify_exercise(level),
            lambda variant,piece,boundaries,q:
                CodaReferenceChordification(level).transform(
                    variant,boundaries=boundaries,quantization=q,
                    source_musicxml=piece.source_musicxml).timing,
            1)
    raise ValueError(f"Unrecognized original Coda operation {name}")



def _exercise(name, level, line, variant, piece, boundaries, q, owners,
              exported_xml, converter, bars):
    record={"operation":name,"chord_level":level}
    author_fn, adapter_fn, factor=_operation(name,level)
    try:
        upstream=author_fn(line)
    except Exception as exc:
        record.update(status="upstream-error",type=type(exc).__name__,
                      detail=str(exc)[:250])
        return record
    if upstream is None:
        record["status"]="upstream-none"
        return record
    try:
        plan=adapter_fn(variant,piece,boundaries,q)
    except ValueError as exc:
        record.update(status="adapter-rejected",type="ValueError",
                      detail=str(exc)[:250])
        return record
    try:
        source_written=written_from_musicxml(exported_xml(upstream))
        author_sounding,tie_errors=sounding_from_written(source_written)
    except Exception as exc:
        return dict(record,status="upstream-export-error",
                    type=type(exc).__name__,detail=str(exc)[:200])
    projected=sounding_from_plan(plan,owners)
    status="unverified"
    written_status="unavailable"
    native_error=None
    try:
        native=_native_written(plan,owners,piece,bars,converter,factor=factor)
        written_status=("exact" if native==source_written else "different")
        actual,errors=sounding_from_written(native)
        if errors or actual!=projected:
            raise ValueError(f"Native notation/grading disagrees: {errors}")
    except Exception as exc:
        native_error=f"{type(exc).__name__}: {exc}"[:300]
    if tie_errors:
        status="upstream-invalid-ties"
    elif native_error:
        status="native-notation-unavailable"
    elif author_sounding==projected:
        status=("observed-strict-changing" if
                written_status=="exact" and
                projected!=sounding_from_plan(
                    OriginalTiming().transform(variant),owners)
                else "observed-both-exact-unchanged" if written_status=="exact"
                else "observed-sounding-only")
    else:
        status="observed-different"
    record.update(
        status=status,written=written_status,
        sounding="invalid-ties" if tie_errors else
                 "exact" if author_sounding==projected else "different",
        author_note_count=len(author_sounding),
        adapter_note_count=len(projected),
        author_written_count=len(source_written),
        reference_tie_errors=list(tie_errors[:4]),
        native_error=native_error,
        author_first=[vars(x) for x in author_sounding[:5]],
        adapter_first=[vars(x) for x in projected[:5]],
    )
    return record


def _case(identity,path,first_bar,last_bar,converter,meter,key,
          ExerciseLine,MusicMatrixRepresentation,exported_xml):
    filename=ROOT/path
    row={"id":identity,"source":path,"sha256":sha256(filename.read_bytes()).hexdigest(),
         "source_first_measure":first_bar,"source_last_measure":last_bar,
         "status":"diagnostic","voices":[]}
    bars=last_bar-first_bar+1
    try:
        piece=load_musicxml(filename,bpm=80)
        if len(piece.bar_boundaries)<=bars:
            raise ValueError("Incomplete selected source measures")
        end=piece.bar_boundaries[bars]
        notes=tuple(n for n in piece.notes if n.start<end-1e-7)
        if not notes:
            raise ValueError("No source attacks in excerpt")
        phrase=Phrase(1,1,bars,0,end,notes)
        variant=ExerciseVariant("original",phrase,tuple(range(len(notes))))
        matrix=MatrixScore.from_phrase(
            phrase,boundaries=tuple(piece.bar_boundaries[:bars+1]),
            source_musicxml=piece.source_musicxml)
        ref_score=converter.parse(str(filename))
        sliced=[]
        for part in ref_score.parts:
            excerpt=part.measures(first_bar,last_bar)
            voices=tuple(excerpt.voicesToParts().parts)
            sliced.extend(voices if voices else (excerpt,))
        # Original ExerciseScore derives its quantization from the shortest
        # WRITTEN note/rest in the entire excerpt, then the first meter.
        lengths=[float(item.quarterLength)
                 for part in sliced for item in part.recurse().notesAndRests
                 if item.quarterLength>0]
        if not lengths:
            raise ValueError("Original source MusicXML has no note or rest")
        original_time=next(iter(ref_score.recurse().getElementsByClass(
            meter.TimeSignature)),None)
        if original_time is None:
            raise ValueError("Original Coda requires an explicit time signature")
        import math
        q=math.ceil(1/min(lengths))*original_time.numerator
        widths=original_chord_levels(q,original_time.numerator,
                                     original_time.denominator)
        row.update(source_notes=len(notes),quantization=q,
                   automatic_chord_levels=list(widths),
                   source_voices=len(tuple(v for part in matrix.parts
                                           for v in part.voices)))
        generated=score_voice_matrices(matrix,quantization=q)
        for vi,line_stream in enumerate(sliced):
            if not tuple(line_stream.recurse().notes):
                continue
            line=ExerciseLine.__new__(ExerciseLine)
            line.original_stream=line_stream
            line.quantization=q
            line.time_signature=original_time
            line.key_signature=key.KeySignature(0)
            voice={"index":vi,"status":"diagnostic","operations":[]}
            try:
                original=line._create_matrices()
                matched=[m for m in generated if
                         all(np.array_equal(a,b) and a.shape==b.shape
                             for a,b in zip(original,(m.piano_roll,
                                           m.onset_map,m.durations_matrix)))]
                voice["mmr_exact_candidates"]=len(matched)
                if len(matched)!=1:
                    voice["status"]="mmr-unmatched-or-ambiguous"
                else:
                    line.music_matrix_representation=MusicMatrixRepresentation(
                        line.key_signature,line.time_signature,q,*original)
                    owners={index for _,_,index,_ in matched[0].owners}
                    operations=[("slow-x2",None),("slow-x4",None),
                                ("dotted-3-to-1",None),("dotted-1-to-3",None)]
                    operations.extend((f"auto-chord-{n}",n) for n in widths)
                    for name,level in operations:
                        voice["operations"].append(_exercise(
                            name,level,line,variant,piece,matrix.boundaries,
                            q,owners,exported_xml,converter,bars))
            except Exception as exc:
                voice.update(status="voice-exception",type=type(exc).__name__,
                             detail=str(exc)[:350])
            row["voices"].append(voice)
        row["compared_voices"]=len(row["voices"])
    except Exception as exc:
        row.update(status="source-unavailable",type=type(exc).__name__,
                   detail=str(exc)[:350])
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    options=parser.parse_args()
    upstream=options.upstream.resolve()
    if not (upstream/"music/exercise.py").is_file():
        raise ValueError("Pinned original Coda backend missing")
    module=types.ModuleType("services.database")
    module.MongoDatabase=type("NoDatabase",(),{"__init__":lambda self:None})
    sys.modules["services.database"]=module
    sys.path.insert(0,str(upstream))
    from music21 import converter,meter,key
    from music.exercise import ExerciseLine,MusicMatrixRepresentation
    from music.processor import get_musicxml_from_music21
    rows=[_case(*case,converter,meter,key,ExerciseLine,
                MusicMatrixRepresentation,get_musicxml_from_music21)
          for case in SOURCES]
    outcomes=[x for row in rows for voice in row["voices"]
              for x in voice["operations"]]
    totals=Counter(x["status"] for x in outcomes)
    report={
        "research_only":True,"status":"diagnostic-only",
        "author_revision":REFERENCE_SHA,
        "source_case_count":len(rows),
        "source_cases_diagnosed":sum(row["status"]=="diagnostic" for row in rows),
        "voices_with_exact_mmr":sum(
            voice.get("mmr_exact_candidates")==1
            for row in rows for voice in row["voices"]),
        "source_voices_attempted":sum(len(row["voices"]) for row in rows),
        "auto_chord_levels_attempted":sum(
            x["chord_level"] is not None for x in outcomes),
        "all_output_statuses":dict(sorted(totals.items())),
        "cases":rows,
    }
    options.report.parent.mkdir(parents=True,exist_ok=True)
    options.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({key:report[key] for key in (
        "source_case_count","source_cases_diagnosed",
        "source_voices_attempted","voices_with_exact_mmr",
        "auto_chord_levels_attempted","all_output_statuses"
    )},sort_keys=True))
    if len(rows)!=len(SOURCES):
        raise AssertionError("Incomplete wider source inventory")
    # Unsupported sources and author exceptions remain explicitly reported.
    # They are not counted as verified parity or dropped from the denominator.


if __name__=="__main__":
    main()
