"""Release dispositions preserve verification statuses and source limitations.

This policy cannot certify pixels or transcription. Every visual construct is
required by default. Only precisely bound MIDI authorial limitations may be
nonblocking, and only with complete independent interpretation-rule evidence.
Inventory, provenance and artifact validation remain separate required gates.
"""
from __future__ import annotations

from pathlib import Path
import re

POLICY_VERSION = "native-notation-release-v2"
STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
_WRITTEN_UNSPECIFIED = frozenset({"written_notes", "written_rests", "voices", "ties",
    "beams", "tuplets", "measure_structure", "pedal_sounding_duration"})


def _counts():
    return dict.fromkeys(("expected", *STATUSES), 0)


def _add(counts, status):
    counts["expected"] += 1
    counts[status] += 1


def _midi_rule_contract():
    try:
        from .midi_transcription_rules import RULE_VERSION, REQUIRED_RULES
        return RULE_VERSION, REQUIRED_RULES
    except ImportError:
        return None, ()


def valid_midi_rule_evidence(row):
    """Validate the current rule inventory, never a producer's boolean alone."""
    version, required = _midi_rule_contract()
    if not version or not isinstance(required, tuple) or not required or len(set(required)) != len(required):
        return False
    if not isinstance(row, dict) or row.get("status") != "verified":
        return False
    evidence = row.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("rule_version") != version:
        return False
    report = evidence.get("rule_report")
    if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
            or report["schema_version"] != 1 or report.get("rule_version") != version
            or report.get("passed") is not True or report.get("complete") is not True):
        return False
    rules = report.get("rules")
    if not isinstance(rules, dict) or set(rules) != set(required):
        return False
    for value in rules.values():
        if (not isinstance(value, dict) or value.get("status") != "verified"
                or not isinstance(value.get("evidence"), dict) or not value["evidence"]):
            return False
    for name in ("discrepancies", "errors", "failures"):
        if name in report and report[name] != []:
            return False
    for name in ("expected", "verified"):
        if name in report and (type(report[name]) is not int or report[name] != len(required)):
            return False
    return True


def _key(job):
    return job.get("source_index"), job.get("source"), job.get("hand")


def _is_midi(job):
    return isinstance(job.get("source"), str) and Path(job["source"]).suffix.lower() in {".mid", ".midi"}


def _valid_job(job):
    return (isinstance(job, dict) and job.get("verification_kind") in ("semantic", "visual")
            and type(job.get("source_index")) is int and job["source_index"] >= 0
            and isinstance(job.get("source"), str) and bool(job["source"])
            and job.get("hand") in ("right", "left", "both")
            and isinstance(job.get("elements"), list) and bool(job["elements"]))


def _valid_row(row):
    return (isinstance(row, dict) and isinstance(row.get("id"), str) and bool(row["id"])
            and isinstance(row.get("construct"), str) and bool(row["construct"])
            and row.get("status") in STATUSES and isinstance(row.get("source"), dict)
            and isinstance(row["source"].get("id"), str) and bool(row["source"]["id"]))


def _rule_rows(job):
    return [row for row in job.get("elements", []) if isinstance(row, dict)
            and row.get("construct") == "midi_transcription_rules"
            and row.get("boundary") == "original->written"
            and isinstance(row.get("source"), dict)
            and row["source"].get("id") == "midi:transcription-rules"]


def _limitation_code(job, row):
    if not _is_midi(job) or row.get("status") not in {"ambiguous", "unsupported"}:
        return None
    source = row.get("source", {})
    if not isinstance(source, dict):
        return None
    construct, identity = row.get("construct"), source.get("id")
    boundary = row.get("boundary")
    if job.get("verification_kind") == "semantic":
        if boundary == "original->written":
            if construct == "midi_written_transcription" and identity == "midi:written-transcription":
                return "midi_authorial_notation_unspecified"
            if construct in _WRITTEN_UNSPECIFIED and identity == f"midi:unspecified:{construct}":
                return ("physical_release_not_pedal_sounding_duration" if construct == "pedal_sounding_duration"
                        else "midi_authorial_notation_unspecified")
        if boundary == "original->native" and row.get("status") == "ambiguous" and isinstance(identity, str):
            if construct == "source_hand_assignment" and re.fullmatch(r"midi-t\d+", identity):
                return "midi_authorial_hand_unspecified"
            if construct == "midi_note_pairing" and re.fullmatch(r"midi-t\d+-e\d+", identity):
                return "midi_overlap_pairing_not_unique"
    elif (job.get("verification_kind") == "visual" and construct == "midi_written_transcription"
          and identity == "midi-written-transcription" and source.get("origin") == "midi"
          and source.get("source_name") in {job["source"], Path(job["source"]).name}):
        return "midi_authorial_notation_unspecified"
    return None


def assess_jobs(jobs):
    """Assess supported scope without changing or discarding ledger statuses.

    The caller must also require complete original inventory, schema, capture,
    source/hand/hash provenance and mutation/artifact integrity. Unknown features
    and all nonverified visual aspects remain required evidence gaps.
    """
    coverage, required, excluded = _counts(), _counts(), _counts()
    blockers, limitations = [], []
    peers = {}
    for job in jobs:
        if _valid_job(job) and job.get("verification_kind") == "semantic" and _is_midi(job):
            peers.setdefault(_key(job), []).append(job)
    rule_validity = {}
    for identity, matches in peers.items():
        rows = _rule_rows(matches[0]) if len(matches) == 1 else []
        rule_validity[identity] = len(rows) == 1 and valid_midi_rule_evidence(rows[0])
    if not jobs:
        blockers.append({"reason_code": "missing_required_jobs", "element": None})
    seen = set()
    for job in jobs:
        if not _valid_job(job):
            blockers.append({"reason_code": "malformed_required_job", "element": None})
            continue
        context = {key: job[key] for key in ("verification_kind", "source_index", "source", "hand")}
        identity = (job["verification_kind"], *_key(job))
        if identity in seen:
            blockers.append({**context, "reason_code": "duplicate_required_job", "element": None})
        seen.add(identity)
        if _is_midi(job) and not rule_validity.get(_key(job), False):
            blockers.append({**context, "reason_code": "midi_rules_missing_or_incomplete", "element": None})
        for original in job["elements"]:
            row = dict(original) if isinstance(original, dict) else {}
            valid = _valid_row(row)
            status = row.get("status") if valid else "unverified"
            if not valid:
                row.update(reported_status=row.get("status"), status="unverified")
            _add(coverage, status)
            code = _limitation_code(job, row) if valid else None
            if code and rule_validity.get(_key(job), False):
                _add(excluded, status)
                limitations.append({**context, "reason_code": code, "element": row,
                    "disposition": "unsupported_capability" if code == "physical_release_not_pedal_sounding_duration"
                                    else "source_limitation"})
                continue
            _add(required, status)
            invalid_rule = row.get("construct") == "midi_transcription_rules" and not valid_midi_rule_evidence(row)
            if status != "verified" or invalid_rule:
                blockers.append({**context, "reason_code": "midi_rules_missing_or_incomplete" if code or invalid_rule
                                 else "supported_correctness_failure" if status == "mismatch"
                                 else "supported_evidence_gap", "element": row})
    return {"policy_version": POLICY_VERSION, "passed": not blockers,
            "complete": not blockers and coverage["expected"] > 0 and coverage["expected"] == coverage["verified"],
            "coverage": coverage, "required_coverage": required, "limitation_coverage": excluded,
            "blockers": blockers, "limitations": limitations,
            "claim": "Supported evidence is required; source limitations retain their nonverified status and do not certify authorial notation."}
