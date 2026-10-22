#!/usr/bin/env python3
"""Phase 3: complete-score native witness accounting, not selected excerpts.

Every measure gets a start-frame, and every note and rest onset is also
captured at the real Godot fixed playhead. Each window must achieve 100%
Godot symbol identity and proximity-ink coverage. This is a useful first
full-piece gate, NOT independent image-space glyph identification of dense
music (scheduled for the next stage of Phase 3).

Usage:
  python scripts/audit_phase3_whole_pieces.py --out /tmp/phase3 --only "Danny_Boy"
  python scripts/audit_phase3_whole_pieces.py --out /tmp/phase3 --all
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
import argparse
import json
import shutil
import sys

from piano_teacher.score import import_piece
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.proof import (
    verify_original_musicxml, verify_generated_engraving
)
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


def measure_windows(number_of_bars: int, max_bars: int = 4) -> tuple[tuple[int,int], ...]:
    if number_of_bars < 1 or max_bars < 1:
        raise ValueError("Measure and window counts must be positive")
    result = tuple((i, min(i+max_bars-1, number_of_bars))
                   for i in range(1,number_of_bars+1,max_bars))
    assert [bar for first,last in result for bar in range(first,last+1)] == list(
        range(1,number_of_bars+1))
    return result


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
                *, max_bars: int, hand: str = "both") -> dict:
    source = ROOT / (name if "/" in name else "midi/" + name)
    piece, _ = import_piece(source)
    measure_count = len(piece.bar_boundaries)-1
    if measure_count < 1 or not piece.notes:
        raise ValueError(f"{name}: empty original piece")
    parts = measure_windows(measure_count,max_bars)
    reports = []
    for first,last in parts:
        case=AuditCase(f"phase3-{source.stem}-{first:03d}-{last:03d}",
                       name,first,last,hand)
        out = directory / f"measures-{first:03d}-{last:03d}"
        print(f"PHASE3 {name}: measures {first}-{last}/{measure_count}",
              flush=True)
        report=run(out,godot,case,all_symbols=True)
        reports.append({
            "first_bar":first,"last_bar":last,
            "whole_window_coverage":report["whole_window_coverage"],
        })
    combined=verify_complete_windows(measure_count,reports)
    # Source note count comes from import; the native per-window note count
    # may be larger due to tied continuation segments.
    combined["original_source_note_attacks"]=len(piece.notes)
    combined["piece"]=name
    combined["hand"]=hand
    combined["windows"]=reports
    if source.suffix == ".musicxml":
        # Whole-piece, independent source semantics. Window-level evidence
        # alone could agree with a wrongly transcribed generated score.
        full_phrase = Phrase(1,1,measure_count,
                             piece.bar_boundaries[0],
                             piece.bar_boundaries[-1],piece.notes)
        full_score = build_lesson_score(
            full_phrase,boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,
            key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes,
            barlines=piece.barlines,source_musicxml=piece.source_musicxml)
        full_model = build_score_model(full_score,
                                      boundaries=piece.bar_boundaries)
        original = verify_original_musicxml(source.read_text(),full_model)
        generated = verify_generated_engraving(
            full_score.musicxml,full_model)
        combined["independent_original_musicxml"]=original
        combined["independent_generated_symbol_inventory"]=generated
        if not original["passed"] or not generated["passed"]:
            combined["passed"]=False
            combined["errors"].extend(original["errors"])
            combined["errors"].extend(generated["errors"])
    (directory/"whole-piece.json").write_text(
        json.dumps(combined,indent=2)+"\n",encoding="utf-8")
    if not combined["passed"]:
        raise AssertionError(f"{name}: whole-piece coverage incomplete: "
                             + repr(combined["errors"]))
    return combined


def main() -> int:
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
    args=parser.parse_args()
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
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Real native Godot renderer is mandatory")
    results=[]
    errors=[]
    for name in selected:
        try:
            result=audit_piece(name,args.out/Path(name).stem,godot,
                               max_bars=args.window_bars,hand=args.hand)
            results.append(result)
        except Exception as exc:
            errors.append({"score":name,"error":str(exc)})
            print(f"PHASE3 FAILURE {name}: {exc}",file=sys.stderr,flush=True)
    report={
        "phase":3,
        "hand":args.hand,
        "passed":not errors,
        "corpus_fully_audited":set(selected)==set(ALL_SOURCES)
            and not errors,
        "scores_total":len(ALL_SOURCES),
        "bundled_midi_total":len(BUNDLED_MIDI),
        "musicxml_reference_total":len(MUSICXML_REFERENCE),
        "scores_attempted":list(selected),
        "scores_not_attempted":sorted(set(ALL_SOURCES)-set(selected)),
        "scores_passed":len(results),"scores_failed":errors,
        "scores":results,
        "limitations":[
            "The Phase 3 pilot records real native ink/identity for every "
            "symbol onset, but does not independently classify dense glyphs",
            "MIDI does not uniquely specify written notation or rhythmic spelling",
            "Whole-piece cross-hand, key/clef/voice and symbol-type comparisons "
            "will be added as separate independent image checks",
            "Independent original-source MusicXML semantic checks are run on "
            "each MusicXML source; most remain unattempted in pilot mode",
        ],
    }
    (args.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PHASE3 REPORT:",len(results),"passed,",len(errors),
          "failed; corpus complete:",report["corpus_fully_audited"],flush=True)
    return int(bool(errors))


if __name__=="__main__":
    raise SystemExit(main())
