#!/usr/bin/env python3
"""Fail closed on incomplete independent evidence for the pinned 17 x 3 corpus.

Semantic and visual jobs have separate ledgers and artifacts. A passed detector
is not a complete notation audit: ambiguous/unsupported/unverified elements
remain blockers. This module uses only the standard library so that aggregation
still runs when renderer or semantic jobs fail to install their dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HANDS = ("both", "right", "left")
STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
# Freeze the index as well as the set: three jobs agreeing on the wrong source
# must not substitute for the source pinned at this index. Keep this independent
# of the rendering runner and its dependency imports.
PINNED_SOURCES = (
    "Ala_–_Joep_Beving.midi",
    "Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi",
    "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi",
    "Danny_Boy(Bill_Evans_Ver_).midi",
    "Merry-Go-Round-of-Life.midi",
    "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi",
    "Waltz_for_Debby.midi",
    "tests/fixtures/musical_fidelity/xml_pickup.musicxml",
    "tests/fixtures/musical_fidelity/xml_mixed_meter.musicxml",
    "tests/fixtures/musical_fidelity/xml_parallel_tied_voices.musicxml",
    "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml",
    "tests/fixtures/musical_fidelity/xml_keys_spelling.musicxml",
    "tests/fixtures/musical_fidelity/xml_crossed_named_hands.musicxml",
    "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml",
    "tests/fixtures/musical_fidelity/xml_trailing_rests.musicxml",
    "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml",
    "tests/fixtures/musical_fidelity/xml_long_multipage.musicxml",
)


def _count(value, *, minimum=0):
    """bool, float and coercible strings are not evidence counters."""
    return type(value) is int and value >= minimum


def _empty_coverage():
    return {"expected": 0, **dict.fromkeys(STATUSES, 0)}


def _source_inventory(path, boundary, hand, source):
    # These two inventory modules read ORIGINAL bytes using only stdlib. Do
    # not import an audit runner, application importer, image code or renderer.
    if boundary == "semantic":
        from piano_teacher.notation.semantic_contract import source_inventory
        return source_inventory(path)
    from piano_teacher.notation.visual_coverage import source_inventory
    xml = path.read_text(encoding="utf-8") if path.suffix == ".musicxml" else None
    return source_inventory(xml, hand, source_name=source)


def _account_inventory(data, required, errors, *, boundary, midi):
    """Restore omitted original constructs to the denominator as unverified.

    A producer may add evidence but cannot reduce the original inventory. A
    semantic MIDI reader can enrich unknown hand bindings; concrete original
    source fields and the boundary/construct must stay intact.
    """
    original = data.get("elements")
    elements = [dict(row) if isinstance(row, dict) else row for row in original] if isinstance(original, list) else []
    by_id = {}
    for position, row in enumerate(elements):
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            by_id.setdefault(row["id"], []).append(position)

    def projection_matches(row, expected):
        if row.get("construct") != expected["construct"]:
            return False
        if "boundary" in expected and row.get("boundary") != expected["boundary"]:
            return False
        source = row.get("source")
        return isinstance(source, dict) and all(
            value is None or source.get(key) == value
            for key, value in expected["source"].items())

    for expected in required:
        is_midi_sentinel = midi and expected["construct"] == "midi_written_transcription"
        if is_midi_sentinel and boundary == "visual":
            positions = [i for i, row in enumerate(elements) if isinstance(row, dict)
                         and row.get("construct") == "midi_written_transcription"]
        else:
            positions = by_id.get(expected["id"], [])
        if not positions:
            errors.append(f"Original source inventory missing {expected['construct']}: {expected['id']}")
            elements.append({**expected, "status": "unverified",
                             "reason": "Required original source inventory element omitted from report"})
            continue
        for position in positions:
            row = elements[position]
            if not projection_matches(row, expected):
                errors.append(f"Original source inventory binding changed: {expected['id']}")
                elements[position] = {**row, "reported_status": row.get("status"),
                                      "status": "unverified", "required_projection": expected,
                                      "reason": "Source inventory construct/boundary/identity does not match original"}
            if is_midi_sentinel and row.get("status") != "unsupported":
                errors.append("MIDI written transcription must remain unsupported; performance bytes do not specify a written score")
                elements[position] = {**elements[position], "reported_status": row.get("status"),
                                      "status": "unverified", "reason": "MIDI written transcription cannot be independently verified"}
    if boundary == "visual" and not midi:
        expected_ids = {row["id"] for row in required}
        for position, row in enumerate(elements):
            if (isinstance(row, dict) and isinstance(row.get("source"), dict)
                    and row["source"].get("origin") == "original"
                    and row.get("id") not in expected_ids):
                errors.append(f"Unexpected original source inventory element: {row.get('id')}")
                elements[position] = {**row, "reported_status": row.get("status"),
                                      "status": "unverified", "reason": "Element absent from pinned original inventory"}
    return {**data, "elements": elements}


def _ledger(data, errors, *, normalized=None):
    elements = data.get("elements")
    if not isinstance(elements, list) or not elements:
        errors.append("Missing/empty every-element ledger; pitch/rest counts alone do not verify notation")
        elements = []
    ids = Counter(row.get("id") for row in elements if isinstance(row, dict)
                  and isinstance(row.get("id"), str))
    counts = _empty_coverage()
    counts["expected"] = len(elements)
    unverified = []
    constructs = {}
    for position, raw in enumerate(elements):
        row = dict(raw) if isinstance(raw, dict) else {}
        valid = isinstance(raw, dict)
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(f"Element {position}: missing stable id")
            valid = False
        elif ids[identifier] != 1:
            errors.append(f"Element {identifier}: duplicated id")
            valid = False
        construct = row.get("construct")
        if not isinstance(construct, str) or not construct.strip():
            errors.append(f"Element {position}: missing construct")
            construct = "unknown"
            valid = False
        source = row.get("source")
        if not isinstance(source, dict) or not source:
            errors.append(f"Element {position}: missing source identity")
            valid = False
        status = row.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            errors.append(f"Element {position}: unknown status {status!r}")
            valid = False
        effective = status if valid else "unverified"
        counts[effective] += 1
        if normalized is not None:
            normalized.append({**row, "status": effective})
        construct_counts = constructs.setdefault(construct, _empty_coverage())
        construct_counts["expected"] += 1
        construct_counts[effective] += 1
        if effective != "verified":
            if status != effective:
                row["reported_status"] = status
            row.update(id=identifier if isinstance(identifier, str) else f"invalid:{position}",
                       construct=construct, status=effective)
            unverified.append(row)
    supplied = data.get("coverage")
    if not isinstance(supplied, dict):
        errors.append("Missing/malformed coverage counters")
        supplied = {}
    for key, expected in counts.items():
        actual = supplied.get(key)
        if not _count(actual) or actual != expected:
            errors.append(f"coverage.{key}: reported {actual!r}, ledger requires {expected}")
    for construct, values in constructs.items():
        for status in STATUSES[1:]:
            if values[status]:
                errors.append(f"Incomplete {construct}: {values[status]} {status} element(s)")
    actually_complete = bool(elements) and counts["verified"] == counts["expected"]
    if type(data.get("complete")) is not bool:
        errors.append("complete must be a boolean")
    elif data["complete"] != actually_complete:
        errors.append("complete flag disagrees with every-element statuses")
    if not actually_complete:
        errors.append("Complete verification blocked by missing or nonverified elements")
    return counts, unverified, constructs


def _visual(data, source, hand, scores, errors):
    if not _count(data.get("scores_total"), minimum=1) or data["scores_total"] != scores:
        errors.append("Wrong visual corpus denominator")
    if data.get("scores_attempted") != [source]:
        errors.append("Visual scores_attempted does not match the pinned source")
    if not _count(data.get("scores_passed")) or data["scores_passed"] != 1:
        errors.append("Visual score did not pass its evidence checks")
    if data.get("scores_failed") != []:
        errors.append("Visual scores_failed missing, malformed or nonempty")
    results = data.get("scores")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        errors.append("Missing/malformed single whole-score visual result")
        return
    result = results[0]
    if result.get("piece") != source or result.get("hand") != hand:
        errors.append("Whole-score source/mode does not match the pinned source")
    if result.get("passed") is not True:
        errors.append("Whole-score visual evidence checks failed")
    if result.get("visual_elements") != data.get("elements"):
        errors.append("Whole-score visual_elements disagree with canonical ledger")
    if result.get("visual_coverage") != data.get("coverage"):
        errors.append("Whole-score visual_coverage disagree with canonical counters")
    for key in ("missing_measures", "duplicated_measures", "unexpected_measures"):
        if result.get(key) != []:
            errors.append(f"Whole-score {key} missing, malformed or nonempty")
    bars = result.get("measures_expected")
    if not _count(bars, minimum=1):
        errors.append("measures_expected must be a positive integer")
        bars = None
    witnessed = result.get("measures_witnessed")
    if not _count(witnessed, minimum=1) or witnessed != bars:
        errors.append("Incomplete/invalid measures_witnessed")
    windows = result.get("windows")
    if not isinstance(windows, list) or not windows:
        errors.append("No actual visual window evidence")
        return
    intervals = []
    window_elements = []
    totals = {"source_noteheads": 0, "source_rests": 0, "screenshot_count": 0}
    for position, window in enumerate(windows):
        prefix = f"window {position}"
        if not isinstance(window, dict):
            errors.append(f"{prefix}: malformed window object")
            continue
        first, last = window.get("first_bar"), window.get("last_bar")
        valid_range = (_count(first, minimum=1) and _count(last, minimum=1)
                       and first <= last and bars is not None and last <= bars)
        if not valid_range:
            errors.append(f"{prefix}: invalid measure window {first!r}-{last!r}")
        else:
            intervals.append((first, last))
            prefix = f"window {first}-{last}"
        elements = window.get("visual_elements")
        if not isinstance(elements, list) or not elements:
            errors.append(f"{prefix}: missing/empty window visual ledger")
            elements = []
        window_elements.extend(elements)
        for row in elements:
            if not isinstance(row, dict) or not isinstance(row.get("source"), dict):
                errors.append(f"{prefix}: malformed window element/source binding")
                continue
            binding = row["source"]
            measure = binding.get("measure_index")
            if (binding.get("origin") == "original" and valid_range
                    and (not _count(measure, minimum=1) or not first <= measure <= last)):
                errors.append(f"{prefix}: original source element is outside its measure window")
        witness = window.get("whole_window_coverage")
        if not isinstance(witness, dict) or not witness:
            errors.append(f"{prefix}: missing/malformed actual screenshot witness")
            continue
        if witness.get("elements") != elements:
            errors.append(f"{prefix}: screenshot witness elements disagree with window ledger")
        for key in ("missing_notes", "missing_rests", "missing_measure_starts",
                    "unexpected_notes", "unexpected_rests"):
            if witness.get(key) != []:
                errors.append(f"{prefix}: {key} missing, malformed or nonempty")
        values = {}
        for key in ("measure_count", "sampled_measures", "screenshot_count",
                    "source_noteheads", "unique_rendered_noteheads",
                    "source_rests", "unique_rendered_rests"):
            value = witness.get(key)
            minimum = 1 if key in ("measure_count", "sampled_measures", "screenshot_count") else 0
            if not _count(value, minimum=minimum):
                errors.append(f"{prefix}: invalid/missing {key}")
            else:
                values[key] = value
                if key in totals:
                    totals[key] += value
        length = last - first + 1 if valid_range else None
        if values.get("measure_count") != length or values.get("sampled_measures") != length:
            errors.append(f"{prefix}: counters do not cover the actual measure window")
        if (length is not None and "screenshot_count" in values
                and values["screenshot_count"] < length):
            errors.append(f"{prefix}: too few actual screenshots for the measures")
        for source_key, rendered_key in (("source_noteheads", "unique_rendered_noteheads"),
                                         ("source_rests", "unique_rendered_rests")):
            if source_key in values and rendered_key in values and values[source_key] != values[rendered_key]:
                errors.append(f"{prefix}: incomplete {source_key} screenshot/identity coverage")
        for proof_key, expected_key, verified_key, source_key in (
                ("independent_image_pitch", "written_active_noteheads", "image_pitch_verified", "source_noteheads"),
                ("independent_image_rests", "written_active_rests", "image_rest_glyphs_verified", "source_rests")):
            proof = witness.get(proof_key)
            if not isinstance(proof, dict) or not proof:
                errors.append(f"{prefix}: missing/malformed {proof_key} evidence")
                continue
            if proof.get("passed") is not True:
                errors.append(f"{prefix}: {proof_key} evidence checks did not pass")
            if proof.get("failures") != []:
                errors.append(f"{prefix}: {proof_key} failures missing, malformed or nonempty")
            expected, verified = proof.get(expected_key), proof.get(verified_key)
            if not _count(expected) or not _count(verified):
                errors.append(f"{prefix}: invalid/missing {proof_key} counters")
            else:
                if verified != expected:
                    errors.append(f"{prefix}: incomplete {proof_key} verification {verified}/{expected}")
                if source_key in values and expected > values[source_key]:
                    errors.append(f"{prefix}: {proof_key} exceeds written source inventory")
                if hand == "both" and source_key in values and expected != values[source_key]:
                    errors.append(f"{prefix}: {proof_key} does not cover all written source elements")
                construct = "pitch" if proof_key == "independent_image_pitch" else "rest"
                active = sum(1 for row in elements if isinstance(row, dict)
                             and row.get("construct") == construct
                             and isinstance(row.get("source"), dict)
                             and row["source"].get("origin") in ("original", "generated")
                             and (hand == "both" or row["source"].get("staff") == hand))
                if expected != active:
                    errors.append(f"{prefix}: {proof_key} count does not cover active-hand source inventory ({expected}/{active})")
            for key in ("intrinsically_indistinguishable_half_whole", "ambiguous", "unsupported", "unverified", "mismatch"):
                if key in proof and (not _count(proof[key]) or proof[key] != 0):
                    errors.append(f"{prefix}: {proof_key} incomplete/ambiguous {key}={proof[key]!r}")
            if "complete" in proof and proof["complete"] is not True:
                errors.append(f"{prefix}: {proof_key} explicitly incomplete")
    if window_elements != data.get("elements"):
        errors.append("Flattened window visual ledgers disagree with canonical elements")
    # Check the interval partition without expanding attacker-controlled bar
    # numbers into a huge range. Any overlap, duplicate or gap is a blocker.
    next_bar = 1
    for first, last in sorted(intervals):
        if first != next_bar:
            errors.append(f"Invalid measure windows: missing/duplicated coverage before {first}-{last}")
        next_bar = max(next_bar, last + 1)
    if bars is not None and next_bar != bars + 1:
        errors.append(f"Invalid measure windows: missing coverage through measure {bars}")
    for key, witness_key in (("notes_image_proximity_witnessed", "source_noteheads"),
                              ("rests_image_proximity_witnessed", "source_rests"),
                              ("native_frames_checked", "screenshot_count")):
        value = result.get(key)
        if not _count(value) or value != totals[witness_key]:
            errors.append(f"{key}: reported {value!r}, windows require {totals[witness_key]}")


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError(f"Nonfinite JSON value: {value}")


def aggregate(folder: Path, *, scores: int = 17, kind: str = "complete", include_elements: bool = False,
              required_provenance: dict | None = None) -> dict:
    """Require every pinned case, with independently recomputed status totals.

    ``scores`` selects a pinned prefix for small regression fixtures only; the
    CLI always requires all 17. Each boundary has its own 51-job denominator.
    ``passed`` here is the complete corpus gate, not a detector's narrower flag.
    """
    errors = []
    jobs = []
    totals = _empty_coverage()
    unverified = []
    constructs = {}
    sources_found = set()
    present = 0
    kinds = ("semantic", "visual") if kind == "complete" else (kind,)
    if kind not in ("complete", "semantic", "visual"):
        errors.append(f"Unknown verification kind {kind!r}")
        kinds = ()
    if not _count(scores, minimum=1) or scores > len(PINNED_SOURCES):
        errors.append("Invalid pinned corpus denominator")
        scores = 0
    for index, source in enumerate(PINNED_SOURCES[:scores]):
        source_file = ROOT / (source if "/" in source else "midi/" + source)
        try:
            digest = sha256(source_file.read_bytes()).hexdigest()
        except OSError as exc:
            digest = None
            errors.append(f"Unreadable pinned source {index}: {exc}")
        for boundary in kinds:
            inventory_cache = {}
            for hand in HANDS:
                label = f"{boundary} {index}/{hand}"
                prefix = "phase3-semantic-report" if boundary == "semantic" else "phase3-report"
                item = folder / f"{prefix}-{index}-{hand}" / "summary.json"
                job = {"verification_kind": boundary, "source_index": index,
                       "source": source, "hand": hand, "status": "missing",
                       "complete": False, "coverage": _empty_coverage(), "errors": []}
                jobs.append(job)
                job_errors = job["errors"]
                report_error_status = None
                try:
                    data = json.loads(item.read_text(encoding="utf-8"),
                                      object_pairs_hook=_json_object,
                                      parse_constant=_invalid_constant)
                except (OSError, ValueError, RecursionError) as exc:
                    job_errors.append(f"Missing/unreadable required report: {exc}")
                    report_error_status = "missing"
                    data = {}
                else:
                    present += 1
                if not isinstance(data, dict):
                    job_errors.append("Malformed report: expected JSON object")
                    report_error_status = "invalid"
                    data = {}
                # The pinned source inventory is required even when no usable
                # report survived. Keep these jobs in every element denominator
                # and restore their exact original constructs as unverified.
                identity_ok = (type(data.get("source_index")) is int
                               and data["source_index"] == index and data.get("source") == source)
                if not identity_ok:
                    job_errors.append("Wrong pinned source/index")
                if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
                    job_errors.append("Missing/unsupported schema_version")
                if data.get("verification_kind") != boundary or data.get("hand") != hand:
                    job_errors.append("Wrong verification kind/hand mode")
                if digest is None or data.get("source_sha256") != digest:
                    job_errors.append("Missing/wrong original source_sha256")
                elif identity_ok:
                    sources_found.add(source)
                if data.get("passed") is not True:
                    job_errors.append("Evidence checks failed or passed is not boolean true")
                for key in ("errors", "failures", "runtime_errors"):
                    if key in data and data[key] != []:
                        job_errors.append(f"Report contains {key}: {data[key]!r}")
                cache_key = "all" if boundary == "semantic" else hand
                try:
                    if cache_key not in inventory_cache:
                        inventory_cache[cache_key] = _source_inventory(source_file, boundary, hand, source)
                    required = inventory_cache[cache_key]
                except Exception as exc:
                    # A bad original or unavailable inventory checker must
                    # leave a diagnostic artifact, never abort aggregation.
                    job_errors.append(f"Unreadable original source inventory: {type(exc).__name__}: {exc}")
                    required = [{"id": "missing-source-inventory", "construct": "source_inventory",
                                 "source": {"id": source}, "status": "unverified"}]
                accounted = _account_inventory(data, required, job_errors,
                    boundary=boundary, midi=source_file.suffix.lower() in (".mid", ".midi"))
                trusted_identity = (identity_ok and digest is not None and data.get("source_sha256") == digest
                                    and type(data.get("schema_version")) is int and data["schema_version"] == 1
                                    and data.get("verification_kind") == boundary and data.get("hand") == hand)
                if required_provenance is not None and data.get("provenance") != required_provenance:
                    job_errors.append("Report provenance differs from required immutable release inputs")
                    trusted_identity = False
                if not trusted_identity:
                    accounted["elements"] = [
                        {**row, "reported_status": row["status"], "status": "unverified",
                         "reason": "Report provenance does not match the pinned source, schema and hand"}
                        if isinstance(row, dict) and row.get("status") == "verified" else row
                        for row in accounted["elements"]]
                normalized = [] if include_elements else None
                coverage, gaps, per_construct = _ledger(accounted, job_errors, normalized=normalized)
                if include_elements:
                    job["elements"] = normalized
                job["coverage"] = coverage
                for key, value in coverage.items():
                    totals[key] += value
                for construct, counts in per_construct.items():
                    at = constructs.setdefault(boundary, {}).setdefault(construct, _empty_coverage())
                    for key, value in counts.items():
                        at[key] += value
                unverified.extend({**row, "verification_kind": boundary, "source_index": index,
                                   "score_source": source, "hand": hand} for row in gaps)
                if boundary == "visual":
                    _visual(data, source, hand, scores, job_errors)
                job.update(status=report_error_status or ("blocked" if job_errors else "verified"), complete=not job_errors,
                           reported_passed=data.get("passed"), reported_complete=data.get("complete"))
                errors.extend(f"{label}: {error}" for error in job_errors)
    complete = not errors and bool(jobs)
    return {
        "schema_version": 1, "verification_kind": kind,
        "passed": complete, "complete": complete,
        "status": "complete" if complete else "blocked",
        "expected_scores": scores, "expected_modes": list(HANDS),
        "required_jobs": scores * len(HANDS) * len(kinds),
        "jobs_with_results": present,
        "jobs_verified": sum(job["complete"] for job in jobs),
        "unique_sources": len(sources_found), "coverage": totals,
        "construct_coverage": constructs, "unverified_elements": unverified,
        "jobs": jobs, "errors": errors,
        "coverage_claim": "Complete only when every pinned source and hand has all expected "
            "elements independently verified at each requested boundary. Native presence and "
            "pitch/rest checks alone do not establish whole visual notation coverage. "
            "Every ambiguous, unsupported, unverified or mismatched construct blocks completion.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kind", choices=("semantic", "visual", "complete"), default="complete")
    args = parser.parse_args()
    result = aggregate(args.root, kind=args.kind)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Phase 3 {args.kind}: {result['status']}; "
          f"{result['jobs_verified']}/{result['required_jobs']} complete jobs, "
          f"{result['jobs_with_results']} reports; "
          f"{result['coverage']['verified']}/{result['coverage']['expected']} verified elements")
    for error in result["errors"]:
        print("BLOCKED", error)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
