"""Blinded real-player Coda-vs-heuristic study assignment and analysis.

No student data are fetched from the app. Explicit enrollment, consent,
fixed original-score pre/post testing and intervention delivery are required.
Keep the randomization secret OUTSIDE the repository and study dataset.
"""
from __future__ import annotations
import argparse
from dataclasses import fields
import json
import os
from pathlib import Path

from piano_teacher.research.coda_pedagogy_pilot import (
    PilotObservation, PROTOCOL, analyze_pilot, assigned_arm,
)


def main():
    cli=argparse.ArgumentParser()
    subs=cli.add_subparsers(dest="command",required=True)
    assign=subs.add_parser("assign")
    assign.add_argument("--anonymous-subject",required=True)
    assign.add_argument("--piece-fingerprint",required=True)
    analyze=subs.add_parser("analyze")
    analyze.add_argument("--input",type=Path,required=True)
    analyze.add_argument("--output",type=Path,required=True)
    args=cli.parse_args()
    secret=os.environ.get("CODA_STUDY_RANDOMIZATION_SECRET","")
    if len(secret)<16:
        cli.error("Set private CODA_STUDY_RANDOMIZATION_SECRET (at least 16 characters)")
    if args.command=="assign":
        print(json.dumps({"protocol":PROTOCOL,
             "anonymous_subject":args.anonymous_subject,
             "piece_fingerprint":args.piece_fingerprint,
             "blinded_arm":assigned_arm(
                 args.anonymous_subject,args.piece_fingerprint,secret=secret)},
             sort_keys=True))
    else:
        payload=json.loads(args.input.read_text())
        if payload.get("protocol")!=PROTOCOL:
            cli.error("Input contains a different preregistered protocol")
        allowed={f.name for f in fields(PilotObservation)}
        if any(set(row)!=allowed for row in payload.get("observations",())):
            cli.error("Study records must contain precisely the expected fields")
        observations=tuple(PilotObservation(**item)
                           for item in payload["observations"])
        result=analyze_pilot(observations,secret=secret)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps({"protocol":PROTOCOL,
             "observations":result["observations"],
             "pieces":len(result["pieces"]),
             "study_conclusion":result["study_conclusion"]}))


if __name__=="__main__":
    main()
