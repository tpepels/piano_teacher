"""Bounded spawned case execution and ownership-aware pool lifetime."""
from concurrent.futures import ProcessPoolExecutor, FIRST_COMPLETED, wait
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
import uuid

from .case_checkpoint import record_case, resumable_case
from .worker_protocol import run_case_worker
from .worker_ownership import (initialize_worker, owner_records, process_identity,
                               signal_identity, stop_owned_groups)


def stop_workers(pool, ownership_root):
    # terminate_workers is public on Python 3.14. Older supported Pythons
    # expose the processes but lack a nonblocking cancellation API.
    processes=list((getattr(pool,'_processes',None) or {}).values())
    records=owner_records(ownership_root)
    owners={owner['pid']:owner for _,owner in records}
    starting=[]
    for process in processes:
        if process.is_alive() and process.pid not in owners:
            identity=process_identity(process.pid)
            # Bind this first observation to the still-live Process object,
            # not merely a PID which might have exited/recycled meanwhile.
            if identity is not None and process.is_alive():
                if identity['parent_pid']!=os.getpid() or identity['uid']!=os.getuid():
                    raise ValueError('Cannot validate unregistered worker ownership')
                if identity['session']==identity['process_group']==process.pid:
                    owners[process.pid]=identity
                else:
                    starting.append(identity)  # Has not reached setsid/registration yet.
    for identity in starting:signal_identity(identity,signal.SIGKILL)
    stop_owned_groups(list(owners.values()),stacks=True)
    for process in processes:
        process.join(timeout=1)
        if process.is_alive():
            raise ValueError('Cannot stop worker ownership; refusing to leave a live pool')
    for path,_ in records:path.unlink(missing_ok=True)
    if hasattr(pool,'shutdown'):
        pool.shutdown(wait=False,cancel_futures=True)


def execute_jobs(jobs, *, execute_case, workers, case_timeout, memory_limit_mib, resume,
                      godot_version, progress=None, initializer=None, pool_factory=None,
                 dependency_hash=None):
    """Bound the existing worker queue; checkpoint before publishing results."""
    pending=[]
    run_id=uuid.uuid4().hex
    for job in jobs:
        saved=resumable_case(job['directory'],key=job['key'],godot_version=godot_version,
                             dependency_hash=dependency_hash) if resume else None
        if saved is not None:
            yield job,saved
        else:
            pending.append(dict(job,run_id=run_id))
    if not pending:
        return
    # A fresh spawned worker imports NumPy with one BLAS thread, including
    # recycled workers. Restore the caller's environment after pool cleanup.
    variables=('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')
    previous={name:os.environ.get(name) for name in variables}
    os.environ.update(dict.fromkeys(variables,'1'))
    owner_directory=Path(os.path.commonpath([job['directory'].parent for job in pending]))/'.audit-workers'
    pool_factory=pool_factory or ProcessPoolExecutor
    initializer=initializer or initialize_worker
    pool=pool_factory(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),
        initializer=initializer,
        initargs=(memory_limit_mib,owner_directory,run_id,process_identity(os.getpid())),
        max_tasks_per_child=8)
    active={}
    remaining=iter(pending)
    abort=False
    try:
        def submit():
            for _ in range(workers-len(active)):
                job=next(remaining,None)
                if job is None:
                    break
                future=pool.submit(run_case_worker,job,execute_case,case_timeout)
                active[future]=(job,time.monotonic())
        submit()
        while active:
            done,_=wait(tuple(active),timeout=.5,return_when=FIRST_COMPLETED)
            for future in done:
                job,_=active.pop(future)
                try:
                    row=future.result()
                except Exception as exc:
                    row=dict(state='interrupted',resumed=False,result=dict(captured=False,
                        errors=[f'Worker failed: {exc}'],error_count=1,symbols={},nonverified_symbols={}))
                    record_case(job['directory'],key=job['key'],row=row)
                if row['state'] in {'timed_out','interrupted'}:
                    abort=True
                yield job,row
            if abort:
                break
            for future,(job,submitted) in active.items():
                try:
                    record=json.loads((job['directory']/'case-state.json').read_text())
                    started=record['started_monotonic'] if record.get('run_id')==run_id else submitted+10
                except (OSError,ValueError,KeyError):
                    started=submitted+10
                if time.monotonic()-started>case_timeout+2:
                    row=dict(state='timed_out',resumed=False,result=dict(captured=False,
                        errors=[f'Hard case deadline exceeded ({case_timeout:g}s); worker terminated'],
                        error_count=1,symbols={},nonverified_symbols={}))
                    record_case(job['directory'],key=job['key'],row=row)
                    yield job,row
                    abort=True
                    break
            if abort:
                break
            if progress is not None:
                progress([job for job,_ in active.values()])
            submit()
    finally:
        try:
            stop_workers(pool,owner_directory.parent) if active else pool.shutdown(wait=True) if hasattr(pool,'shutdown') else None
            records=owner_records(owner_directory.parent)
            stop_owned_groups([owner for _,owner in records])
            for path,_ in records:path.unlink(missing_ok=True)
        finally:
            for name,value in previous.items():
                if value is None:
                    os.environ.pop(name,None)
                else:
                    os.environ[name]=value

