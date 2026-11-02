"""Produce a manifest-complete MIDI Coda note-ownership audit.

Never print a blanket original-Coda parity claim. Unsupported fixtures
are explicitly recorded as rejected with a reason; the default exit code
rejects an incomplete corpus unless --allow-rejected is specified.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from piano_teacher.music import load_midi
from piano_teacher.research.coda_live_note_audit import audit_coda_midi


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--manifest",type=Path,default=Path(
        "tests/fixtures/musical_fidelity/manifest.json"))
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--allow-rejected",action="store_true")
    args=cli.parse_args()
    manifest=json.loads(args.manifest.read_text())
    filenames=sorted({x["file"] for x in manifest["supported"]
                       if x["file"].endswith((".mid",".midi"))})
    result={"schema":"coda-midi-all-stages-v1","source":"independent MIDI corpus",
            "original_backend_note_parity":"unproven",
            "files":[]}
    failed=0
    for name in filenames:
        try:
            piece=load_midi(args.manifest.parent/name)
            audit=audit_coda_midi(piece)
            result["files"].append({"file":name,"status":"audited",**audit.as_dict()})
        except Exception as exc:
            failed+=1
            result["files"].append({"file":name,"status":"rejected",
                                    "error":type(exc).__name__+": "+str(exc)})
    result["fixture_count"]=len(filenames)
    result["audited"]=len(filenames)-failed
    result["rejected"]=failed
    result["total_stages"]=sum(len(x.get("stages",())) for x in result["files"])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:result[k] for k in ("fixture_count","audited",
                                            "rejected","total_stages")}))
    if failed and not args.allow_rejected:
        raise SystemExit(1)


if __name__=="__main__":
    main()
