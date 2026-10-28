"""Compose case preparation, transactional capture and independent proof execution."""
from __future__ import annotations
import json
from pathlib import Path
from PIL import Image
from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG

from . import capture_runner, capture_store, case_inputs, frame_evidence, proof_execution
from .capture_store import ROOT, CaptureProvenanceError
from .case_catalog import CASES
from .case_checkpoint import ignore_stage
from .case_types import AuditCase

def run(out: Path, godot: str, case: AuditCase = CASES[0],
        *, all_symbols: bool = False, strict: bool = True,
        reuse_captures: bool = False, prepared=None) -> dict:
    return execute_case(out, godot, case, all_symbols=all_symbols, strict=strict,
                     reuse_captures=reuse_captures, prepared=prepared,
                     record_stage=ignore_stage)


def execute_case(out: Path, godot: str, case: AuditCase,
              *, all_symbols: bool = False, strict: bool = True,
              reuse_captures: bool = False, prepared=None, record_stage) -> dict:
    out=out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    capture_store.recover_capture_publish(out)
    data, engraving = case_inputs.fixture(case) if prepared is None else prepared
    data = dict(data)
    if 'capture_config' in data and data['capture_config']!=CANONICAL_CAPTURE_CONFIG:
        raise CaptureProvenanceError('Capture configuration must explicitly select canonical audit mode')
    # run() owns the capture mode even for a caller supplying prepared assets.
    # This explicit field is sent to Godot and compared with retained fixtures.
    data['capture_config']=dict(CANONICAL_CAPTURE_CONFIG)
    model = data["model"]
    if all_symbols:
        # Every score symbol is positioned at the playhead in at least one
        # actual native frame. Every measure is also sampled even if silent.
        # No best-effort subset or fixed four-frame sampling is permitted.
        data["sample_beats"] = case_inputs.capture_clocks(data["xml"])
        data["phase3_full"] = True
        data["full_symbol_inventory"] = True
        if not data["sample_beats"]:
            raise AssertionError("Full-score witness has no sample clocks")
        if len({f"{at:.5f}" for at in data["sample_beats"]}) != len(data["sample_beats"]):
            raise AssertionError("Distinct source onsets would overwrite a screenshot filename")
    # Preserve the actual lesson MusicXML as the single reference score.
    xml=data.pop("xml")
    data = capture_runner.capture(out, godot, payload=data, xml=xml, pages=engraving.pages,
        root=ROOT, all_symbols=all_symbols, reuse_captures=reuse_captures,
        record_stage=record_stage)
    report = json.loads((out/"native-overlay-report.json").read_text())
    legacy_diagnostics = frame_evidence.readability_errors(model, report, case)
    # The older editorial audit uses renderer geometry and per-passage
    # readability budgets. Those are diagnostics, not independent evidence
    # that legitimate full-piece notation is incorrect.
    errors = list(data.get("source_errors", []))
    if not all_symbols:
        errors.extend(legacy_diagnostics)
    reference = Image.open(out/"verovio-0.png") if not all_symbols else None
    refnotes = engraving.layout["notes"]
    printed_ids = {n["id"] for n in model["notation_events"] if n["kind"] == "note"}
    reference_ids = {n["id"] for n in refnotes}
    if reference_ids != printed_ids:
        errors.append(f"{case.name}: Verovio/native note IDs differ: "
                      f"{len(reference_ids)} reference, {len(printed_ids)} native")
    checked = 0
    rendered_ids = set()
    registered_ids = set()
    active_pixel_samples = 0
    note_staff = {e["id"]:e["staff"] for e in model["notation_events"]
                  if e["kind"] == "note"}
    active_hand = model["active_hand"]

    def is_active(staff: str) -> bool:
        return active_hand == "both" or active_hand == staff

    for frame in report["frames"]:
        screenshot = Image.open(out/frame["file"])
        heads = frame["noteheads"]
        expected = frame.get("expected_noteheads", {})
        for ident, expected_x in expected.items():
            if ident not in heads:
                errors.append(f"{case.name}: Native omitted visible note {ident} "
                              f"at {frame['clock']:.3f}")
            elif abs(heads[ident][0] - expected_x) > 2.4 * report["staff_gap"]:
                errors.append(f"{case.name}: Printed onset drift for {ident} "
                              f"at {frame['clock']:.3f}")
        for ident, (x,y) in heads.items():
            if 20 < x < screenshot.width-20 and 20 < y < screenshot.height-20:
                rendered_ids.add(ident)
                checked += 1
                if is_active(note_staff.get(ident, "")):
                    active_pixel_samples += 1
                if is_active(note_staff.get(ident, "")) and frame_evidence.visible_ink(screenshot,x,y) < 5:
                    errors.append(f"Missing rendered native notehead {ident} "
                                  f"at beat {frame['clock']}")
        for rest in frame["rests"]:
            if (is_active(rest["hand"]) and
                    30 < rest["x"] < screenshot.width-30):
                if frame_evidence.visible_ink(screenshot,rest["x"],rest["y"],26) < 7:
                    errors.append("Missing native rest pixels: "+str(rest["id"]))
        # Hundreds of full-score frames do not require hundreds of mostly
        # redundant overlay PNGs. Phase 2 retains the full editorial overlays.
        if not all_symbols:
            frame["reference_notes_overlaid"] = frame_evidence.draw_overlay(
                reference.copy(),screenshot,refnotes,heads,
                out/f"overlay-{frame['clock']:.2f}.png")
        registered_ids.update(set(heads) & reference_ids)
    full_coverage = None
    if all_symbols:
        all_notes = {str(e["id"]) for e in model["notation_events"]
                     if e["kind"] == "note"}
        all_rests = {str(e["id"]) for e in model["notation_events"]
                     if e["kind"] == "rest"}
        registered_rests = {str(rest["id"]) for frame in report["frames"]
                            for rest in frame["rests"]}
        missed_notes = sorted(all_notes - rendered_ids)
        missed_rests = sorted(all_rests - registered_rests)
        unexpected_notes = sorted(rendered_ids - all_notes)
        unexpected_rests = sorted(registered_rests - all_rests)
        sampled_measures = set()
        for measure in model["measures"]:
            start = float(measure["start_beat"])
            if any(abs(float(frame["clock"]) - start) <= 0.0000001
                   for frame in report["frames"]):
                sampled_measures.add(int(measure["number"]))
        missed_measures = sorted(
            {int(m["number"]) for m in model["measures"]} - sampled_measures)
        full_coverage = {
            "measure_count": len(model["measures"]),
            "sampled_measures": len(sampled_measures),
            "source_noteheads": len(all_notes),
            "unique_rendered_noteheads": len(rendered_ids),
            "source_rests": len(all_rests),
            "unique_rendered_rests": len(registered_rests),
            "screenshot_count": len(report["frames"]),
            "missing_notes": missed_notes,
            "missing_rests": missed_rests,
            "missing_measure_starts": missed_measures,
            "unexpected_notes": unexpected_notes,
            "unexpected_rests": unexpected_rests,
            "witness_type": "Godot identity + per-note/rest ink proximity; "
                "not yet independent whole-piece symbol-classification",
        }
        if any((missed_notes, missed_rests, missed_measures,
                unexpected_notes, unexpected_rests)):
            errors.append(f"{case.name}: incomplete whole-window coverage: "
                          + json.dumps(full_coverage,sort_keys=True))
    if all_symbols:
        proof = proof_execution.execute_proofs(out, case, model=model,
            original_xml=data.get('original_xml', ''), record_stage=record_stage)
        errors.extend(proof.errors)
        full_coverage.update(proof.coverage)
    if checked == 0 and printed_ids:
        errors.append("No on-screen native noteheads were checked")
    active_written_notes = sum(
        1 for event in model["notation_events"]
        if event["kind"] == "note" and is_active(event["staff"]))
    if active_pixel_samples == 0 and active_written_notes:
        errors.append("No active-hand noteheads were pixel-verified")
    # A hand with no written notes is a valid silent practice mode, not
    # evidence of missing pixels. Its rests still require screenshot coverage.
    if not registered_ids and reference_ids:
        errors.append("Original Verovio identities never aligned with native frames")
    if rendered_ids - reference_ids:
        errors.append(f"Native rendered {len(rendered_ids-reference_ids)} "
                      "notes absent from Verovio")
    summary = {
        "source":f"{case.filename}, measures {case.first_bar}-{case.last_bar}, {case.hand}",
        "case":case.name,
        "density":report["density"],
        "density_witness":report.get("density_witness", {}),
        "native_notehead_samples":checked,
        "reference_source_note_count":len(refnotes),
        "distinct_native_noteheads":len(rendered_ids),
        "active_notehead_pixel_samples":active_pixel_samples,
        "registered_noteheads":len(registered_ids),
        "tiny_rests":sum(1 for n in model["notation_events"] if
                         n["kind"] == "rest" and n["note_type"] in
                         {"32nd","64th","128th"}),
        "maximum_dots":max((n["dots"] for n in model["notation_events"]
                            if n["kind"] == "note"), default=0),
        "rest_overlap_count":report["unavoidable_rest_overlaps"],
        "errors":errors,
        "passed":not errors,
        "legacy_renderer_diagnostics":legacy_diagnostics,
        "whole_window_coverage":full_coverage,
        "nonverified_symbols": proof.nonverified_symbols if all_symbols else {},
    }
    (out/"audit.json").write_text(json.dumps(summary,indent=2)+"\n")
    if errors and strict:
        raise AssertionError("\n".join(errors))
    return summary


def execute_job(job, *, record_stage):
    """One native/Verovio worker with an explicit per-case stage recorder."""
    case, source_phrase, variant, directory, godot, focused = (
        job[key] for key in ('case', 'source_phrase', 'variant', 'directory', 'godot', 'focused'))
    reuse_captures = job.get('reuse_captures', False)
    try:
        record_stage('prepare')
        if variant is not None:
            problems = case_inputs.variant_errors(source_phrase, variant)
            if problems:
                raise AssertionError("; ".join(problems))
        source_path = (ROOT / (case.filename if "/" in case.filename
                               else "midi/" + case.filename)).resolve()
        piece = case_inputs.load_piece(str(source_path))
        from piano_teacher.preprocessing_cache import PreprocessingCache
        cache = PreprocessingCache(directory.parent.parent/"cache")
        prepared = case_inputs.fixture(case, piece=piece,
                           phrase=variant.phrase if variant is not None else None, cache=cache)
        result=None
        if reuse_captures and (directory/'capture-manifest.json').is_file():
            try:
                result=execute_case(directory,godot,case,all_symbols=not focused,strict=False,
                           prepared=prepared,reuse_captures=True,record_stage=record_stage)
            except CaptureProvenanceError as exc:
                print(f'RECAPTURE {case.name}: {exc}',flush=True)
        if result is None:
            result=execute_case(directory,godot,case,all_symbols=not focused,strict=False,prepared=prepared,
                             record_stage=record_stage)
        # Successful PNGs are reusable evidence too. Keep them alongside the
        # exact-input manifest instead of recapturing every passing case.
        return {"errors": result["errors"][:25], "error_count": len(result["errors"]),
                "captured": True,
                "nonverified_symbols": result["nonverified_symbols"],
                "symbols": (result["whole_window_coverage"] or {}).get("symbols", {})}
    except Exception as exc:
        return {"errors": [f"{type(exc).__name__}: {exc}"], "error_count": 1,
                "captured": False, "symbols": {}}

