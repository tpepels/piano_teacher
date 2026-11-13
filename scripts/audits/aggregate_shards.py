"""Fail-closed final verifier of 24 independent source/photographic shards."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re

HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
CASE = re.compile(r"[gs]:[a-f0-9]{64}\Z")
PREFIX = "native-complete-shard-"


def case_identity(source: str, phase: str, case: object) -> str:
    if phase not in {"originals", "focused", "stages", "semantics"}:
        raise ValueError("Unrecognized source audit phase")
    if not source or source.startswith("/") or "\\" in source or ".." in source.split("/"):
        raise ValueError("Case identity requires a repository-relative source")
    payload = {"source": source, "phase": phase,
               "case": {**asdict(case), "filename": source}}
    digest = sha256(json.dumps(payload, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
    return ("s:" if phase == "semantics" else "g:") + digest


def encode_manifest(cases: list[str]) -> bytes:
    if any(not CASE.fullmatch(value) for value in cases):
        raise ValueError("Invalid source case identity")
    if len(set(cases)) != len(cases):
        raise ValueError("Duplicate source case within a shard")
    return ("\n".join(sorted(cases)) + ("\n" if cases else "")).encode("ascii")


def unverified_semantics(report: dict) -> list[dict]:
    """Original-source exit requires every actual obligation to verify."""
    if not isinstance(report, dict) or not isinstance(report.get("elements"), list):
        raise ValueError("Missing original-source semantic obligation ledger")
    return [row for row in report["elements"]
            if not isinstance(row, dict) or row.get("status") != "verified"]


def _int(value):
    return type(value) is int and value >= 0


def check(artifacts: Path, revision: str, *, shard_count: int = 24) -> dict:
    if not HEX40.fullmatch(revision) or type(shard_count) is not int or shard_count < 1:
        raise ValueError("Expected full Git SHA and a positive shard count")
    receipt = dict(schema_version=1, revision=revision, expected_shards=shard_count,
                   passed=False, failures=[], shards=[], sources_discovered=None,
                   inputs_sha256=None, cases_expected=0, cases_checked=0,
                   source_semantics_expected=0, source_semantics_checked=0,
                   measure_window_obligations=0, unique_case_ids=0)
    errors = receipt["failures"]
    if not artifacts.is_dir():
        errors.append("Missing entire shard artifact directory")
        return receipt
    expected = {f"{PREFIX}{i}-{revision}" for i in range(shard_count)}
    actual = {p.name for p in artifacts.iterdir() if p.name.startswith(PREFIX)}
    for missing in sorted(expected - actual):
        errors.append("Missing shard artifact " + missing)
    for extra in sorted(actual - expected):
        errors.append("Stale or unexpected shard artifact " + extra)
    seen, common = {}, {}
    for i in range(shard_count):
        directory = artifacts / f"{PREFIX}{i}-{revision}"
        if not directory.is_dir():
            continue
        try:
            recorded_revision = (directory / "revision.txt").read_text().strip()
            summary = json.loads((directory / "summary.json").read_text())
            manifest_bytes = (directory / "case-manifest.txt").read_bytes()
            manifest = manifest_bytes.decode("ascii").splitlines()
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"Shard {i}: unreadable receipt ({type(exc).__name__}: {exc})")
            continue
        if not isinstance(summary, dict):
            errors.append(f"Shard {i}: summary must be an object")
            continue
        if recorded_revision != revision:
            errors.append(f"Shard {i}: wrong original revision")
        if any(not CASE.fullmatch(x) for x in manifest):
            errors.append(f"Shard {i}: malformed case identity")
        if manifest_bytes != ("\n".join(sorted(set(manifest))) +
                             ("\n" if manifest else "")).encode("ascii"):
            errors.append(f"Shard {i}: duplicate, unsorted or truncated case manifest")
        digest = sha256(manifest_bytes).hexdigest()
        if summary.get("manifest_sha256") != digest or summary.get("manifest_entries") != len(manifest):
            errors.append(f"Shard {i}: manifest digest/count disagreement")
        graphical = sum(x.startswith("g:") for x in manifest)
        semantic = sum(x.startswith("s:") for x in manifest)
        if summary.get("cases_expected") != graphical or summary.get("source_semantics_expected") != semantic:
            errors.append(f"Shard {i}: planned case denominator disagrees with manifest")
        for identity in manifest:
            if identity in seen:
                errors.append(f"Duplicate graphical/semantic case between shards {seen[identity]} and {i}: {identity}")
            else:
                seen[identity] = i
        if summary.get("shard_index") != i or summary.get("shard_count") != shard_count:
            errors.append(f"Shard {i}: incorrect partition index/count")
        for key in ("sources_discovered", "inputs_sha256", "capture_config", "runtime"):
            value = summary.get(key)
            if key == "inputs_sha256" and (not isinstance(value, str) or not HEX64.fullmatch(value)):
                errors.append(f"Shard {i}: missing or invalid source-input digest")
            if key == "sources_discovered" and (not _int(value) or value < 1):
                errors.append(f"Shard {i}: invalid source inventory")
            if key in ("capture_config", "runtime") and (not isinstance(value, dict) or not value):
                errors.append(f"Shard {i}: incomplete runtime or capture configuration")
            if key in common and common[key] != value:
                errors.append(f"Shard {i}: {key} differs across shards")
            common.setdefault(key, value)
        if summary.get("state") != "passed" or summary.get("passed") is not True:
            errors.append(f"Shard {i}: not successfully completed")
        if summary.get("denominators_complete") is not True or summary.get("failures") != [] or summary.get("active_cases") != [] or summary.get("stop_reason"):
            errors.append(f"Shard {i}: incomplete, failed or interrupted original evidence")
        for completed, planned in (("cases_attempted", "cases_expected"), ("cases_checked", "cases_expected"),
                                   ("sources_checked", "sources_expected"), ("measures_checked", "measures_expected"),
                                   ("source_semantics_checked", "source_semantics_expected")):
            if not _int(summary.get(completed)) or not _int(summary.get(planned)) or summary[completed] != summary[planned]:
                errors.append(f"Shard {i}: {completed} does not equal {planned}")
        if summary.get("cases_pending") != 0 or not _int(summary.get("cases_pending")):
            errors.append(f"Shard {i}: pending source cases")
        if not _int(summary.get("cases_expected")) or summary["cases_expected"] == 0:
            errors.append(f"Shard {i}: empty graphical partition")
        for target, field in (("cases_expected", "cases_expected"), ("cases_checked", "cases_checked"),
                              ("source_semantics_expected", "source_semantics_expected"),
                              ("source_semantics_checked", "source_semantics_checked"),
                              ("measure_window_obligations", "measures_expected")):
            if _int(summary.get(field)):
                receipt[target] += summary[field]
        receipt["shards"].append(dict(index=i, graphical_cases=graphical,
                                      semantic_sources=semantic, manifest_sha256=digest))
    receipt["unique_case_ids"] = len(seen)
    receipt["sources_discovered"] = common.get("sources_discovered")
    receipt["inputs_sha256"] = common.get("inputs_sha256")
    if len(receipt["shards"]) != shard_count:
        errors.append("Missing or unreadable shard receipts")
    if receipt["source_semantics_expected"] != receipt["sources_discovered"]:
        errors.append("Source semantic inventory was not covered exactly once")
    if receipt["unique_case_ids"] != receipt["cases_expected"] + receipt["source_semantics_expected"]:
        errors.append("Global graphical and semantic case partition is incomplete")
    if receipt["cases_checked"] != receipt["cases_expected"] or receipt["cases_expected"] < 1:
        errors.append("Global graphical denominator incomplete")
    if receipt["source_semantics_checked"] != receipt["source_semantics_expected"]:
        errors.append("Global source semantic denominator incomplete")
    receipt["passed"] = not errors
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--shard-count", type=int, default=24)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check(args.artifacts, args.sha, shard_count=args.shard_count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("COMPLETE_NATIVE_CORPUS", "PASS" if result["passed"] else "FAIL",
          f"{len(result['shards'])}/{result['expected_shards']}",
          f"{result['cases_checked']}/{result['cases_expected']} cases")
    for problem in result["failures"]:
        print("FAIL", problem)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
