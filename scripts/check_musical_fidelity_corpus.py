#!/usr/bin/env python3
"""Run real corpus engraving and retain reproducible PNG/JSON evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/piano-phase2a-corpus"))
    parser.add_argument("--fixture", help="Run one exact fixture filename instead of the entire corpus")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("musical_fidelity_checks", root / "tests/test_musical_fidelity_corpus.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    args.output.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    cases = [case for case in checks.SUPPORTED if not args.fixture or case["file"] == args.fixture]
    negatives = [case for case in checks.UNSUPPORTED if not args.fixture or case["file"] == args.fixture]
    if not cases and not negatives:
        parser.error(f"Unknown fixture: {args.fixture}")
    for case in cases:
        try:
            result = checks.check_pipeline(case, args.output)
            results.append(result)
            print(f"PASS {case['file']}: {result['source_attacks']} source attacks, {len(result['variants'])} variants, {len(result['pngs'])} PNGs", flush=True)
        except Exception as error:
            failures.append({"file": case["file"], "error": str(error), "traceback": traceback.format_exc()})
            print(f"FAIL {case['file']}: {type(error).__name__}: {error}", flush=True)
    for case in negatives:
        try:
            checks.test_actual_corpus_rejects_ambiguous_or_unsupported_input(case)
            results.append({"file": case["file"], "rejected": case["error"]})
            print(f"PASS {case['file']}: rejected with '{case['error']}'", flush=True)
        except BaseException as error:
            failures.append({"file": case["file"], "error": str(error), "traceback": traceback.format_exc()})
            print(f"FAIL {case['file']}: {type(error).__name__}: {error}", flush=True)
    report = {"passed": len(results), "failed": len(failures), "results": results, "failures": failures}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(results)} passed, {len(failures)} failed; evidence: {args.output / 'report.json'}")
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
