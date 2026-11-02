"""MIDI score vs performed MIDI: Fukuda DTW source-mistake diagnostic."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from piano_teacher.fukuda_midi_performance import analyze_recorded_midi


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--score",type=Path,required=True)
    parser.add_argument("--performance",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    result=analyze_recorded_midi(args.score,args.performance)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"score_attacks":result["score_attacks"],
                      "performed_attacks":result["performed_attacks"],
                      "aligned":result["dtw_aligned_onsets"],
                      "mismatches":len(result["mismatches"]),
                      "extras":len(result["extra_notes"])},sort_keys=True))


if __name__=="__main__":
    main()
