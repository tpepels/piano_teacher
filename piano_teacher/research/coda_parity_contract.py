"""Fail-closed, revision-pinned original-Coda parity subset (research only).

This module consumes independent author-source differential evidence. It never
determines parity from a fixture name or a strategy implementation alone. The
manifest is a reviewed *expectation*, not a generated oracle or live feature
switch. A changed input, algorithm, report shape or expected outcome fails.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Mapping
import hashlib
import json

OPERATIONS = ("slow-x2", "slow-x4", "dotted-3-to-1", "dotted-1-to-3",
              "chord-2-beat")
VALID_TIERS = frozenset((
    "strict-transformed", "exact-noop", "sounding-only",
    "excluded-safety", "excluded-upstream-defect", "upstream-none",
))
SOUNDING_ONLY_CAUSES = frozenset((
    "rest-coverage-only", "written-segmentation-tuplet",
    "written-segmentation-meter",
))
SAFETY_CAUSES = frozenset((
    "beamed-source-protected", "cross-measure-group-protected",
    "tuplet-source-protected", "rest-bearing-tuplet-protected",
    "changing-meter-cross-bar-chord",
))
AUTHOR_DEFECTS = frozenset((
    "upstream-disconnected-tie", "changing-meter-dotted-quantization",
))


class CodaParityContractError(ValueError):
    """Evidence does not support the pinned research parity declaration."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CodaParityContractError(reason)


def load_manifest(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _require(data.get("schema_version") == 1, "Unknown parity contract version")
    _require(data.get("research_only") is True and
             data.get("production_enabled") is False, "Production use is forbidden")
    _require(tuple(data.get("operations", ())) == OPERATIONS,
             "Different original-Coda operation set")
    _require(isinstance(data.get("fixtures"), list) and data["fixtures"],
             "Missing pinned source corpus")
    expected = Counter()
    for fixture in data["fixtures"]:
        _require(set(fixture["voices"]) == {"0", "1"},
                 "Expected two independently matched voices per pinned fixture")
        _require(len(fixture["sha256"]) == 64, "Missing source fixture fingerprint")
        for operations in fixture["voices"].values():
            _require(set(operations) == set(OPERATIONS),
                     "Incomplete declared algorithm coverage")
            for category in operations.values():
                _require(category in VALID_TIERS, "Unknown contract category")
                expected[category] += 1
    _require(dict(expected) == data["expected_counts"],
             "Declared parity counters disagree with case declarations")
    _require(len({f["id"] for f in data["fixtures"]}) == len(data["fixtures"]),
             "Duplicate pinned fixture identity")
    return data


def classify_evidence(outcome: Mapping) -> str:
    """Return evidence-derived tier, never upgrading a matching no-op."""
    if outcome.get("status") == "upstream-none":
        _require(outcome.get("written", {}).get("status") == "unavailable" and
                 outcome.get("sounding", {}).get("status") == "unavailable",
                 "Upstream None has contradictory generated output")
        return "upstream-none"
    _require(outcome.get("status") == "compared", "Incomplete algorithm comparison")
    written = outcome.get("written", {}).get("status")
    sounding = outcome.get("sounding", {}).get("status")
    effect = outcome.get("transformation_effect")
    _require(isinstance(effect, dict) and
             effect.get("native_matches_grading") is True,
             "Native written notation disagrees with grading or no effect evidence")
    _require(isinstance(effect.get("adapter_changes_source"), bool) and
             isinstance(effect.get("author_changes_source"), bool),
             "Missing source-transformation assessment")
    reason = outcome.get("diagnosis", {}).get("category")
    if written == "exact" and sounding == "exact":
        _require("diagnosis" not in outcome, "Exact output spuriously diagnosed")
        _require(effect["adapter_changes_source"] ==
                 effect["author_changes_source"],
                 "Only one side changes the original source")
        return ("strict-transformed" if effect["adapter_changes_source"]
                else "exact-noop")
    _require(written == "different" and reason,
             "Non-exact written result lacks concrete discrepancy evidence")
    if sounding == "exact":
        _require(reason in SOUNDING_ONLY_CAUSES,
                 "Sounding match with unsupported written divergence")
        _require(effect["adapter_changes_source"] ==
                 effect["author_changes_source"],
                 "Sounding match has inconsistent transformation evidence")
        return "sounding-only"
    if sounding == "different":
        if reason in SAFETY_CAUSES:
            return "excluded-safety"
        if reason in AUTHOR_DEFECTS:
            return "excluded-upstream-defect"
    if sounding == "invalid-reference-ties":
        _require(reason == "upstream-disconnected-tie",
                 "Reference tie invalidity requires explicit corroboration")
        return "excluded-upstream-defect"
    raise CodaParityContractError(
        f"Unexpected or unclassified comparison: written={written}, "
        f"sounding={sounding}, reason={reason}")


def certify_parity_subset(report: Mapping, manifest: Mapping) -> dict:
    """Check all 60 pinned outputs, and certify ONLY changing strict matches.

    This is bounded symbolic parity evidence, not production approval.
    """
    _require(report.get("upstream_revision") == manifest["reference_revision"],
             "Author revision changed")
    declarations = {x["id"]: x for x in manifest["fixtures"]}
    cases = report.get("cases", [])
    _require({x["case"] for x in cases} == set(declarations) and
             len(cases) == len(declarations), "Unapproved or missing source fixture")
    counts = Counter()
    strict = []
    excluded = []
    for case in cases:
        declaration = declarations[case["case"]]
        _require(case.get("source") == declaration["source"] and
                 case.get("sample_bars") == declaration["bars"] and
                 case.get("source_sha256") == declaration["sha256"],
                 f"Source fingerprint/scope changed: {case['case']}")
        _require(case.get("all_exact") is True and
                 case.get("reference_voices") == 2 and
                 case.get("source_part_voices") == 2 and
                 case.get("exactly_matched_voices") == 2,
                 f"Source voice MMR not independently proven: {case['case']}")
        voices = case.get("voices", [])
        _require(len(voices) == 2 and
                 {x.get("reference_voice_index") for x in voices} == {0, 1},
                 f"Ambiguous voice coverage: {case['case']}")
        for voice in voices:
            index = str(voice["reference_voice_index"])
            _require(voice.get("status") == "exact-array-match" and
                     voice.get("exact_mmr_matches") == 1,
                     f"Ambiguous MMR selection: {case['case']} voice {index}")
            operations = voice.get("algorithms", {})
            _require(set(operations) == set(OPERATIONS),
                     f"Missing or extra Coda operation: {case['case']} voice {index}")
            for operation in OPERATIONS:
                item = operations[operation]
                actual = classify_evidence(item)
                expected = declaration["voices"][index][operation]
                key = f"{case['case']}:v{index}:{operation}"
                _require(actual == expected,
                         f"Parity/subset drift {key}: expected {expected}; got {actual}")
                counts[actual] += 1
                if actual == "strict-transformed":
                    strict.append(key)
                else:
                    excluded.append({"case": key, "tier": actual,
                                     "cause": item.get("diagnosis", {}).get("category")})
    _require(dict(counts) == manifest["expected_counts"],
             "Pinned case totals changed")
    _require(report.get("algorithm_total") == sum(counts.values()) and
             report.get("algorithm_exceptions") == 0,
             "Original Coda differential did not finish cleanly")
    _require(report.get("reference_mmr_exact_voices") ==
             report.get("reference_mmr_sampled_voices") ==
             2 * len(declarations), "Missing source MMR array equality")
    _require(report.get("strict_exact_changed") == len(strict) and
             report.get("strict_exact_noop") == counts["exact-noop"],
             "Source transformation counters are inconsistent")
    _require(report.get("algorithm_upstream_none") == counts["upstream-none"],
             "Unreported original None results")
    return {
        "status": "bounded-symbolic-parity-verified",
        "research_only": True,
        "production_enabled": False,
        "reference_revision": manifest["reference_revision"],
        "strict_transformed_cases": strict,
        "strict_transformed_count": len(strict),
        "case_tiers": dict(sorted(counts.items())),
        "non_strict_cases": excluded,
        "scope": manifest["comparison_scope"],
        "limitations": [
            "Only the six SHA-pinned source excerpts and five specified operation settings",
            "Written comparison covers bare note/rest/tie events, not all authored annotations",
            "No native Godot, physical MIDI, or measured learning effectiveness",
            "Score/Part/Voice selection and all original chord levels remain outside this certificate",
        ],
    }


def certify_files(report_path: str | Path, manifest_path: str | Path,
                  output_path: str | Path) -> dict:
    """Emit a revision-bound certificate only when the full report passes."""
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    manifest = load_manifest(manifest_path)
    certificate = certify_parity_subset(report, manifest)
    certificate["report_sha256"] = hashlib.sha256(
        Path(report_path).read_bytes()).hexdigest()
    certificate["manifest_sha256"] = hashlib.sha256(
        Path(manifest_path).read_bytes()).hexdigest()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(certificate, indent=2) + "\n", encoding="utf-8")
    return certificate
