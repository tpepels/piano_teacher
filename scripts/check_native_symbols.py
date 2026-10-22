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
from check_native_verovio_overlay import AuditCase, ROOT, fixture

CASES = (
    (AuditCase("written-rests", "tests/fixtures/native_pixel_rest_probe.musicxml",
               1, 4, "both"), (0, 2, 4, 5, 8, 11, 12)),
    (AuditCase("written-accidentals", "tests/fixtures/native_pixel_accidental_probe.musicxml",
               1, 2, "both"), tuple(range(8))),
    (AuditCase("source-beams", "tests/fixtures/native_pixel_beam_probe.musicxml",
               1, 2, "both"), (0.25,0.75,1.25,1.75,2.25,2.75,3.25,3.75)),
    (AuditCase("source-ties", "tests/fixtures/native_pixel_tie_probe.musicxml",
               1, 2, "both"), (0,1,2,3,4)),
)

def capture_all(out: Path, godot: str | None = None) -> list[dict]:
    godot = godot or shutil.which("godot") or shutil.which("godot4")
    if not godot:
        raise RuntimeError("Actual native Godot is required")
    captured = []
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
        captured.append({"case":case.name,"path":str(path),
                         "beats":list(beats),"screenshots":len(screenshots)})
        print(f"Native captured {case.name}: {len(screenshots)} frames",flush=True)
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
