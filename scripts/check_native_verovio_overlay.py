#!/usr/bin/env python3
"""Canonical source/Verovio/native notation test for the entire MIDI library.

Loads the production native view.gd with the selected source and curriculum
scores. Independent MIDI/XML readers and actual framebuffer checks account
for source events, notation features and relative musical relationships.
Unresolved symbols fail explicitly; diagnostic PNGs remain beside failures.
--case retains the existing focused Verovio/native overlay regressions.

This is intentionally NOT a raw full-page pixel equality check: native
practice uses constant beats-per-pixel, whereas Verovio print spacing is
optical. Registration is by original source note ID, not an invented warp of
the score or a requirement that notation moves at varying speeds.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

from piano_teacher.notation import audit_annotations

# Public imports compose the same owners as direct execution. ROOT, AUTUMN_FILE
# and capture_clocks also have existing source-audit/native fixture clients.
if __package__:
    from .package_notation_diagnostics import TerminationSignals, package
    from .audits import worker_ownership, case_catalog, capture_store
    from .audits.batch_run import audit_library, execute_case_jobs
    from .audits.case_execution import run
    from .audits.case_types import AuditCase
    from .audits.case_inputs import fixture, capture_clocks
    from .audits.case_catalog import AUTUMN_FILE
    from .audits.capture_store import ROOT
else:
    from package_notation_diagnostics import TerminationSignals, package
    from audits import worker_ownership, case_catalog, capture_store
    from audits.batch_run import audit_library, execute_case_jobs
    from audits.case_execution import run
    from audits.case_types import AuditCase
    from audits.case_inputs import fixture, capture_clocks
    from audits.case_catalog import AUTUMN_FILE
    from audits.capture_store import ROOT


__all__ = ['AuditCase', 'fixture', 'run', 'audit_library', 'execute_case_jobs',
           'ROOT', 'AUTUMN_FILE', 'capture_clocks']


def package_previous_interruption(out: Path):
    """Recover diagnostics after SIGKILL/power loss, before new planning writes.

    Call only while holding the batch writer lock. A hard kill cannot execute
    a finally block; its last atomic summary and case checkpoints survive.
    """
    worker_ownership.recover_prior_workers(out)
    try:
        previous=json.loads((out/'summary.json').read_text())
    except (OSError,ValueError):
        return None
    if not isinstance(previous,dict) or previous.get('state') not in {'planning','running','interrupted'}:
        return None
    archive=out.parent/(out.name+'-interrupted.zip')
    result=package(out,archive)
    print('Previous interrupted run diagnostics: '+result['archive'],flush=True)
    return archive


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,
                        default=Path("/tmp/piano-native-verovio-overlay"))
    parser.add_argument("--only", default="", help="MIDI filename substring (focused diagnosis)")
    parser.add_argument("--case", help="Run one existing focused regression case")
    parser.add_argument("--window-bars", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2,
                        help="Independent Godot capture processes (default: 2, memory bounded)")
    parser.add_argument('--resume',action='store_true',
                        help='Reuse completed exact-input case checkpoints and valid retained captures')
    parser.add_argument('--case-timeout',type=float,default=600,
                        help='Per-case wall-clock deadline in seconds (default: 600)')
    parser.add_argument('--worker-memory-mib',type=int,default=3072,
                        help='Per-worker virtual-memory ceiling, inherited by Godot (default: 3072 MiB)')
    parser.add_argument("--reuse-captures",action="store_true",
                        help="Recheck unchanged retained PNGs; changed or missing captures are rendered again")
    parser.add_argument('--no-package-diagnostics',action='store_true',
                        help='Let the outer runner package current-run diagnostics after flushing logs')
    parser.add_argument("--shard-index", type=int, default=0,
                        help="Zero-based partition of original and curriculum cases")
    parser.add_argument("--shard-count", type=int, default=1,
                        help="Total partitions (every one must pass for full coverage)")
    a=parser.parse_args()
    godot=shutil.which("godot") or shutil.which("godot4")
    if not godot:
        parser.error("Actual Godot 4 renderer is required")
    if a.window_bars < 1:
        parser.error("--window-bars must be positive")
    if a.workers < 1:
        parser.error("--workers must be positive")
    if a.case_timeout<=0 or a.worker_memory_mib<512:
        parser.error('--case-timeout must be positive and --worker-memory-mib at least 512')
    if a.shard_count < 1 or not 0 <= a.shard_index < a.shard_count:
        parser.error("Expected 0 <= --shard-index < --shard-count")
    if a.case and a.shard_count != 1:
        parser.error("--case uses its focused overlay command; shard only the full-library test")
    if not a.case:
        failure_status=1
        with TerminationSignals() as signals:
            try:
                with worker_ownership.audit_lock(a.out):
                    recovered=False
                    try:
                        with signals.defer():
                            package_previous_interruption(a.out)
                        if signals.exit_status:
                            # Recovery finished its original archive. Leave that
                            # checkpoint intact and do not begin another run.
                            return signals.exit_status
                        recovered=True
                        summary = audit_library(a.out, godot, only=a.only, max_bars=a.window_bars,
                            workers=a.workers,reuse_captures=a.reuse_captures,resume=a.resume,
                            case_timeout=a.case_timeout,memory_limit_mib=a.worker_memory_mib,
                            shard_index=a.shard_index,shard_count=a.shard_count)
                    except (KeyboardInterrupt,Exception) as exc:
                        if not recovered and isinstance(exc,ValueError):
                            # Invalid prior process ownership must abort without
                            # rewriting another worker's checkpoint or evidence.
                            raise
                        failure_status=2 if isinstance(exc,ValueError) else 1
                        # Keep the last checkpoint's counts, even when planning,
                        # progress reporting or pool cleanup fails unexpectedly.
                        try:
                            summary=json.loads((a.out/'summary.json').read_text())
                            if not isinstance(summary,dict):
                                summary={}
                        except (OSError,ValueError):
                            summary={}
                        for field in ('cases_checked','cases_expected','sources_checked',
                                      'sources_expected','measures_checked','measures_expected'):
                            summary.setdefault(field,0)
                        interrupted=isinstance(exc,KeyboardInterrupt)
                        reason=('Interrupted during source planning' if interrupted else
                                f'Coordinator failed: {type(exc).__name__}: {exc}')
                        summary.update(passed=False,state='interrupted' if interrupted else 'error',
                                       finished_at=time.time(),denominators_complete=False,stop_reason=reason,
                                       capture_config=dict(audit_annotations.CANONICAL_CAPTURE_CONFIG))
                        summary.setdefault('failures',[]).append(reason)
                        if not interrupted:
                            detail=traceback.format_exc()
                            print(detail,file=sys.stderr,flush=True)
                            (a.out/'coordinator-error.log').write_text(detail)
                        capture_store.atomic_json(a.out/'summary.json',summary)
                    if not summary['passed'] and not a.no_package_diagnostics:
                        with signals.defer():
                            try:
                                packaged=package(a.out,a.out.parent/'triage.zip')
                                print('Diagnostic package: '+packaged['archive'],flush=True)
                            except Exception as exc:
                                print(f'Could not package diagnostics: {exc}',file=sys.stderr,flush=True)
            except ValueError as exc:
                parser.error(str(exc))
            print(f"Native notation: {summary['sources_checked']}/{summary['sources_expected']} sources, "
                  f"{summary['measures_checked']}/{summary['measures_expected']} measures, "
                  f"{summary['cases_checked']}/{summary['cases_expected']} cases, "
                  f"{len(summary['failures'])} failures; {a.out}", flush=True)
            return signals.exit_status or (0 if summary['passed'] else failure_status)
    cases = case_catalog.selected_cases(a.case)
    results = []
    errors = []
    for case in cases:
        directory = a.out / case.name
        try:
            summary = run(directory, godot, case)
            results.append(summary)
            print(f"PASS {case.name}: {summary['native_notehead_samples']} pixels "
                  f"checked; {summary['density']:.1f} px/beat; limiting ink: "
                  + json.dumps(summary["density_witness"],sort_keys=True),
                  flush=True)
        except Exception as exc:
            errors.append({"case":case.name,"error":str(exc)})
            print(f"FAIL {case.name}: {exc}",file=sys.stderr,flush=True)
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/"summary.json").write_text(json.dumps({
        "passed":len(results),"failed":len(errors),"results":results,
        "failures":errors},indent=2)+"\n")
    print(f"Native Verovio overlay: {len(results)} passed, "
          f"{len(errors)} failed",flush=True)
    return 1 if errors else 0



if __name__=="__main__":
    sys.exit(main())
