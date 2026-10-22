"""Replay Phase 2's existing image oracles without rendering or new tolerances."""
from hashlib import sha256
import json
from pathlib import Path


def validate_prior_notation(path, revision, provenance):
    from scripts.audit_native_release import read_json
    errors, checks, files = [], [], []
    if path is None:
        return {"complete": False, "errors": ["Missing Phase 2 actual-rendering prerequisite evidence"], "checks": []}
    path = Path(path)
    try:
        data = read_json(path)
        if (type(data.get("schema_version")) is not int or data["schema_version"] != 1
                or data.get("revision") != revision or data.get("phase2") != {"result": "success", "revision": revision}):
            raise ValueError("Phase 2 workflow failed, missing or belongs to a different revision")
        from scripts.check_native_pixels import PROBES, BEATS
        from scripts.check_native_symbols import CASES
        from piano_teacher.notation.pixel_proof import verify_pixel_frames
        from piano_teacher.notation import symbol_pixel_proof as symbols
        from scripts.check_native_verovio_overlay import ROOT
        for dirname, summary in (("phase2-native-pixel-proof", "summary.json"),
                                 ("phase2-symbol-specimens", "symbol-proof-summary.json")):
            root = path.parent / dirname
            result = read_json(root / summary)
            if (result.get("passed") is not True or provenance.get("clean") is not True
                    or result.get("provenance") != provenance or result.get("provenance_after") != provenance):
                raise ValueError(f"{dirname}: failed/missing/stale actual rendering provenance")
        root = path.parent / "phase2-native-pixel-proof"
        summary = read_json(root / "summary.json")
        if (type(summary.get("probes")) is not int or summary["probes"] != len(PROBES)
                or sorted(r.get("name") for r in summary.get("results", [])) != sorted(p.name for p in PROBES)):
            raise ValueError("Phase 2 missing/duplicate pitch/chord probe inventory")
        for probe in PROBES:
            folder = root / probe.name
            frames = {b: folder / f"native-{b:.2f}.png" for b in BEATS}
            if {p.name for p in folder.glob("native-*.png")} != {p.name for p in frames.values()}:
                raise ValueError(f"{probe.name}: missing or unexpected native frames")
            source = ROOT / probe.filename
            result = verify_pixel_frames(source.read_text(), frames)
            stored = read_json(folder / "pixel-proof-report.json")
            if result.get("passed") is not True or stored != json.loads(json.dumps({**result, "name": probe.name})):
                raise ValueError(f"{probe.name}: stored and independently replayed pixel evidence disagree")
            checks.append({"name": probe.name, "passed": True, "source_sha256": sha256(source.read_bytes()).hexdigest()})
        functions = dict(zip(("written-rests", "written-accidentals", "source-beams", "source-ties", "written-rhythms", "source-slur"),
                             (symbols.prove_rest_ink, symbols.prove_accidental_ink, symbols.prove_beam_ink,
                              symbols.prove_tie_ink, symbols.prove_note_rhythm_ink, symbols.prove_slur_ink)))
        root = path.parent / "phase2-symbol-specimens"
        summary = read_json(root / "symbol-proof-summary.json")
        names = [r.get("case") for r in summary.get("scores", [])]
        if sorted(names) != sorted(functions) or summary.get("errors") != []:
            raise ValueError("Phase 2 missing/duplicate/failed symbol probe inventory")
        for case, beats in CASES:
            folder = root / case.name
            expected = {f"native-{float(b):.2f}.png" for b in beats}
            if {p.name for p in folder.glob("native-*.png")} != expected:
                raise ValueError(f"{case.name}: missing or unexpected native frames")
            source = ROOT / case.filename
            result = functions[case.name](source.read_text(), (folder / "input.musicxml").read_text(), folder)
            stored = read_json(folder / "symbol-proof.json")
            if result.get("passed") is not True or stored != json.loads(json.dumps(result)):
                raise ValueError(f"{case.name}: stored and independently replayed symbol evidence disagree")
            checks.append({"name": case.name, "passed": True, "source_sha256": sha256(source.read_bytes()).hexdigest()})
        for file in sorted(path.parent.rglob("*")):
            if file.is_file():
                files.append({"path": file.relative_to(path.parent).as_posix(), "sha256": sha256(file.read_bytes()).hexdigest()})
    except Exception as exc:
        # Artifact corruption and oracle/runtime errors must preserve a blocked
        # decision, never interrupt the consolidated diagnostic report.
        errors.append(f"Phase 2 actual rendering: {type(exc).__name__}: {exc}")
    return {"complete": not errors, "errors": errors, "checks": checks, "files": files}
