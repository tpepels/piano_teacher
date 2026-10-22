#!/usr/bin/env python3
"""Capture whole pieces and account independently for each visual construct.

Original MusicXML establishes source coverage; generated XML selects required
glyphs. Actual framebuffer pixels supply staff rails, notehead silhouettes and
controlled rest contours. Renderer telemetry is supplemental diagnostic data.
Every unavailable detector or inseparable glyph remains explicitly nonverified.

Usage:
  python scripts/audit_phase3_whole_pieces.py --out /tmp/phase3 --only "Danny_Boy"
  python scripts/audit_phase3_whole_pieces.py --out /tmp/phase3 --all --all-hands
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json
import shutil
import sys
import hashlib
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from piano_teacher.score import import_piece
# Imported as a script in CI and as a package module in pytest.
if __package__:
    from scripts.check_native_verovio_overlay import ROOT, AuditCase, run
else:
    from check_native_verovio_overlay import ROOT, AuditCase, run

# Explicit, pinned set. Never discover just the easiest files and call that
# complete corpus coverage. The report lists missing/unrun scores by name.
BUNDLED_MIDI = (
    "Ala_–_Joep_Beving.midi",
    "Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi",
    "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi",
    "Danny_Boy(Bill_Evans_Ver_).midi",
    "Merry-Go-Round-of-Life.midi",
    "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi",
    "Waltz_for_Debby.midi",
)

# MusicXML is the only source format that independently specifies a written
# score. Include every explicitly supported reference case, not just excerpts
# chosen because they render well.
MANIFEST = json.loads((ROOT/"tests/fixtures/musical_fidelity/manifest.json").read_text())
MUSICXML_REFERENCE = tuple(
    "tests/fixtures/musical_fidelity/" + case["file"]
    for case in MANIFEST["supported"] if case["file"].endswith(".musicxml")
)
ALL_SOURCES = BUNDLED_MIDI + MUSICXML_REFERENCE


def unverified_window_elements(source: Path, name: str, hand: str, first: int,
                               last: int, out: Path, reason: str) -> list[dict]:
    """A crashed capture cannot erase its original inventory denominator."""
    from piano_teacher.notation.visual_coverage import source_inventory, visual_elements
    original=source.read_text() if source.suffix==".musicxml" else None
    generated=out/"score.musicxml"
    if generated.is_file():
        rows=visual_elements(original,generated.read_text(),{}, {},hand=hand,
                             first_bar=first,last_bar=last,source_name=name)
    else:
        rows=source_inventory(original,hand=hand,source_name=name)
        rows=[row for row in rows if first <= row["source"].get("measure_index",first) <= last]
        if original is None:
            for row in rows:
                row["id"]=f"w{first}-{last}:"+row["id"]
                row["source"]["measure"]=first
    return [dict(row,status="unsupported",reason="MIDI has no unique original written score")
            if row["construct"]=="midi_written_transcription" else
            dict(row,status="unverified",reason=reason) for row in rows]


def measure_windows(number_of_bars: int, max_bars: int = 4) -> tuple[tuple[int,int], ...]:
    if number_of_bars < 1 or max_bars < 1:
        raise ValueError("Measure and window counts must be positive")
    result = tuple((i, min(i+max_bars-1, number_of_bars))
                   for i in range(1,number_of_bars+1,max_bars))
    assert [bar for first,last in result for bar in range(first,last+1)] == list(
        range(1,number_of_bars+1))
    return result


def piece_measure_windows(piece, max_bars: int = 4) -> tuple[tuple[int,int], ...]:
    """Retain every bar, joining attack-free chunks to an adjacent context.

    A tail may contain a held continuation or silence without a new attack.
    The production lesson builder requires an attack in a phrase; joining such
    windows preserves the complete bar grid and lets it engrave continuations.
    The global onset limit still rejects oversized dense captures explicitly.
    """
    result=[]
    opening=None
    bars=len(piece.bar_boundaries)-1
    for first,last in measure_windows(bars,max_bars):
        start,end=piece.bar_boundaries[first-1],piece.bar_boundaries[last]
        if any(start<=note.start<end for note in piece.notes):
            result.append((opening if opening is not None else first,last))
            opening=None
        elif result:
            result[-1]=(result[-1][0],last)
        elif opening is None:
            opening=first
    return tuple(result) if result else ((1,bars),)


def verify_complete_windows(number_of_bars: int,
                            windows: list[dict]) -> dict:
    """Refuse duplicates, skipped measures and partially witnessed symbols.

    Does not infer pixel validity from a test name or count alone: every
    window has to provide its own exact native-screenshot coverage object.
    """
    observed = Counter()
    errors = []
    source_notes = source_rests = frames = 0
    for row in windows:
        for measure in range(int(row["first_bar"]),int(row["last_bar"])+1):
            observed[measure] += 1
        witness = row.get("whole_window_coverage")
        if row.get("errors"):
            errors.extend(row["errors"])
        if witness is None:
            errors.append(f"Window {row.get('first_bar')}-{row.get('last_bar')} "
                          "has no actual screenshot witness")
            continue
        if any(witness.get(k) for k in (
            "missing_notes","missing_rests","missing_measure_starts",
            "unexpected_notes","unexpected_rests")):
            errors.append(f"Incomplete symbol witness for {row['first_bar']}-"
                          f"{row['last_bar']}")
        if witness["sampled_measures"] != witness["measure_count"]:
            errors.append(f"Uncaptured measure(s) {row['first_bar']}-"
                          f"{row['last_bar']}")
        if witness["measure_count"] != row["last_bar"] - row["first_bar"] + 1:
            errors.append(f"Window reports wrong number of measures for "
                          f"{row['first_bar']}-{row['last_bar']}")
        if (witness["source_noteheads"] !=
                witness["unique_rendered_noteheads"]):
            errors.append(f"Not all notes were visibly recorded in "
                          f"{row['first_bar']}-{row['last_bar']}")
        if witness["source_rests"] != witness["unique_rendered_rests"]:
            errors.append(f"Not all rests were visibly recorded in "
                          f"{row['first_bar']}-{row['last_bar']}")
        if witness["screenshot_count"] < witness["measure_count"]:
            errors.append(f"Too few actual frames to cover measures "
                          f"{row['first_bar']}-{row['last_bar']}")
        source_notes += witness["source_noteheads"]
        source_rests += witness["source_rests"]
        frames += witness["screenshot_count"]
    missing = [n for n in range(1,number_of_bars+1) if observed[n]==0]
    duplicated = [n for n in range(1,number_of_bars+1) if observed[n]>1]
    unexpected = sorted(set(observed)-set(range(1,number_of_bars+1)))
    if missing or duplicated or unexpected:
        errors.append("Invalid measure coverage: missing=%s duplicated=%s "
                      "unexpected=%s" % (missing,duplicated,unexpected))
    return {
        "passed":not errors,
        "measures_expected":number_of_bars,
        "measures_witnessed":len(observed)-len(unexpected),
        "notes_image_proximity_witnessed":source_notes,
        "rests_image_proximity_witnessed":source_rests,
        "native_frames_checked":frames,
        "missing_measures":missing,
        "duplicated_measures":duplicated,
        "unexpected_measures":unexpected,
        "errors":errors,
        "evidence_level":"whole-piece native visual presence and image-ink "
            "proximity; independent note-pitch/glyph recognition on actual "
            "dense frames not yet certified",
    }


def audit_piece(name: str, directory: Path, godot: str,
                *, max_bars: int, hand: str = "both",reuse_captures=False) -> dict:
    source = ROOT / (name if "/" in name else "midi/" + name)
    piece, _ = import_piece(source)
    measure_count = len(piece.bar_boundaries)-1
    if measure_count < 1 or not piece.notes:
        raise ValueError(f"{name}: empty original piece")
    parts = piece_measure_windows(piece,max_bars)
    reports = []
    for first,last in parts:
        case=AuditCase(f"phase3-{source.stem}-{first:03d}-{last:03d}",
                       name,first,last,hand)
        out = directory / f"measures-{first:03d}-{last:03d}"
        print(f"PHASE3 {name}: measures {first}-{last}/{measure_count}",
              flush=True)
        try:
            report=run(out,godot,case,all_symbols=True,strict=False,
                       reuse_captures=reuse_captures)
            from piano_teacher.notation.visual_coverage import visual_elements
            pitch=json.loads((out/"independent-pixels.json").read_text())
            rests=json.loads((out/"independent-rests.json").read_text())
            elements=visual_elements(
                source.read_text() if source.suffix==".musicxml" else None,
                (out/"score.musicxml").read_text(),pitch,rests,hand=hand,
                first_bar=first,last_bar=last,source_name=name)
            row={"first_bar":first,"last_bar":last,
                 "whole_window_coverage":report["whole_window_coverage"],
                 "errors":report["errors"],"visual_elements":elements}
            row["whole_window_coverage"]["elements"]=elements
        except Exception as exc:
            try:
                uncovered=unverified_window_elements(source,name,hand,first,last,out,str(exc))
            except Exception as inventory_error:
                uncovered=[]
            row={"first_bar":first,"last_bar":last,
                 "whole_window_coverage":None,"errors":[str(exc)],
                 "visual_elements":uncovered+[{
                     "id":f"{name}:{first}-{last}:capture",
                     "construct":"window_capture","status":"unverified",
                     "source":{"measure":first,"staff":hand,"voice":None},
                     "reason":str(exc)}]}
        reports.append(row)
        # Preserve partial evidence after each window, including failures.
        (directory/"windows.json").write_text(json.dumps(reports,indent=2)+"\n")
    combined=verify_complete_windows(measure_count,reports)
    # Source note count comes from import; the native per-window note count
    # may be larger due to tied continuation segments.
    combined["original_source_note_attacks"]=len(piece.notes)
    combined["piece"]=name
    combined["hand"]=hand
    combined["windows"]=reports
    from piano_teacher.notation.visual_coverage import coverage_counts
    combined["visual_elements"]=[e for row in reports for e in row["visual_elements"]]
    combined["visual_coverage"]=coverage_counts(combined["visual_elements"])
    mismatches=[e for e in combined["visual_elements"] if e["status"]=="mismatch"]
    if mismatches:
        combined["passed"]=False
        combined["errors"].extend(
            f"{e['construct']} {e['source']}: {e.get('reason','source/image mismatch')}"
            for e in mismatches)
    combined["complete"]=all(e["status"]=="verified" for e in combined["visual_elements"])
    (directory/"whole-piece.json").write_text(
        json.dumps(combined,indent=2)+"\n",encoding="utf-8")
    return combined


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--only",help="Pilot score filename substring")
    group.add_argument("--index",type=int,
                       help="Zero-based index into the pinned 17-score corpus")
    group.add_argument("--all",action="store_true",
                       help="Attempt all seven MIDI pieces plus all supported MusicXML scores")
    parser.add_argument("--window-bars",type=int,default=4)
    parser.add_argument("--hand",choices=("both","right","left"),default="both",
                        help="Render full piece using this real Practice hand mode")
    parser.add_argument("--all-hands",action="store_true",
                        help="Write a separate canonical report for every hand mode")
    parser.add_argument("--allow-incomplete",action="store_true",
                        help="Exploratory execution only: return success for unsupported coverage, never a complete proof")
    parser.add_argument("--reuse-captures",action="store_true",
                        help="Reanalyze existing actual PNGs only when source/layout/protocol provenance matches exactly")
    args=parser.parse_args(argv)
    args.out.mkdir(parents=True,exist_ok=True)
    if args.index is not None:
        if not 0 <= args.index < len(ALL_SOURCES):
            parser.error(f"Corpus index {args.index} outside 0..{len(ALL_SOURCES)-1}")
        selected = (ALL_SOURCES[args.index],)
    else:
        selected=(ALL_SOURCES if args.all else tuple(
            name for name in ALL_SOURCES
            if args.only.lower() in name.lower()))
    if not selected:
        parser.error(f"No explicitly pinned score matches {args.only!r}")
    if len(selected)>1 or args.all_hands:
        matrix=[]
        for name in selected:
            index=ALL_SOURCES.index(name)
            for hand in (("both","right","left") if args.all_hands else (args.hand,)):
                destination=args.out/f"phase3-report-{index}-{hand}"
                options=["--index",str(index),"--hand",hand,"--window-bars",str(args.window_bars),
                         "--out",str(destination)]
                if args.reuse_captures:
                    options.append("--reuse-captures")
                if args.allow_incomplete:
                    options.append("--allow-incomplete")
                code=main(options)
                result=json.loads((destination/"summary.json").read_text())
                matrix.append({"source":name,"source_index":index,"hand":hand,
                               "passed":result["passed"],"complete":result["complete"],
                               "report":str(destination/"summary.json"),"exit_code":code})
        summary={"schema_version":1,"verification_kind":"visual-matrix",
                 "passed":all(r["passed"] for r in matrix),
                 "complete":len(matrix)==len(ALL_SOURCES)*3 and all(r["complete"] for r in matrix),
                 "cases_attempted":len(matrix),"required_full_corpus_cases":len(ALL_SOURCES)*3,
                 "cases":matrix}
        (args.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
        return int(any(r["exit_code"] for r in matrix))
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Real native Godot renderer is mandatory")
    results=[]
    errors=[]
    for name in selected:
        try:
            result=audit_piece(name,args.out/Path(name).stem,godot,
                               max_bars=args.window_bars,hand=args.hand,
                               reuse_captures=args.reuse_captures)
            results.append(result)
            if not result["passed"]:
                errors.append({"score":name,"errors":result["errors"]})
        except Exception as exc:
            errors.append({"score":name,"error":str(exc)})
            print(f"PHASE3 FAILURE {name}: {exc}",file=sys.stderr,flush=True)
    report={
        "phase":3,
        "hand":args.hand,
        "schema_version":1,"verification_kind":"visual",
        "passed":not errors,
        "complete":bool(results) and not errors and all(r["complete"] for r in results),
        "corpus_fully_audited":set(selected)==set(ALL_SOURCES)
            and not errors,
        "scores_total":len(ALL_SOURCES),
        "bundled_midi_total":len(BUNDLED_MIDI),
        "musicxml_reference_total":len(MUSICXML_REFERENCE),
        "scores_attempted":list(selected),
        "scores_not_attempted":sorted(set(ALL_SOURCES)-set(selected)),
        "scores_passed":sum(r["passed"] for r in results),"scores_failed":errors,
        "scores":results,
        "limitations":[
            "Unsupported, ambiguous and unverified elements never establish complete visual proof",
            "MIDI does not uniquely specify written notation or rhythmic spelling",
            "Semantic verification runs independently in audit_phase3_semantics.py",
        ],
    }
    from piano_teacher.notation.visual_coverage import coverage_counts
    report["elements"]=[e for result in results for e in result["visual_elements"]]
    report["coverage"]=coverage_counts(report["elements"])
    if len(selected)==1:
        name=selected[0]
        path=ROOT/(name if "/" in name else "midi/"+name)
        report.update(source=name,source_index=ALL_SOURCES.index(name),
                      source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    report["environment"]={"python":platform.python_version(),
        "godot":subprocess.check_output([godot,"--version"],text=True).strip(),
        "framebuffer":[1536,520],"rest_difference_protocol":2}
    from scripts.notation_release_provenance import current_provenance
    report["provenance"]=current_provenance()
    (args.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PHASE3 REPORT:",report["scores_passed"],"passed,",len(errors),
          "failed; corpus complete:",report["corpus_fully_audited"],flush=True)
    return int(bool(errors) or (not report["complete"] and not args.allow_incomplete))


if __name__=="__main__":
    raise SystemExit(main())
