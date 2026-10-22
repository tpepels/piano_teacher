#!/usr/bin/env python3
"""Make a release decision from independent notation and mutation evidence.

Exit 0 certifies only the pinned corpus and the explicit policy in this report.
Exit 1 preserves diagnostics and blocks a native renderer release.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import aggregate_phase3_corpus as corpus
from scripts.notation_release_provenance import current_provenance

POLICY_VERSION = "native-notation-release-v1"
STATUSES = corpus.STATUSES


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=corpus._json_object,
                      parse_constant=corpus._invalid_constant)


def empty_coverage():
    return dict.fromkeys(("expected", *STATUSES), 0)


def add_coverage(target, counts):
    for key in target:
        target[key] += counts[key]


def grouped(jobs, dimension):
    groups = {}
    for job in jobs:
        for row in job["elements"]:
            source = row.get("source") if isinstance(row.get("source"), dict) else {}
            identity = {"source_index": job["source_index"], "source": job["source"], "hand": job["hand"]}
            if dimension == "score":
                identity.pop("hand")
            elif dimension == "hand":
                identity = {"hand": job["hand"]}
            elif dimension == "feature":
                identity = {"feature": row.get("construct", "unknown")}
            else:
                # Preserve source labels (including pickups), parts and an
                # explicit score-level bucket. Never assign MIDI attacks to
                # inferred written measures as if the source specified them.
                identity.update(part=source.get("part", source.get("part_index")),
                                measure=source.get("measure"),
                                measure_index=source.get("measure_index"))
            key = json.dumps(identity, sort_keys=True)
            at = groups.setdefault(key, {**identity, "coverage": empty_coverage()})["coverage"]
            at["expected"] += 1
            at[row["status"]] += 1
    return list(groups.values())


def _expected_nodeids(files):
    result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "--color=no",
                             "-o", "addopts=", *files],
                            cwd=ROOT, env={**os.environ, "PYTEST_ADDOPTS": ""},
                            text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise ValueError("Mutation collection failed: " + (result.stdout + result.stderr)[-2000:])
    prefixes = tuple(path + "::" for path in files)
    nodes = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith(prefixes)]
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError("Mutation collection empty or duplicated")
    return nodes


def validate_mutations(folder, revision):
    errors, suites = [], []
    try:
        from scripts.record_notation_mutations import SUITES
    except ImportError as exc:
        return {"complete": False, "errors": [f"Mutation registry unavailable: {exc}"], "suites": []}
    folder = Path(folder)
    for name, files in SUITES.items():
        row = {"suite": name, "complete": False, "errors": []}
        suites.append(row)
        problems = row["errors"]
        try:
            candidates = list(folder.rglob("suite.json"))
            matches = [p for p in candidates if read_json(p).get("suite") == name]
            if len(matches) != 1:
                raise ValueError(f"Require exactly one {name} mutation manifest; found {len(matches)}")
            path = matches[0]
            data = read_json(path)
            if type(data.get("schema_version")) is not int or data["schema_version"] != 1 or data.get("revision") != revision:
                raise ValueError("Mutation schema/revision mismatch")
            expected = _expected_nodeids(files)
            if Counter(data.get("expected_nodeids", [])) != Counter(expected):
                raise ValueError("Mutation expected-node inventory differs from current required suite")
            actual_hashes = {f: sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
            if data.get("test_files_sha256") != actual_hashes:
                raise ValueError("Mutation test files differ from tested revision")
            junit = (path.parent / data["junit_path"]).resolve()
            if not junit.is_relative_to(path.parent.resolve()) or not junit.is_file():
                raise ValueError("Missing/invalid mutation JUnit path")
            content = junit.read_bytes()
            if sha256(content).hexdigest() != data.get("junit_sha256"):
                raise ValueError("Mutation JUnit digest mismatch")
            root = ET.fromstring(content)
            testcases = list(root.iter("testcase"))
            actual = [r.get("classname", "").replace(".", "/") + ".py::" + r.get("name", "") for r in testcases]
            if Counter(actual) != Counter(expected):
                raise ValueError("Missing, duplicate or unexpected executed mutation tests")
            failures = sum(len(list(r.iter(tag))) for tag in ("failure", "error", "skipped") for r in testcases)
            if failures or list(root.iter("error")) or list(root.iter("failure")) or list(root.iter("skipped")):
                raise ValueError("Mutation failures/errors/skips block release")
            row.update(complete=True, executed=len(actual), junit_sha256=data["junit_sha256"])
        except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError, subprocess.SubprocessError) as exc:
            problems.append(f"{name}: {exc}")
        errors.extend(problems)
    return {"complete": bool(suites) and not errors, "errors": errors, "suites": suites}


def validate_evidence(path, reports, revision):
    try:
        from scripts.package_notation_evidence import validate_manifest
        return validate_manifest(Path(path), Path(reports), revision)
    except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
        return {"complete": False, "errors": [f"Evidence validation failed: {exc}"], "cases": []}


def build_report(reports, evidence, mutations, *, revision, manual_review=None):
    reports = Path(reports)
    provenance = current_provenance()
    aggregate = corpus.aggregate(reports, scores=len(corpus.PINNED_SOURCES), include_elements=True,
                                 required_provenance=provenance)
    blockers = list(aggregate["errors"])
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or provenance["revision"] != revision:
        blockers.append("Release revision differs from the checked-out immutable revision")
    if provenance.get("clean") is not True:
        blockers.append("Release inputs contain uncommitted changes")
    for job in aggregate["jobs"]:
        prefix = "phase3-semantic-report" if job["verification_kind"] == "semantic" else "phase3-report"
        path = reports / f"{prefix}-{job['source_index']}-{job['hand']}" / "summary.json"
        try:
            supplied = read_json(path).get("provenance")
        except (OSError, ValueError, AttributeError):
            supplied = None
        if supplied != provenance:
            blockers.append(f"{job['verification_kind']} {job['source_index']}/{job['hand']}: report provenance differs from release inputs")
    categories = {}
    for kind in ("semantic", "visual"):
        jobs = [j for j in aggregate["jobs"] if j["verification_kind"] == kind]
        counts = empty_coverage()
        for job in jobs:
            add_coverage(counts, job["coverage"])
        categories[kind] = {
            "complete": all(j["complete"] for j in jobs), "coverage": counts,
            "correctness": ("failed" if counts["mismatch"] else
                            "verified" if all(j["complete"] for j in jobs) else "undetermined"),
            "cases_expected": len(jobs), "cases_present": sum(j["status"] != "missing" for j in jobs),
            "by_score": grouped(jobs, "score"), "by_hand": grouped(jobs, "hand"),
            "by_measure": grouped(jobs, "measure"), "by_feature": grouped(jobs, "feature"),
            "nonverified_elements": [r for r in aggregate["unverified_elements"] if r["verification_kind"] == kind],
            "cases": [{k: v for k, v in j.items() if k != "elements"} for j in jobs],
        }
    artifact_result = validate_evidence(evidence, reports, revision)
    mutation_result = validate_mutations(mutations, revision)
    blockers.extend(artifact_result["errors"])
    blockers.extend(mutation_result["errors"])
    if artifact_result.get("complete") is not True:
        blockers.append("Reproducible artifact evidence incomplete")
    if mutation_result.get("complete") is not True:
        blockers.append("Required mutation evidence incomplete")
    ready = not blockers and aggregate["complete"]
    return {
        "schema_version": 1, "report_kind": "native_notation_release", "policy_version": POLICY_VERSION,
        "revision": revision, "provenance": provenance, "release_ready": ready,
        "scope": {"sources": list(corpus.PINNED_SOURCES), "hands": list(corpus.HANDS),
                  "semantic_boundary": "original source versus generated notation and native score model",
                  "visual_boundary": "actual Godot pixels versus independent source and Verovio glyph expectations",
                  "beyond_corpus_verified": False},
        "decision": "release_ready" if ready else "blocked", "required_cases": aggregate["required_jobs"],
        "categories": categories, "coverage": aggregate["coverage"],
        "evidence": artifact_result, "mutations": mutation_result, "blockers": blockers,
        "manual_review": {"affects_automated_decision": False, "editorial_record": manual_review},
        "claim": "Only the pinned 17-source, three-hand corpus is eligible. Every independent semantic and visual obligation, artifact and required mutation must be verified; unsupported, ambiguous and unverified are blockers. Manual editorial review cannot override this decision.",
    }


def markdown_report(report):
    lines = [f"# Native notation release: {report['decision']}", "",
             f"Revision: `{report['revision']}` · Policy: `{report['policy_version']}`", "",
             "| Independent category | Expected | Verified | Mismatch | Ambiguous | Unsupported | Unverified |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for name, category in report["categories"].items():
        c = category["coverage"]
        lines.append(f"| {name} | {c['expected']} | {c['verified']} | {c['mismatch']} | {c['ambiguous']} | {c['unsupported']} | {c['unverified']} |")
    lines.extend(["", report["claim"], "", f"Blocking diagnostics: {len(report['blockers'])}. Full source locations and coverage are in the JSON report.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--mutations", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = build_report(args.reports, args.evidence, args.mutations, revision=args.revision)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown_report(report))
    print(f"Native release {report['decision']}: {len(report['blockers'])} blockers; {report['coverage']['verified']}/{report['coverage']['expected']} verified obligations")
    return 0 if report["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
