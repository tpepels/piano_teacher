#!/usr/bin/env python3
"""Capture additional independently authored MusicXML scores in actual Godot.

This runner fails closed if any test score cannot be imported, loaded or
captured. The separate image oracle inspects every PNG in the same run.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_native_verovio_overlay import AuditCase, fixture
from scripts.notation_release_provenance import current_provenance
from piano_teacher.notation.symbol_pixel_proof import (prove_rest_ink, prove_accidental_ink, prove_beam_ink, prove_tie_ink, prove_note_rhythm_ink, prove_slur_ink)

CASES = (
    (AuditCase("written-rests", "tests/fixtures/native_pixel_rest_probe.musicxml",
               1, 4, "both"), (0, 2, 4, 5, 8, 11, 12)),
    (AuditCase("written-accidentals", "tests/fixtures/native_pixel_accidental_probe.musicxml",
               1, 2, "both"), tuple(range(8))),
    (AuditCase("source-beams", "tests/fixtures/native_pixel_beam_probe.musicxml",
               1, 2, "both"), (0.25,0.75,1.25,1.75,2.25,2.75,3.25,3.75)),
    (AuditCase("source-ties", "tests/fixtures/native_pixel_tie_probe.musicxml",
               1, 2, "both"), (0,1,2,3,4)),
    (AuditCase("written-rhythms", "tests/fixtures/native_pixel_rhythm_probe.musicxml",
               1, 3, "both"), (0,4,6,7,7.5,8,9.5,10)),
    (AuditCase("source-slur", "tests/fixtures/native_pixel_slur_probe.musicxml",
               1, 2, "both"), (1.5,)),
)

def capture_all(out: Path, godot: str | None = None) -> list[dict]:
    godot = godot or shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Actual native Godot is required")
    captured = []
    provenance = current_provenance()
    proofs = {"written-rests":prove_rest_ink,
              "written-accidentals":prove_accidental_ink,
              "source-beams":prove_beam_ink,
              "source-ties":prove_tie_ink,
              "written-rhythms":prove_note_rhythm_ink,
              "source-slur":prove_slur_ink}
    failing = []
    for case, beats in CASES:
        path = out / case.name
        path.mkdir(parents=True, exist_ok=True)
        data, _engraving = fixture(case)
        xml = data.pop("xml")
        data["sample_beats"] = list(beats)
        (path/"input.musicxml").write_text(xml,encoding="utf-8")
        (path/"fixture.json").write_text(json.dumps(data))
        result = subprocess.run([
            godot,"--path",str(ROOT/"godot"),
            "--rendering-method","gl_compatibility",
            "--script",str(ROOT/"tests/godot/native_verovio_overlay.gd"),
            "--",str(path/"fixture.json"),str(path)
        ],capture_output=True,text=True,timeout=240)
        (path/"godot.log").write_text(result.stdout+result.stderr)
        if result.returncode or "NATIVE_VEROVIO_OVERLAY_FAILURES:0" not in result.stdout:
            raise RuntimeError(f"{case.name} Godot failed:\n"+(result.stdout+result.stderr)[-5000:])
        screenshots={float(b):path/f"native-{b:.2f}.png" for b in beats}
        if any(not p.is_file() for p in screenshots.values()):
            raise RuntimeError(f"{case.name}: missing a mandatory screenshot")
        original=(ROOT/case.filename).read_text(encoding="utf-8")
        proof=proofs[case.name](original,xml,path)
        (path/"symbol-proof.json").write_text(json.dumps(proof,indent=2)+chr(10))
        if not proof["passed"]:
            failing.append({"case":case.name,"errors":proof["errors"]})
        captured.append({"case":case.name,"path":str(path),
                         "beats":list(beats),"screenshots":len(screenshots),
                         "pixel_passed":proof["passed"]})
        print(f"Native {case.name}: {len(screenshots)} frames; "
              f"independent image proof={proof['passed']}",flush=True)
        for problem in proof["errors"]:
            print("FAIL",case.name,problem,flush=True)
    (out/"symbol-proof-summary.json").write_text(json.dumps(
        {"passed":not failing,"scores":captured,"errors":failing,
         "provenance":provenance,"provenance_after":current_provenance()},indent=2)+chr(10))
    if failing:
        raise AssertionError(f"Independent symbol image checks failed: {failing}")
    return captured

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    results=capture_all(args.out)
    (args.out/"capture-manifest.json").write_text(json.dumps(results,indent=2)+"\n")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
