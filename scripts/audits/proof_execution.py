"""Ordered independent source/pixel proofs and strict evidence publication."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path

from .case_checkpoint import ignore_stage
from .case_types import AuditCase

def feature_evidence_errors(report: dict) -> list[str]:
    """Inspect each observation; aggregate pass flags never authorize a glyph."""
    errors = []
    for row in report.get("measured", []):
        for feature, observation in row.get("features", {}).items():
            if observation.get("status") != "verified":
                errors.append(f"measure {row.get('measure')} {row.get('staff')} "
                              f"voice {row.get('voice')} {row.get('source_id')} "
                              f"{feature}: {observation.get('status', 'unverified')} "
                              f"{observation.get('reason', 'no independent pixel evidence')}")
    if not report.get("complete", False) and not errors:
        errors.append("Incomplete note-feature pixel accounting")
    return errors


def absence_evidence_errors(report: dict) -> list[str]:
    """Reject observed extra glyphs and missing capture evidence.

    The independent detector deliberately does NOT claim global absence of
    extra ink: headers, antialiasing and crossing glyphs leave residual pixels.
    Those pixels remain explicitly unverified in its evidence, not positive
    proof of invented notes or a reason every valid score must fail.
    """
    rows = [row for row in report.get('measured', []) if row.get('region') == 'viewport']
    errors = [f"Unexpected-symbol check {row.get('frame')} beat {row.get('clock')}: "
              f"{row.get('reason', 'unexpected glyph')}"
              for row in rows if row.get('status') == 'mismatch']
    coverage = report.get('coverage', {})
    if not rows:
        errors.append('No framebuffer observations for unexpected symbols')
    if any(row.get('status') not in ('verified', 'unverified', 'mismatch')
           for row in rows):
        errors.append('Unexpected-symbol detector returned an invalid status')
    if any('evidence' not in row for row in rows):
        errors.append('Unexpected-symbol observation has no pixel evidence')
    if coverage.get('measured_frames') != coverage.get('frames') or not coverage.get('frames'):
        errors.append('Incomplete actual framebuffer capture for unexpected symbols')
    if not coverage.get('initial_viewport') or not coverage.get('terminal_viewport'):
        errors.append('Missing opening or ending framebuffer coverage')
    if coverage.get('motion_status') != 'verified':
        errors.append('Unverified movement between sampled source positions')
    if (coverage.get('clock_gaps') or coverage.get('motion_errors')
            or coverage.get('missing_source_clocks') or coverage.get('binding_errors')):
        errors.append('Incomplete source clock or glyph tracking evidence')
    for kind in ('heads', 'rests'):
        if (not isinstance(coverage.get('expected_'+kind), int)
                or coverage.get('bound_'+kind) != coverage['expected_'+kind]):
            errors.append(f'Incomplete independent {kind} ownership')
    # Residual pixels and unresolved overprinting remain in the returned
    # evidence as unverified. Never turn them into an all-clear assertion.
    return errors


def symbol_error(row: dict) -> str:
    source = row.get("source", {})
    return (f"measure {source.get('measure')} {source.get('staff')} "
            f"voice {source.get('voice')} {source.get('id')} {row['construct']}: "
            f"{row['status']} {row.get('reason', row.get('differences', 'no independent evidence'))}")



@dataclass(frozen=True)
class ProofResult:
    errors: list[str]
    coverage: dict
    nonverified_symbols: dict


def execute_proofs(out: Path, case: AuditCase, *, model: dict, original_xml: str = "",
                   record_stage=ignore_stage) -> ProofResult:
    errors = []
    full_coverage = {}
    # Unlike the legacy overlay, this check reads the WRITTEN pitches
    # from MusicXML, then extracts staff lines and notehead positions
    # directly from PNG pixels. No Godot head/staff Y is permitted.
    from piano_teacher.notation.phase3_pixels import (
        verify_all_notehead_pixels, verify_all_rest_pixels, verify_scroll_pixels)
    engraving_xml=(out/"score.musicxml").read_text(encoding="utf-8")
    record_stage('noteheads')
    independent = verify_all_notehead_pixels(
        engraving_xml,out,hand=case.hand)
    record_stage('rests')
    rests_independent = verify_all_rest_pixels(
        engraving_xml,out,hand=case.hand)
    record_stage('scroll')
    motion = verify_scroll_pixels(engraving_xml, out)
    (out/"independent-motion.json").write_text(json.dumps(motion,indent=2)+"\n")
    for row in motion["measured"]:
        if not row["passed"]:
            errors.append(f"measure transition at beat {row['clock']}: "
                          f"{row['reason']} {row.get('pixel_steps', [])}")
    full_coverage["independent_motion"] = motion
    full_coverage["independent_image_rests"] = {
        key:value for key,value in rests_independent.items()
        if key!="measured"
    }
    (out/"independent-rests.json").write_text(
        json.dumps(rests_independent,indent=2)+"\n")
    if not rests_independent["passed"]:
        errors.extend(f"Independent rest glyph: {message}"
                      for message in rests_independent["failures"][:30])
        if len(rests_independent["failures"])>30:
            errors.append(f"And {len(rests_independent['failures'])-30} "
                          "more rest image failures (see independent-rests.json)")
    full_coverage["independent_image_pitch"] = {
        key:value for key,value in independent.items() if key!="measured"
    }
    (out/"independent-pixels.json").write_text(
        json.dumps(independent,indent=2)+"\n")
    if not independent["passed"]:
        errors.extend(f"Independent native pixel check: {message}"
                      for message in independent["failures"][:30])
        if len(independent["failures"])>30:
            errors.append(f"And {len(independent['failures'])-30} more independent "
                          "pixel errors (see independent-pixels.json)")
    # A detector's 'passed' means no established mismatch. It must not
    # turn an ambiguous or unavailable symbol witness into a visual pass.
    for kind, proof in (("notehead", independent), ("rest", rests_independent)):
        for row in proof.get("measured", []):
            if row.get("status") != "verified":
                errors.append(f"measure {row.get('measure')} {row.get('staff')} "
                              f"voice {row.get('voice')} {row.get('source_id')} "
                              f"{kind}: {row.get('status', 'unverified')} "
                              f"{row.get('reason', 'incomplete independent image evidence')}")
    from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels
    from piano_teacher.notation.connector_pixels import verify_beam_pixels, verify_tuplet_pixels
    record_stage('ties-and-slurs')
    connectors=verify_connector_pixels(engraving_xml,out,hand=case.hand)
    record_stage('beams')
    beams=verify_beam_pixels(engraving_xml,out,hand=case.hand)
    record_stage('tuplets')
    tuplets=verify_tuplet_pixels(engraving_xml,out,hand=case.hand)
    by_id={event['id']:event for event in model['notation_events']}
    for label,proof in (('connectors',connectors),('beams',beams),('tuplets',tuplets)):
        (out/f'independent-{label}.json').write_text(json.dumps(proof,indent=2)+'\n')
        full_coverage[f'independent_{label}']=proof['coverage']
        for observation in proof.get('observations',proof.get('measured',[])):
            if observation.get('graphical',True) and observation['status']!='verified':
                ids=observation.get('event_ids',observation.get('source_ids',[]))
                source=next((by_id[identity] for identity in ids if identity in by_id),observation)
                errors.append(symbol_error(dict(construct=observation['construct'],
                    source=dict(source,id='|'.join(str(i) for i in ids)),status=observation['status'],
                    reason=observation.get('reason') or observation.get('evidence',{}).get('reason','No independent connector evidence'))))
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels, verify_structure_pixels, verify_ledger_pixels
    record_stage('note-features')
    features = verify_note_feature_pixels(engraving_xml, out, hand=case.hand)
    record_stage('ledger-lines')
    ledgers=verify_ledger_pixels(engraving_xml,out,hand=case.hand)
    (out/'independent-ledgers.json').write_text(json.dumps(ledgers,indent=2)+'\n')
    errors.extend(feature_evidence_errors(ledgers))
    full_coverage['independent_ledgers']=ledgers['coverage']
    (out/"independent-features.json").write_text(json.dumps(features,indent=2)+"\n")
    errors.extend(feature_evidence_errors(features))
    full_coverage["independent_note_features"] = features["coverage"]
    from piano_teacher.notation.semantic_contract import verify_generated_contract
    record_stage('semantics')
    semantics = verify_generated_contract(engraving_xml, model)
    (out/"semantics.json").write_text(json.dumps(semantics,indent=2)+"\n")
    for row in semantics["elements"]:
        if row["status"] != "verified":
            errors.append("Generated/native " + symbol_error(row))
    from piano_teacher.notation.visual_coverage import visual_elements, coverage_counts
    elements = visual_elements(original_xml or None,
        engraving_xml, independent, rests_independent, hand=case.hand,
        first_bar=case.first_bar, last_bar=case.last_bar,
        source_name=case.filename, feature_report=features,connector_report=connectors,
        beam_report=beams,tuplet_report=tuplets,ledger_report=ledgers,
        semantic_report=semantics)
    record_stage('structure')
    structures = verify_structure_pixels(engraving_xml, out, elements,
                                          hand=case.hand, first_bar=case.first_bar)
    structural = {row["id"]: row for row in structures}
    for row in elements:
        if row["id"] in structural and row["status"] != "mismatch":
            observation = structural[row["id"]]
            row.update({key: observation[key] for key in ("status", "reason", "evidence")})
    (out/"independent-structure.json").write_text(json.dumps(structures,indent=2)+"\n")
    # MIDI has no unique authored spelling. That is an interpretation
    # limit, separate from checking every symbol of its chosen score.
    required = [row for row in elements if row["construct"] != "midi_written_transcription"]
    (out/"independent-symbols.json").write_text(json.dumps(elements,indent=2)+"\n")
    full_coverage["symbols"] = coverage_counts(required)
    for row in required:
        if row["status"] != "verified":
            errors.append(symbol_error(row))
    from piano_teacher.notation.extra_symbol_pixels import verify_extra_symbol_pixels
    record_stage('unexpected-symbols')
    absence = verify_extra_symbol_pixels(engraving_xml, out, hand=case.hand)
    (out/'independent-unexpected-symbols.json').write_text(json.dumps(absence,indent=2)+'\n')
    full_coverage['unexpected_symbols'] = absence['coverage']
    errors.extend(absence_evidence_errors(absence))
    return ProofResult(errors, full_coverage, dict(Counter(
        f"{row['construct']}:{row['status']}" for row in required
        if row['status'] != 'verified')))
