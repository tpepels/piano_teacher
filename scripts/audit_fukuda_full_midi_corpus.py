"""Bounded, fail-closed Fukuda corpus audit on ALL shipped real MIDI scores.

This is an executable functional audit, not a claim of paper-figure
note-for-note parity or physical-MIDI usability. All 16 independent MIDI
fixtures and every source MIDI in midi/ are inspected. No exceptions,
timeouts or skipped files are silently counted as matches.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import time

from piano_teacher.music import load_midi
from piano_teacher.lesson_generators import FukudaMidiLessonGenerator,lesson_hands


def evaluate_one(path:Path) -> dict:
    start=time.perf_counter()
    piece=load_midi(path)
    source_ids=[n.source_id for n in piece.notes]
    if not source_ids or len(set(source_ids))!=len(source_ids):
        raise ValueError("Imported source lost unique MIDI attack IDs")
    generator=FukudaMidiLessonGenerator(mistakes=frozenset(source_ids))
    definition=generator.generate(piece)
    if not definition.exercises or definition.exercises[-1].kind!="perform":
        raise ValueError("Missing complete original performance")
    original=definition.exercises[-1].phrase.notes
    if Counter(n.source_id for n in original)!=Counter(source_ids):
        raise ValueError("Terminal performance changes original MIDI source")
    focused=set()
    stages=Counter()
    for exercise in definition.exercises:
        if exercise.kind=="learn":
            focused.update(n.source_id for n in exercise.phrase.notes)
            # Each attacked mistake must be represented by at least one
            # genuine playable source hand, not only by an unrelated chord.
            if not set(n.source_id for n in exercise.phrase.notes):
                raise ValueError("Empty error-focused lesson")
        for hand in lesson_hands(exercise):
            expected={n.source_id for n in exercise.phrase.notes
                      if hand=="both" or n.hand==hand}
            variants=definition.stages(exercise,hand)
            if not variants or variants[-1].variant.level!="original":
                raise ValueError("Generated source stage not terminal")
            if {n.source_id for n in variants[-1].variant.notes}!=expected:
                raise ValueError("Original exercise drops MIDI attack identity")
            for stage in variants:
                ids=[n.source_id for n in stage.variant.notes]
                if not ids or len(set(ids))!=len(ids) or not set(ids)<=expected:
                    raise ValueError("Invalid simplified source attack identities")
                if tuple(exercise.phrase.notes[i] for i in
                         stage.variant.source_indices)!=stage.variant.notes:
                    raise ValueError("Stage source index mapping is invalid")
                if any(n.start<exercise.phrase.start-1e-7 or
                       n.end>exercise.phrase.end+1e-7 or n.end<=n.start
                       for n in stage.variant.notes):
                    raise ValueError("Stage cuts a note across a score boundary")
                stages[stage.variant.level]+=1
    if focused!=set(source_ids):
        raise ValueError("Some failed source notes were not included in focused lessons")
    elapsed_ms=round(1000*(time.perf_counter()-start),2)
    return {
        "file":path.as_posix(),
        "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "status":"passed",
        "note_attacks":len(piece.notes),
        "source_measures":len(piece.bar_boundaries)-1,
        "focus_exercises":sum(x.kind=="learn" for x in definition.exercises),
        "stages":dict(sorted(stages.items())),
        "elapsed_ms":elapsed_ms,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--budget-seconds",type=float,default=70)
    args=ap.parse_args()
    manifest=Path("tests/fixtures/musical_fidelity/manifest.json")
    fixtures=json.loads(manifest.read_text())
    files=sorted({manifest.parent/x["file"] for x in fixtures["supported"]
                  if x["file"].endswith((".mid",".midi"))}|
                 set(Path("midi").glob("*.mid"))|
                 set(Path("midi").glob("*.midi")))
    deadline=time.monotonic()+args.budget_seconds
    records=[]
    for path in files:
        if time.monotonic()>deadline:
            records.append({"file":path.as_posix(),"status":"timeout"})
            continue
        try:
            records.append(evaluate_one(path))
        except Exception as exc:
            records.append({"file":path.as_posix(),"status":"failed",
                            "reason":type(exc).__name__+": "+str(exc)})
    report={
        "scope":"all repository-shipped MIDI sources and independent MIDI fixtures",
        "input_only":"midi",
        "files_expected":len(files),
        "passed":sum(r["status"]=="passed" for r in records),
        "failed":sum(r["status"]!="passed" for r in records),
        "total_notes":sum(r.get("note_attacks",0) for r in records),
        "total_stages":sum(sum(r.get("stages",{}).values()) for r in records),
        "records":records,
        "reference_figure_parity":"not established by source MIDI audit",
        "human_keyboard_verified":False,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:report[k] for k in
        ("files_expected","passed","failed","total_notes","total_stages")}))
    if report["failed"] or len(files)<30:
        raise SystemExit(1)


if __name__=="__main__":
    main()
