"""Diagnostic, source-backed Coda comparison on nonuniform MusicXML.

Run only with the pinned unmodified author's backend, in the existing
explicit four-minute workflow. This deliberately CANNOT graduate a
complex source to 'parity' automatically: report per-voice attempts,
exceptions and exact MMR matches, including unmatched source voices.
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.research.coda_reference_exercises import (
    CodaReferenceSlowdown,CodaReferenceDotted,CodaReferenceChordification,
)
from piano_teacher.music import Phrase
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.exercise_contracts import OriginalTiming
from piano_teacher.research.coda_written_tie_segments import tie_segment_chains
from piano_teacher.research.coda_differential import (
    written_from_musicxml, sounding_from_plan, report_comparison,
)
from piano_teacher.research.coda_score_projection import _original_metadata
from piano_teacher.notation.lesson import build_lesson_score
from dataclasses import replace
from hashlib import sha256
from piano_teacher.research.coda_reference_matrix import (
    reference_quantization,score_voice_matrices,
)

ROOT=Path(__file__).resolve().parents[1]
CASES=(
    ("source-parallel-ties",
     "tests/fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml",2),
    ("source-authored-beams",
     "tests/fixtures/connector_pixels/beams/score.musicxml",1),
    ("long-multipage-first-two-bars",
     "tests/fixtures/musical_fidelity/xml_long_multipage.musicxml",2),
    ("authored-triplet",
     "tests/fixtures/research/coda_authored_triplet.musicxml",1),
    ("rest-bearing-triplet",
     "tests/fixtures/research/coda_triplet_interior_rest.musicxml",1),
    ("changing-meter",
     "tests/fixtures/research/coda_mixed_meter.musicxml",2),
)


def _music21_events(part):
    from music21 import chord
    events=[]
    for event in part.recurse().notes:
        pitches=event.pitches if isinstance(event,chord.Chord) else (event.pitch,)
        for pitch in pitches:
            events.append((round(float(event.getOffsetInHierarchy(part)),6),
                           int(pitch.midi),round(float(event.quarterLength),6)))
    return sorted(events)


def _coda_events(plan, indices):
    return sorted((round(float(plan.events[i].exercise_start),6),
                   plan.original.notes[i].pitch,
                   round(float(plan.events[i].exercise_end-plan.events[i].exercise_start),6))
                  for i in indices)



def _native_written(plan, owners, piece, bars, converter, *, factor):
    """Parse actual generated *bare* native notation, never guessed MIDI notes.

    This comparison covers pitches, rhythms, written rests and ties for the
    isolated source voice. It does not certify source expression preservation
    or the full strict Coda projected-notation pipeline.
    """
    source=plan.original.phrase
    if source.start != 0 or source.first_bar != 1:
        raise ValueError("Comparison needs a bar-one source excerpt")
    end=piece.bar_boundaries[bars]
    excerpt=replace(
        piece,bar_boundaries=tuple(piece.bar_boundaries[:bars+1]),
        time_signatures=tuple(t for t in piece.time_signatures if t[0]<end),
        key_signatures=tuple(v for v in piece.key_signatures if v.beat<end),
        clef_changes=tuple(v for v in piece.clef_changes if v.beat<end))
    grid,meters,keys,clefs=_original_metadata(excerpt,source,plan,factor)
    selected=replace(
        plan.exercise_phrase,first_bar=1,last_bar=len(grid)-1,
        notes=tuple(note for i,note in enumerate(plan.exercise_phrase.notes)
                    if i in owners))
    if not selected.notes:
        raise ValueError("No owned source-voice notes to render")
    native=build_lesson_score(
        selected,boundaries=grid,time_signatures=meters,
        key_signatures=keys,clef_changes=clefs,retimed_source=True)
    return written_from_musicxml(native.musicxml)


def _case(name: str, filename: str, bars: int, converter, meter, key,
          ExerciseLine, MusicMatrixRepresentation, get_musicxml_from_music21):
    from music21 import chord
    row={"case":name,"source":filename,"sample_bars":bars,
         "source_sha256":sha256((ROOT/filename).read_bytes()).hexdigest(),
         "status":"diagnostic","voices":[]}
    try:
        piece=load_musicxml(ROOT/filename,bpm=80)
        if len(piece.bar_boundaries)<=bars:
            raise ValueError("Source does not contain requested bar count")
        end=piece.bar_boundaries[bars]
        notes=tuple(n for n in piece.notes if n.start<end-1e-7)
        phrase=Phrase(1,1,bars,0,end,notes)
        matrix=MatrixScore.from_phrase(
            phrase,boundaries=tuple(piece.bar_boundaries[:bars+1]),
            source_musicxml=piece.source_musicxml)
        variant=ExerciseVariant("original",phrase,tuple(range(len(phrase.notes))))
        q=reference_quantization(
            min(n.end-n.start for n in notes),piece.time_signatures[0][1])
        generated=score_voice_matrices(matrix,quantization=q)
        row.update(source_attacks=len(notes),source_part_voices=len(generated),
                   quantization=q,source_duration_beats=end)
        if len(piece.bar_boundaries)==bars+1:
            chains=tie_segment_chains(
                piece,OriginalTiming().transform(variant))
            row["source_written_tie_chains"]=len(chains)
            row["source_written_tie_segments"]=sum(
                len(c.source_segments) for c in chains)
            row["distinct_sounding_attacks_in_ties"]=len({
                c.sounding_id for c in chains})
            row["written_vs_sounding_warning"]=bool(chains)
        else:
            row["source_written_tie_chains"]=None
        reference=converter.parse(str(ROOT/filename))
        candidates=[]
        for part in reference.parts:
            clipped=part.measures(1,bars)
            by_voice=clipped.voicesToParts().parts
            candidates.extend(by_voice if len(by_voice)>0 else (clipped,))
        for index,line_stream in enumerate(candidates):
            if not tuple(line_stream.recurse().notes):
                continue
            line=ExerciseLine.__new__(ExerciseLine)
            line.original_stream=line_stream
            line.quantization=q
            first_meter=piece.time_signatures[0][1:]
            line.time_signature=meter.TimeSignature(
                f"{first_meter[0]}/{first_meter[1]}")
            line.key_signature=key.KeySignature(0)
            result={"reference_voice_index":index}
            try:
                original=line._create_matrices()
                result["reference_shapes"]=[list(arr.shape) for arr in original]
                matched=[ours for ours in generated if all(
                    a.shape==b.shape and np.array_equal(a,b)
                    for a,b in zip(original,(
                        ours.piano_roll,ours.onset_map,ours.durations_matrix)))]
                result["exact_mmr_matches"]=len(matched)
                result["status"]=(
                    "exact-array-match" if len(matched)==1 else
                    "ambiguous-array-match" if len(matched)>1 else "mismatch")
                # Compare the actual author algorithms for that exact
                # matrix/voice, never only a matching note count.
                result["algorithms"]={}
                if len(matched)==1:
                    line.music_matrix_representation=MusicMatrixRepresentation(
                        line.key_signature,line.time_signature,q,*original)
                    owners={index for _,_,index,_ in matched[0].owners}
                    for name,reference_fn,ours_fn,factor in (
                        ("slow-x2",lambda:line.generate_slowed_down_exercise(2),
                         lambda:CodaReferenceSlowdown(2).transform(variant).timing,2),
                        ("slow-x4",lambda:line.generate_slowed_down_exercise(4),
                         lambda:CodaReferenceSlowdown(4).transform(variant).timing,4),
                        ("dotted-3-to-1",lambda:line.generate_dotted_exercise([1.5,.5]),
                         lambda:CodaReferenceDotted(True).transform(
                             variant,boundaries=matrix.boundaries,
                             quantization=q,source_musicxml=piece.source_musicxml).timing,1),
                        ("dotted-1-to-3",lambda:line.generate_dotted_exercise([.5,1.5]),
                         lambda:CodaReferenceDotted(False).transform(
                             variant,boundaries=matrix.boundaries,
                             quantization=q,source_musicxml=piece.source_musicxml).timing,1),
                        ("chord-2-beat",lambda:line.generate_chordify_exercise(2*q),
                         lambda:CodaReferenceChordification(2*q).transform(
                             variant,boundaries=matrix.boundaries,
                             quantization=q,source_musicxml=piece.source_musicxml).timing,1),
                    ):
                        try:
                            upstream=reference_fn()
                            if upstream is None:
                                result["algorithms"][name]={
                                    "status":"upstream-none",
                                    "written":{"status":"unavailable","reason":"author returned None"},
                                    "sounding":{"status":"unavailable","reason":"author returned None"}}
                                continue
                            author_written=written_from_musicxml(
                                get_musicxml_from_music21(upstream))
                            plan=ours_fn()
                            native_error=""
                            try:
                                native_written=_native_written(
                                    plan,owners,piece,bars,converter,factor=factor)
                            except Exception as exc:
                                # Notation may be unsupported, but this must
                                # not suppress a valid sounding comparison.
                                native_written=None
                                native_error=f"{type(exc).__name__}: {exc}"
                            outcome=report_comparison(
                                author_written,sounding_from_plan(plan,owners),
                                native_written,unavailable_reason=native_error)
                            # Keep the historic raw tuple comparison for audit,
                            # but DO NOT use it as a valid parity classification.
                            raw_observed=_music21_events(upstream)
                            raw_expected=_coda_events(plan,owners)
                            result["algorithms"][name]={
                                "status":"compared",
                                "legacy_raw_status":(
                                    "match" if raw_observed==raw_expected
                                    else "mismatch"),
                                "written_basis":"actual author-exported MusicXML versus bare native lesson MusicXML",
                                "sounding_basis":"explicit tie-collapsed author-exported MusicXML versus canonical grading TimingPlan",
                                **outcome,
                            }
                        except Exception as exc:
                            result["algorithms"][name]={
                                "status":"exception","error":type(exc).__name__,
                                "detail":str(exc)[:350]}
                # Matrix parity is independent of algorithm output parity.
                # No diagnostic exception or mismatch is promoted.
            except Exception as exc:
                result.update(status="upstream-exception",
                              error=type(exc).__name__,
                              detail=str(exc)[:450])
            row["voices"].append(result)
        row["reference_voices"]=len(row["voices"])
        row["exactly_matched_voices"]=sum(
            x["status"]=="exact-array-match" for x in row["voices"])
        row["all_exact"]=(
            row["reference_voices"]==row["source_part_voices"]
            and row["exactly_matched_voices"]==row["reference_voices"])
    except Exception as exc:
        row.update(status="diagnostic-error",error=type(exc).__name__,
                   detail=str(exc)[:700],all_exact=False)
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    checkout=args.upstream.resolve()
    if not (checkout/"music/exercise.py").is_file():
        raise ValueError("Missing pinned author backend")
    unused=types.ModuleType("services.database")
    unused.MongoDatabase=type("NoDatabase",(),{"__init__":lambda self:None})
    sys.modules["services.database"]=unused
    sys.path.insert(0,str(checkout))
    from music21 import converter,meter,key
    from music.exercise import ExerciseLine,MusicMatrixRepresentation
    from music.processor import get_musicxml_from_music21

    rows=[_case(*case,converter,meter,key,ExerciseLine,MusicMatrixRepresentation,
                get_musicxml_from_music21)
          for case in CASES]
    algorithms=[outcome for row in rows for voice in row.get("voices",())
                for outcome in voice.get("algorithms",{}).values()]
    count=lambda path,value:sum(
        outcome.get(path[0],{}).get(path[1])==value for outcome in algorithms)
    result={
        "upstream_revision":"a4eb85dfc2bd418818ca9ff775c0a11ccccb3530",
        "status":"diagnostic-only",
        "comparison_basis":"Both written scores parsed from generated MusicXML; reference tie chains collapsed separately from adapter TimingPlan",
        "native_written_scope":"bare generated notation for one source voice; authored expressive annotations not compared",
        "author_parity_proven":False,
        "reference_mmr_exact_voices":sum(row.get("exactly_matched_voices",0) for row in rows),
        "reference_mmr_sampled_voices":sum(row.get("reference_voices",0) for row in rows),
        "algorithm_total":len(algorithms),
        "algorithm_legacy_raw_exact":sum(o.get("legacy_raw_status")=="match" for o in algorithms),
        "algorithm_legacy_raw_mismatches":sum(o.get("legacy_raw_status")=="mismatch" for o in algorithms),
        "algorithm_written_exact":count(("written","status"),"exact"),
        "algorithm_written_different":count(("written","status"),"different"),
        "algorithm_written_unavailable":count(("written","status"),"unavailable"),
        "algorithm_sounding_exact":count(("sounding","status"),"exact"),
        "algorithm_sounding_different":count(("sounding","status"),"different"),
        "algorithm_sounding_invalid_ties":count(("sounding","status"),"invalid-reference-ties"),
        "algorithm_upstream_none":sum(o["status"]=="upstream-none" for o in algorithms),
        "algorithm_exceptions":sum(o["status"]=="exception" for o in algorithms),
        "cases":rows}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"cases":len(rows),
          "successful_diagnostic_cases":sum(row["status"]=="diagnostic" for row in rows),
          "source_match_counts":[(row["case"],row.get("exactly_matched_voices",0),
            row.get("reference_voices",0)) for row in rows],
          "algorithm_sounding_exact":result["algorithm_sounding_exact"],
          "algorithm_written_exact":result["algorithm_written_exact"],
          "algorithm_written_unavailable":result["algorithm_written_unavailable"],
          "algorithm_legacy_raw_exact":result["algorithm_legacy_raw_exact"],
          "algorithm_total":result["algorithm_total"]},sort_keys=True))
    # Missing fixtures and broken imports are infrastructure failures.
    # Legitimate author mismatches/errors remain in the source-bound report.
    if result["algorithm_exceptions"]:
        raise AssertionError(
            "Coda differential infrastructure/algorithm exception: "
            f"{result['algorithm_exceptions']} cases; inspect retained report")
    if (result["algorithm_total"] !=
            result["algorithm_upstream_none"] +
            result["algorithm_exceptions"] +
            sum(o["status"]=="compared" for o in algorithms)):
        raise AssertionError("Coda diagnostic did not classify every algorithm")
    if any(row.get("status")=="diagnostic-error" for row in rows):
        raise AssertionError("Coda score diagnostics could not run one or more source fixtures")


if __name__=="__main__":
    main()
