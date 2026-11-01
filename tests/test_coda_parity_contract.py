"""Fast synthetic contract tests; original backend execution is separate CI."""
from copy import deepcopy
from pathlib import Path

import pytest

from piano_teacher.research.coda_parity_contract import (
    CodaParityContractError, certify_parity_subset, classify_evidence,
    load_manifest,
)

MANIFEST = Path(__file__).resolve().parent / "fixtures/research/coda_supported_parity_v1.json"
CAUSES = {
    "source-parallel-ties": "rest-coverage-only",
    "source-authored-beams": "beamed-source-protected",
    "long-multipage-first-two-bars": "cross-measure-group-protected",
    "authored-triplet": "tuplet-source-protected",
    "rest-bearing-triplet": "rest-bearing-tuplet-protected",
    "changing-meter": "changing-meter-dotted-quantization",
}


def _outcome(fixture, operation, tier):
    if tier == "upstream-none":
        return {
            "status": "upstream-none",
            "written": {"status": "unavailable"},
            "sounding": {"status": "unavailable"},
        }
    if tier in ("strict-transformed", "exact-noop"):
        return {
            "status": "compared",
            "written": {"status": "exact"},
            "sounding": {"status": "exact"},
            "transformation_effect": {
                "adapter_changes_source": tier == "strict-transformed",
                "author_changes_source": tier == "strict-transformed",
                "native_matches_grading": True,
            },
        }
    category = CAUSES[fixture]
    sounding = "different"
    if tier == "sounding-only":
        sounding = "exact"
        category = {
            "source-parallel-ties": "rest-coverage-only",
            "rest-bearing-triplet": "written-segmentation-tuplet",
            "changing-meter": ("rest-coverage-only" if operation == "chord-2-beat"
                               else "written-segmentation-meter"),
        }[fixture]
    elif tier == "excluded-upstream-defect":
        category = ("upstream-disconnected-tie" if fixture == "authored-triplet"
                    else "changing-meter-dotted-quantization")
        if category == "upstream-disconnected-tie":
            sounding = "invalid-reference-ties"
    elif fixture == "changing-meter":
        category = "changing-meter-cross-bar-chord"
    return {
        "status": "compared",
        "written": {"status": "different"},
        "sounding": {"status": sounding},
        "diagnosis": {"category": category},
        "transformation_effect": {
            "adapter_changes_source": tier == "sounding-only",
            "author_changes_source": tier == "sounding-only",
            "native_matches_grading": True,
        },
    }


def _report(manifest):
    cases = []
    for fixture in manifest["fixtures"]:
        voices = []
        for index,operations in fixture["voices"].items():
            voices.append({
                "reference_voice_index": int(index),
                "status": "exact-array-match",
                "exact_mmr_matches": 1,
                "algorithms": {
                    name: _outcome(fixture["id"], name, tier)
                    for name,tier in operations.items()
                },
            })
        cases.append({
            "case": fixture["id"], "source": fixture["source"],
            "sample_bars": fixture["bars"],
            "source_sha256": fixture["sha256"],
            "reference_voices": 2, "source_part_voices": 2,
            "exactly_matched_voices": 2, "all_exact": True, "voices": voices,
        })
    return {
        "upstream_revision": manifest["reference_revision"], "cases": cases,
        "algorithm_total": 60, "algorithm_exceptions": 0,
        "reference_mmr_exact_voices": 12, "reference_mmr_sampled_voices": 12,
        "strict_exact_changed": 24, "strict_exact_noop": 6,
        "algorithm_upstream_none": 4,
    }


def test_pinned_manifest_rejects_incomplete_or_unknown_coverage():
    manifest = load_manifest(MANIFEST)
    assert manifest["expected_counts"] == {
        "strict-transformed": 24, "exact-noop": 6, "sounding-only": 10,
        "excluded-safety": 11, "excluded-upstream-defect": 5, "upstream-none": 4,
    }
    assert len(manifest["fixtures"]) == 6


def test_strict_subset_excludes_noops_written_only_and_author_defects():
    manifest = load_manifest(MANIFEST)
    result = certify_parity_subset(_report(manifest), manifest)
    assert result["strict_transformed_count"] == 24
    assert result["case_tiers"] == manifest["expected_counts"]
    assert len(result["non_strict_cases"]) == 36
    assert result["research_only"] and not result["production_enabled"]


@pytest.mark.parametrize("mutation", [
    "source-fingerprint", "missing-operation", "unexpected-voice",
    "changed-author-revision", "lost-source-mmr", "native-grading-divergence",
    "promoted-noop", "broken-strict-timing", "unapproved-reference-tie",
    "unknown-discrepancy-cause", "upstream-none-has-output",
])
def test_contract_rejects_drift_and_false_parity(mutation):
    manifest = load_manifest(MANIFEST)
    report = _report(manifest)
    sample = report["cases"][1]
    if mutation == "source-fingerprint":
        sample["source_sha256"] = "0"*64
    elif mutation == "missing-operation":
        del sample["voices"][0]["algorithms"]["slow-x2"]
    elif mutation == "unexpected-voice":
        sample["voices"][1]["reference_voice_index"] = 0
    elif mutation == "changed-author-revision":
        report["upstream_revision"] = "different"
    elif mutation == "lost-source-mmr":
        sample["voices"][0]["exact_mmr_matches"] = 0
    elif mutation == "native-grading-divergence":
        sample["voices"][0]["algorithms"]["slow-x2"][
            "transformation_effect"]["native_matches_grading"] = False
    elif mutation == "promoted-noop":
        report["cases"][0]["voices"][0]["algorithms"]["dotted-3-to-1"][
            "transformation_effect"]["adapter_changes_source"] = True
    elif mutation == "broken-strict-timing":
        sample["voices"][0]["algorithms"]["slow-x2"]["sounding"]["status"] = "different"
    elif mutation == "unapproved-reference-tie":
        sample["voices"][0]["algorithms"]["dotted-3-to-1"][
            "sounding"]["status"] = "invalid-reference-ties"
    elif mutation == "unknown-discrepancy-cause":
        sample["voices"][0]["algorithms"]["dotted-3-to-1"][
            "diagnosis"]["category"] = "unclassified"
    elif mutation == "upstream-none-has-output":
        sample["voices"][1]["algorithms"]["chord-2-beat"][
            "written"]["status"] = "exact"
    with pytest.raises(CodaParityContractError):
        certify_parity_subset(report, manifest)


def test_manifest_cannot_enable_production():
    import json
    from tempfile import TemporaryDirectory
    manifest = load_manifest(MANIFEST)
    manifest["production_enabled"] = True
    with TemporaryDirectory() as d:
        path = Path(d) / "manifest.json"
        path.write_text(json.dumps(manifest))
        with pytest.raises(CodaParityContractError):
            load_manifest(path)


def test_unknown_result_never_qualifies_for_strict_subset():
    with pytest.raises(CodaParityContractError):
        classify_evidence({"status": "not-run"})
