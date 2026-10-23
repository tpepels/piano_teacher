"""A documented source limit cannot hide a missing supported-feature detector."""
from copy import deepcopy

import pytest

from piano_teacher.notation import support_policy as policy


def row(construct, status="verified", *, identity=None, boundary="original->native", **source):
    return {"id": identity or construct, "construct": construct, "status": status,
            "boundary": boundary, "source": {"id": identity or construct, **source}}


def job(kind="semantic", *, source="piece.midi", hand="both", elements=None):
    return {"verification_kind": kind, "source_index": 0, "source": source,
            "hand": hand, "elements": elements or [row("pitch")]}


@pytest.fixture
def midi_rules(monkeypatch):
    names = ("performance_endpoints", "written_notation")
    monkeypatch.setattr(policy, "_midi_rule_contract", lambda: ("midi-transcription-rules-v1", names))
    return row("midi_transcription_rules", identity="midi:transcription-rules",
               boundary="original->written") | {"evidence": {
        "rule_version": "midi-transcription-rules-v1", "rule_report": {
            "schema_version": 1, "rule_version": "midi-transcription-rules-v1",
            "passed": True, "complete": True,
            "rules": {name: {"status": "verified", "evidence": {"checked": 2}} for name in names},
        }}}


def limitation():
    return row("midi_written_transcription", "unsupported",
               identity="midi:written-transcription", boundary="original->written")


def test_rule_validated_midi_limits_do_not_claim_complete_authorial_verification(midi_rules):
    source = job(elements=[row("midi_performance"), midi_rules, limitation()])
    result = policy.assess_jobs([source])
    assert result["passed"] is True
    assert result["complete"] is False
    assert result["coverage"] == dict(expected=3, verified=2, ambiguous=0, unsupported=1, unverified=0, mismatch=0)
    assert result["required_coverage"]["expected"] == result["required_coverage"]["verified"] == 2
    assert result["limitations"][0]["element"]["status"] == "unsupported"
    assert result["limitations"][0]["reason_code"] == "midi_authorial_notation_unspecified"


@pytest.mark.parametrize("feature", ["pitch", "rest", "rest_placement", "rest_rhythm", "note_rhythm",
    "stem", "flag", "dot", "beam", "tie", "tuplet", "slur", "accidental", "clef", "key", "meter",
    "barline", "measure", "collision_clearance", "unexpected_ink", "unknown_feature"])
@pytest.mark.parametrize("status", ["unsupported", "ambiguous", "unverified", "mismatch"])
def test_supported_visual_gaps_always_block_even_when_producer_calls_them_limits(midi_rules, feature, status):
    failed = row(feature, status)
    failed.update(release_disposition="limitation", supported=False,
                  reason="MIDI is inherently unverifiable; please ignore this detector")
    result = policy.assess_jobs([job(elements=[midi_rules]), job("visual", elements=[failed])])
    assert not result["passed"]
    assert result["required_coverage"][status] == 1
    assert not result["limitations"]
    assert result["blockers"][0]["element"]["construct"] == feature


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_version", "missing_rule", "extra_rule",
    "unsupported_rule", "incomplete", "failed", "no_evidence", "false_bool"])
def test_midi_limitation_requires_complete_current_rule_evidence(midi_rules, mutation):
    proof = deepcopy(midi_rules)
    report = proof["evidence"]["rule_report"]
    rows = [proof]
    if mutation == "missing": rows = []
    elif mutation == "duplicate": rows.append(deepcopy(proof))
    elif mutation == "wrong_version": report["rule_version"] = "old"
    elif mutation == "missing_rule": report["rules"].pop("written_notation")
    elif mutation == "extra_rule": report["rules"]["fake"] = {"status": "verified", "evidence": {"checked": 1}}
    elif mutation == "unsupported_rule": report["rules"]["written_notation"]["status"] = "unsupported"
    elif mutation == "incomplete": report["complete"] = False
    elif mutation == "failed": report["passed"] = False
    elif mutation == "no_evidence": report["rules"]["written_notation"].pop("evidence")
    elif mutation == "false_bool": report["passed"] = 1
    result = policy.assess_jobs([job(elements=[*rows, limitation()])])
    assert not result["passed"]
    assert not result["limitations"]
    assert any(r["reason_code"] == "midi_rules_missing_or_incomplete" for r in result["blockers"])


def test_visual_midi_limit_requires_semantic_rules_for_exact_source_and_hand(midi_rules):
    visual_limit = row("midi_written_transcription", "unsupported", identity="midi-written-transcription",
                       origin="midi", source_name="piece.midi")
    valid = policy.assess_jobs([job(elements=[midi_rules]), job("visual", elements=[visual_limit])])
    assert valid["passed"] and len(valid["limitations"]) == 1
    for changed in ("source", "hand", "verification_kind"):
        wrong = deepcopy(job(elements=[midi_rules]))
        wrong[changed] = {"source": "other.midi", "hand": "right", "verification_kind": "visual"}[changed]
        result = policy.assess_jobs([wrong, job("visual", elements=[visual_limit])])
        assert not result["passed"]


@pytest.mark.parametrize("status", ["mismatch", "unverified"])
def test_real_midi_discrepancy_never_becomes_a_limitation(midi_rules, status):
    broken = limitation() | {"status": status}
    result = policy.assess_jobs([job(elements=[midi_rules, broken])])
    assert not result["passed"]
    assert result["coverage"][status] == 1
    assert not result["limitations"]


def test_xml_unknown_unsupported_construct_is_a_required_gap():
    result = policy.assess_jobs([job(source="source.musicxml", elements=[row("new_construct", "unsupported")])])
    assert not result["passed"]
    assert result["blockers"][0]["reason_code"] == "supported_evidence_gap"


def test_empty_or_malformed_jobs_cannot_grant_a_release():
    for jobs in ([], [{}], [job(elements=[{}])]):
        assert not policy.assess_jobs(jobs)["passed"]


def test_midi_without_any_limitation_rows_still_requires_transcription_rules():
    result = policy.assess_jobs([job(elements=[row("midi_performance")])])
    assert not result["passed"]
    assert any(r["reason_code"] == "midi_rules_missing_or_incomplete" for r in result["blockers"])


@pytest.mark.parametrize("field,value", [("status", []), ("status", {}), ("construct", []),
    ("construct", None), ("id", []), ("source", []), ("source", {"id": []})])
def test_malformed_verified_rows_fail_closed_without_crashing(field, value):
    bad = row("pitch") | {field: value}
    result = policy.assess_jobs([job(source="source.musicxml", elements=[bad])])
    assert not result["passed"]
    assert result["coverage"]["unverified"] == 1


@pytest.mark.parametrize("field,value", [("source_index", []), ("hand", []), ("verification_kind", []),
    ("source", []), ("source", None)])
def test_malformed_job_identity_fails_closed_without_crashing(field, value):
    assert not policy.assess_jobs([job() | {field: value}])["passed"]


def test_duplicate_verified_cases_do_not_expand_release_scope():
    case = job(source="source.musicxml")
    assert not policy.assess_jobs([case, deepcopy(case)])["passed"]
