#!/usr/bin/env python3
"""Collect the trusted detector registry before running and preserving raw JUnit.

The release auditor independently collects SUITES on its own checkout; producer
metadata alone never proves that the required tests ran. No caller-supplied
test selection, count, or pytest options can narrow these suites.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
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
from scripts.notation_release_provenance import current_provenance

SUITES = {
    "semantic": (
        "tests/test_notation_proof_phase1.py",
        "tests/test_phase3_semantics.py",
        "tests/test_phase3_corpus_aggregation.py",
        "tests/test_phase5_authored_rests.py",
        "tests/test_phase5_beam_metadata.py",
        "tests/test_phase5_written_metadata.py",
        "tests/test_phase5_midi_overlaps.py",
        "tests/test_phase5_midi_contract.py",
    ),
    "visual": (
        "tests/test_native_pixel_proof.py",
        "tests/test_source_beam_pixel_fidelity.py",
        "tests/test_native_symbol_pixel_proof.py",
        "tests/test_phase3_whole_piece_coverage.py",
        "tests/test_phase3_independent_pixels.py",
        "tests/test_phase3_rest_differences.py",
        "tests/test_phase3_visual_coverage.py",
        "tests/test_phase3_raster_matching.py",
        "tests/test_phase3_capture_provenance.py",
    ),
    "real_rest": ("tests/test_phase3_real_rest_protocol.py",),
    "release_contract": tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "tests").glob("test_phase4_*.py"))
    ) + ("tests/test_phase5_corpus.py",),
}


def collect_nodeids(suite: str) -> list[str]:
    """Independently usable collection; exceptions mean readiness is blocked."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--color=no",
         "-o", "addopts=", *SUITES[suite]],
        cwd=ROOT, env={**os.environ, "PYTEST_ADDOPTS": ""},
        text=True, capture_output=True, timeout=180,
    )
    prefixes = tuple(path + "::" for path in SUITES[suite])
    nodeids = [line.strip() for line in result.stdout.splitlines()
               if line.strip().startswith(prefixes)]
    if result.returncode or not nodeids or len(nodeids) != len(set(nodeids)):
        raise ValueError("Required pytest collection failed or was empty/duplicated:\n"
                         + result.stdout + result.stderr)
    return sorted(nodeids)


def junit_nodeids(path: Path) -> list[str]:
    """Reject unsuccessful cases and normalize pytest's xunit2 classnames."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases or any(list(root.iter(tag)) for tag in ("failure", "error", "skipped")):
        raise ValueError("JUnit has no cases or contains failures, errors or skips")
    nodeids = []
    for case in cases:
        classname, name = case.get("classname", ""), case.get("name", "")
        if not classname.startswith("tests.") or not name:
            raise ValueError("JUnit testcase has no trusted pytest identity")
        nodeids.append(classname.replace(".", "/") + ".py::" + name)
    return sorted(nodeids)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, choices=SUITES)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("--revision requires a full lowercase commit SHA")
    args.out.mkdir(parents=True, exist_ok=True)
    junit = args.out / "junit.xml"
    junit.unlink(missing_ok=True)
    manifest = {
        "schema_version": 1, "revision": args.revision, "suite": args.suite,
        "junit_path": junit.name, "junit_sha256": None,
        "expected_nodeids": [], "test_files_sha256": {},
        "provenance": None, "provenance_after": None,
    }
    registry = args.out / "suite.json"

    def write_manifest():
        registry.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    write_manifest()
    status = 1
    try:
        manifest["provenance"] = current_provenance()
        write_manifest()
        if (manifest["provenance"].get("clean") is not True
                or manifest["provenance"].get("revision") != args.revision):
            raise ValueError("Mutation execution requires a clean checkout of the requested revision")
        manifest["test_files_sha256"] = {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in SUITES[args.suite]
        }
        manifest["expected_nodeids"] = collect_nodeids(args.suite)
        (args.out / "collection.log").write_text(
            "\n".join(manifest["expected_nodeids"]) + "\n")
        write_manifest()  # Must exist before any test executes.
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--color=no", "-o", "addopts=",
             "-o", "junit_family=xunit2", f"--junitxml={junit.resolve()}", *SUITES[args.suite]],
            cwd=ROOT, env={**os.environ, "PYTEST_ADDOPTS": ""},
            text=True, capture_output=True, timeout=1800,
        )
        (args.out / "pytest.log").write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr, end="", flush=True)
        if junit.is_file():
            manifest["junit_sha256"] = hashlib.sha256(junit.read_bytes()).hexdigest()
        write_manifest()
        if not result.returncode and Counter(junit_nodeids(junit)) == Counter(manifest["expected_nodeids"]):
            status = 0
    except (OSError, ValueError, ET.ParseError, subprocess.SubprocessError) as exc:
        (args.out / "collection.log").write_text(str(exc) + "\n")
        if junit.is_file():
            manifest["junit_sha256"] = hashlib.sha256(junit.read_bytes()).hexdigest()
        write_manifest()
        print(f"BLOCKED {args.suite}: {exc}", file=sys.stderr)
    finally:
        try:
            manifest["provenance_after"] = current_provenance()
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"BLOCKED final provenance: {exc}", file=sys.stderr)
        write_manifest()
    if (not manifest["provenance_after"]
            or manifest["provenance_after"].get("clean") is not True
            or manifest["provenance_after"] != manifest["provenance"]):
        print("BLOCKED: verification inputs changed during mutation execution", file=sys.stderr)
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
