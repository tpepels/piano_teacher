#!/usr/bin/env python3
"""Fail closed unless all 17 complete scores passed in all 3 hand modes.

A job never earns full-corpus status by passing a smaller --only / --index
subset. This independent aggregate consumes one JSON result per score and
hand, plus per-window pixel/pitch coverage. Failed or missing CI jobs cannot
disappear from the denominator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


HANDS = ("both","right","left")


def aggregate(folder: Path, *, scores: int = 17) -> dict:
    errors=[]
    found={}
    for index in range(scores):
        for hand in HANDS:
            item=folder/f"phase3-report-{index}-{hand}"/"summary.json"
            if not item.is_file():
                errors.append(f"Missing required full-score report: {index}/{hand}")
                continue
            try:
                data=json.loads(item.read_text())
            except (OSError,ValueError) as exc:
                errors.append(f"Unreadable report {index}/{hand}: {exc}")
                continue
            if data.get("hand")!=hand or data.get("scores_total")!=scores:
                errors.append(f"Wrong mode/corpus denominator: {index}/{hand}")
            if data.get("scores_passed")!=1 or data.get("scores_failed") or not data.get("passed"):
                errors.append(f"Failed/incomplete score: {index}/{hand}")
            attempted=data.get("scores_attempted",[])
            if len(attempted)!=1:
                errors.append(f"Score index {index}/{hand} did not audit exactly one score")
                continue
            name=attempted[0]
            found[index,hand]=name
            reports=data.get("scores",[])
            if len(reports)!=1:
                errors.append(f"{index}/{hand}: missing whole-score report")
                continue
            result=reports[0]
            if not result.get("passed"):
                errors.append(f"{index}/{hand}: whole-score failed")
            if result.get("measures_expected")!=result.get("measures_witnessed"):
                errors.append(f"{index}/{hand}: incomplete measure coverage")
            windows=result.get("windows",[])
            if not windows:
                errors.append(f"{index}/{hand}: no actual window evidence")
            for window in windows:
                witness=window.get("whole_window_coverage",{})
                pixels=witness.get("independent_image_pitch",{})
                if not pixels.get("passed"):
                    errors.append(f"{index}/{hand} window "
                                  f"{window['first_bar']}-{window['last_bar']}: "
                                  "independent raster pitch not passed")
                if pixels.get("image_pitch_verified") != pixels.get("written_active_noteheads"):
                    errors.append(f"{index}/{hand}: unverified written notehead")
                if witness.get("missing_measure_starts") or witness.get("missing_notes") or witness.get("missing_rests"):
                    errors.append(f"{index}/{hand}: missing native screenshot/identity")
            if name.endswith(".musicxml"):
                for key in ("independent_original_musicxml",
                            "independent_generated_symbol_inventory"):
                    if not result.get(key,{}).get("passed"):
                        errors.append(f"{index}/{hand}: original MusicXML evidence missing")
    # All three hands must be the *same* source at each corpus index.
    for index in range(scores):
        names={found.get((index,hand)) for hand in HANDS}
        if len(names)!=1 or None in names:
            errors.append(f"Corpus index {index} missing/changed among modes")
    both={found.get((i,"both")) for i in range(scores)}
    if len(both)!=scores or None in both:
        errors.append("Score indices do not represent exactly the full pinned corpus")
    return {
        "passed":not errors,
        "expected_scores":scores,"expected_modes":list(HANDS),
        "required_jobs":scores*len(HANDS),
        "jobs_with_results":len(found),
        "unique_sources":len(both-{None}),
        "errors":errors,
        "coverage_claim":"Every window and written-pitch head witnessed in actual "
                         "Godot screenshots in all three Practice hand modes. "
                         "This does not imply every engraved symbol shape is "
                         "independently classified in dense music.",
    }


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    result=aggregate(args.root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    print(f"Phase 3 corpus {result['jobs_with_results']}/"
          f"{result['required_jobs']} jobs; "
          f"{result['unique_sources']}/"
          f"{result['expected_scores']} unique sources")
    for error in result["errors"]:
        print("FAIL",error)
    return 0 if result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
