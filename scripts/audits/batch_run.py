"""Batch composition, fixed denominators and complete exact-input accounting."""
from __future__ import annotations
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG
from . import case_catalog, case_inputs, case_execution, capture_store, job_executor, planning, verification_inputs
from .capture_store import ROOT, atomic_json
from .case_types import AuditCase
from .proof_execution import symbol_error
from .batch_checkpoint import BatchCheckpoint


def execute_case_jobs(jobs, *, workers, case_timeout, memory_limit_mib, resume,
                      godot_version, progress=None):
    """Compose the independent executor with this CLI's case execution."""
    yield from job_executor.execute_jobs(jobs, execute_case=case_execution.execute_job,
        workers=workers, case_timeout=case_timeout, memory_limit_mib=memory_limit_mib,
        resume=resume, godot_version=godot_version, progress=progress,
        dependency_hash=capture_store.capture_dependency_hash)


def audit_library(out: Path, godot: str, *, only: str = "", max_bars: int = 4,
                  include_fixtures: bool = True, workers: int = 2,
                  reuse_captures: bool = False, shard_index: int = 0,
                  shard_count: int = 1, resume: bool = False,
                  case_timeout: float = 600, memory_limit_mib: int = 3072) -> dict:
    return run_batch(out, godot, only=only, max_bars=max_bars, include_fixtures=include_fixtures,
        workers=workers, reuse_captures=reuse_captures, shard_index=shard_index,
        shard_count=shard_count, resume=resume, case_timeout=case_timeout,
        memory_limit_mib=memory_limit_mib, execute_jobs=execute_case_jobs)

def run_batch(out: Path, godot: str, *, only: str = "", max_bars: int = 4,
                  include_fixtures: bool = True, workers: int = 2,
                  reuse_captures: bool = False, shard_index: int = 0,
                  shard_count: int = 1, resume: bool = False,
                  case_timeout: float = 600, memory_limit_mib: int = 3072, execute_jobs) -> dict:
    """One source/Verovio/native test, partitionable without skipping cases."""
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("Expected 0 <= shard-index < shard-count")
    if workers<1 or case_timeout<=0 or memory_limit_mib<512:
        raise ValueError('Workers and case timeout must be positive; worker memory must be at least 512 MiB')
    sources=case_catalog.discover_sources(only=only,include_fixtures=include_fixtures)
    inputs_hash=verification_inputs.verification_inputs_hash(sources)
    godot_version=subprocess.check_output([godot,'--version'],text=True).strip()
    import numpy
    import PIL
    import verovio
    runtime=dict(godot=godot_version,python=sys.version,numpy=numpy.__version__,
                 pillow=PIL.__version__,verovio=verovio.toolkit().getVersion(),
                 capture_config=dict(CANONICAL_CAPTURE_CONFIG))
    available=next((int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                    if line.startswith('MemAvailable:')),0) if Path('/proc/meminfo').is_file() else 0
    effective_workers=min(workers,max(1,(available-1024**3)//(1536*1024**2))) if available else workers
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary = {"passed": False, "sources_expected": 0, "sources_discovered": len(sources),
               "shard_index": shard_index, "shard_count": shard_count,
               "inputs_sha256": inputs_hash,
               "capture_config": dict(CANONICAL_CAPTURE_CONFIG),
               "state":'planning',"runtime":runtime,"cases_attempted":0,"cases_resumed":0,
               "denominators_complete":False,
               "requested_workers":workers,"workers":effective_workers,
               "worker_memory_limit_mib":memory_limit_mib,"case_timeout_seconds":case_timeout,
               "started_at":time.time(),"active_cases":[],
               "coordinator_pid":os.getpid(),
               "sources_checked": 0, "cases_expected": 0, "cases_checked": 0,
               "measures_expected": 0, "measures_checked": 0,
               "failures": [], "nonverified_symbols": {}}
    atomic_json(out/'summary.json',summary)
    plans=[]
    planning_failed=False
    for source_index, path in enumerate(sources):
        try:
            piece = case_inputs.load_piece(str(path))
            # Full-source semantic import is independent of rendered
            # four-bar cases. Assign it to exactly one deterministic shard
            # instead of rebuilding an enormous complete score 24 times.
            semantic_case = AuditCase("source-semantics", str(path), 1, 1)
            if case_catalog.case_shard(path, semantic_case, shard_count) == shard_index:
                semantics = planning.source_semantics(path, piece)
                for row in semantics["elements"]:
                    if row["status"] in {"mismatch", "unverified"}:
                        summary["failures"].append(f"{path.name}: " + symbol_error(row))
                directory = out/f"{source_index:02d}-{path.stem}"
                directory.mkdir(parents=True,exist_ok=True)
                (directory/"source-semantics.json").write_text(
                    json.dumps(semantics,indent=2)+"\n")
            plan = planning.plan_source(path, piece, source_index=source_index, max_bars=max_bars,
                shard_index=shard_index, shard_count=shard_count, focused_cases=case_catalog.CASES)
            if not plan.case_count:
                continue
            summary["sources_expected"] += 1
            summary["cases_expected"] += plan.case_count
            summary["measures_expected"] += plan.measure_count
            plans.append(plan)

        except Exception as exc:
            planning_failed=True
            message = f"{path.name}: {type(exc).__name__}: {exc}"
            summary["failures"].append(message)
            print("FAIL " + message, flush=True)
    # Freeze all denominators before capture. Cover every original measure,
    # then the named hard passages, then the generated learning curriculum.
    completed=Counter()
    visited={plan.source_index:set() for plan in plans}
    totals={plan.source_index:plan.case_count for plan in plans}
    aborted=False
    summary['state']='running'
    summary['denominators_complete']=not planning_failed
    checkpoint = BatchCheckpoint(out, summary)
    checkpoint(force=True)
    try:
        for phase in ('originals', 'focused', 'stages'):
            jobs = planning.case_jobs(plans, phase, out=out, inputs_hash=inputs_hash, runtime=runtime,
                godot=godot, reuse_captures=reuse_captures or resume)
            for job,row in execute_jobs(jobs,workers=effective_workers,case_timeout=case_timeout,
                    memory_limit_mib=memory_limit_mib,resume=resume,godot_version=godot_version,
                    progress=checkpoint):
                source_index,path,case,directory=(job[k] for k in ('source_index','path','case','directory'))
                result=row['result']
                if result["errors"]:
                    message = f"{path.name} {case.name}: {result['errors'][0]}"
                    summary["failures"].append(message)
                    print("FAIL " + message + f" (details: {directory})", flush=True)
                else:
                    print(f"{'RESUME' if row.get('resumed') else 'PASS'} {path.name} {case.name}", flush=True)
                for kind, count in result.get("nonverified_symbols", {}).items():
                    summary["nonverified_symbols"][kind] = summary["nonverified_symbols"].get(kind, 0)+count
                if phase == 'originals' and result["captured"]:
                    visited[source_index].update(range(case.first_bar, case.last_bar+1))
                summary['cases_attempted']+=1
                summary['cases_resumed']+=int(row.get('resumed',False))
                if row['state']=='completed':
                    summary["cases_checked"] += 1
                    completed[source_index]+=1
                if completed[source_index]==totals[source_index]:
                    summary["sources_checked"]+=1
                summary["measures_checked"]=sum(map(len,visited.values()))
                for field in ('worker_peak_rss_kib','renderer_peak_rss_kib'):
                    summary[field]=max(summary.get(field,0),row.get(field,0))
                checkpoint(force=True)
                if row['state'] in {'interrupted','timed_out'}:
                    aborted=True
                    summary['stop_reason']=row['state']
                    break
            if aborted:
                break
    except KeyboardInterrupt:
        aborted=True
        summary['stop_reason']='signal interruption'
        summary['failures'].append('Audit interrupted; completed checkpoints and captures are retained')
    from piano_teacher.preprocessing_cache import PreprocessingCache
    PreprocessingCache(out/"cache").prune()
    try:
        current_sources=case_catalog.discover_sources(only=only,include_fixtures=include_fixtures)
        if current_sources!=sources:
            summary['failures'].append('Source membership changed during this audit; rerun the complete check')
        elif verification_inputs.verification_inputs_hash(sources)!=inputs_hash:
            summary['failures'].append('Source inputs or verification code changed during this audit; rerun the complete check')
    except (OSError,ValueError) as exc:
        summary['failures'].append(f'Source membership changed or became unreadable during this audit: {exc}')
    summary["passed"] = (not summary["failures"] and
                         not aborted and
                         summary['denominators_complete'] and
                         summary["sources_checked"] == summary["sources_expected"] and
                         summary["cases_checked"] == summary["cases_expected"] and
                         summary["measures_checked"] == summary["measures_expected"])
    summary['state']='interrupted' if aborted else 'passed' if summary['passed'] else 'failed'
    summary['finished_at']=time.time()
    checkpoint(force=True)
    return summary

