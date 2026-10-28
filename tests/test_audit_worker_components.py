"""Worker contracts use real spawned processes and explicit per-case recording."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

import pytest


def component(name):
    try:
        return importlib.import_module('scripts.audits.' + name)
    except ModuleNotFoundError as exc:
        pytest.fail(f'Independent worker component is missing: {exc.name}')


def receipt_worker(job, *, record_stage):
    """Picklable job callable; importing it must not import the coordinator."""
    from scripts.audits import capture_store
    directory = job['directory']
    record_stage('note-features')
    state = json.loads((directory / 'case-state.json').read_text())
    assert state['stage'] == 'note-features' and state['key'] == job['key']
    if job.get('standalone_worker'):
        assert 'scripts.check_native_verovio_overlay' not in sys.modules
    marker = directory / 'executions'
    marker.write_text(marker.read_text() + 'x' if marker.exists() else 'x')
    (directory / 'runtime.json').write_text(json.dumps(dict(
        pid=os.getpid(), session=os.getsid(0), group=os.getpgrp(),
        memory_limit=resource.getrlimit(resource.RLIMIT_AS)[0],
        threads={key: os.environ.get(key) for key in
                 ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')})))
    frame = directory / 'native-0.00000.png'
    frame.write_bytes(b'actual worker capture')
    (directory / 'fixture.json').write_text('{}')
    (directory / 'score.musicxml').write_text('<score/>')
    errors = ['Unverified symbol'] if job.get('failed_verdict') else []
    (directory / 'audit.json').write_text(json.dumps(dict(errors=errors, passed=not errors)))
    (directory / 'capture-manifest.json').write_text(json.dumps(dict(
        capture_config=capture_store.CANONICAL_CAPTURE_CONFIG,
        renderer_dependencies_sha256=capture_store.capture_dependency_hash(), godot='engine',
        screenshots=[dict(file=frame.name, sha256=hashlib.sha256(frame.read_bytes()).hexdigest())])))
    return dict(errors=errors, captured=True, symbols={}, nonverified_symbols={})


def make_jobs(tmp_path, count):
    types = component('case_types')
    return [dict(case=types.AuditCase(str(i), 'source.mid', 1, 1),
                 directory=tmp_path / str(i), key=f'key-{i}', source_phrase=None,
                 variant=None, focused=False, godot='godot') for i in range(count)]


def test_stage_recorders_own_independent_case_state(tmp_path):
    checkpoint = component('case_checkpoint')
    first = checkpoint.StageRecorder(tmp_path / 'first', key='one', run_id='run',
                                      worker_identity={'pid': os.getpid()})
    second = checkpoint.StageRecorder(tmp_path / 'second', key='two', run_id='run',
                                       worker_identity={'pid': os.getpid()})
    first('prepare')
    second('capture')
    first('noteheads')
    a = json.loads((tmp_path / 'first/case-state.json').read_text())
    b = json.loads((tmp_path / 'second/case-state.json').read_text())
    assert (a['key'], a['stage'], b['key'], b['stage']) == ('one', 'noteheads', 'two', 'capture')
    assert a['pid'] == b['pid'] == os.getpid()
    assert a['run_id'] == b['run_id'] == 'run'
    assert a['updated_at'] >= a['started_at']
    assert a['started_monotonic'] <= time.monotonic()


def test_worker_protocol_persists_terminal_stage_and_receipt(tmp_path):
    protocol = component('worker_protocol')
    job, = make_jobs(tmp_path, 1)
    job['run_id'] = 'run'
    row = protocol.run_case_worker(job, receipt_worker, 10)
    assert row['state'] == 'completed' and row['result']['captured']
    assert json.loads((job['directory'] / 'case-state.json').read_text())['stage'] == 'completed'
    receipt = json.loads((job['directory'] / 'case-result.json').read_text())
    assert receipt['key'] == job['key']
    assert set(receipt['witnesses']) == {'audit.json', 'fixture.json', 'score.musicxml',
                                       'capture-manifest.json'}
    assert {'worker_peak_rss_kib', 'renderer_peak_rss_kib', 'elapsed_seconds'} <= row.keys()


def test_worker_timeout_remains_timeout_when_case_catches_alarm(tmp_path):
    protocol = component('worker_protocol')
    job, = make_jobs(tmp_path, 1)
    job['run_id'] = 'run'

    def catching_case(job, *, record_stage):
        record_stage('rests')
        try:
            time.sleep(1)
        except TimeoutError:
            return dict(captured=True, errors=[], symbols={}, nonverified_symbols={})

    previous = signal.getsignal(signal.SIGALRM)
    row = protocol.run_case_worker(job, catching_case, .1)
    assert row['state'] == 'timed_out' and not row['result']['captured']
    assert 'deadline' in row['result']['errors'][0].lower()
    assert json.loads((job['directory'] / 'case-state.json').read_text())['stage'] == 'timed_out'
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_spawned_executor_recycles_workers_and_preserves_limits_and_resume(tmp_path, monkeypatch):
    executor = component('job_executor')
    jobs = make_jobs(tmp_path, 9)
    for job in jobs:
        job['standalone_worker'] = True
    jobs[0]['failed_verdict'] = True
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '3')
    monkeypatch.delenv('OMP_NUM_THREADS', raising=False)
    monkeypatch.setenv('MKL_NUM_THREADS', '4')
    options = dict(execute_case=receipt_worker, workers=1, case_timeout=10,
                   memory_limit_mib=3072, resume=True, godot_version='engine')
    rows = list(executor.execute_jobs(jobs, **options))
    assert len(rows) == 9 and all(row['state'] == 'completed' for _, row in rows)
    runtimes = [json.loads((job['directory'] / 'runtime.json').read_text()) for job in jobs]
    assert len({row['pid'] for row in runtimes[:8]}) == 1
    assert runtimes[8]['pid'] != runtimes[0]['pid']
    for row in runtimes:
        assert row['pid'] == row['session'] == row['group']
        assert row['memory_limit'] == 3072 * 1024**2
        assert set(row['threads'].values()) == {'1'}
    assert os.environ['OPENBLAS_NUM_THREADS'] == '3'
    assert 'OMP_NUM_THREADS' not in os.environ and os.environ['MKL_NUM_THREADS'] == '4'
    assert not list(tmp_path.rglob('.audit-workers/*.json'))
    resumed = list(executor.execute_jobs(jobs, **options))
    assert len(resumed) == 9 and all(row['resumed'] for _, row in resumed)
    assert resumed[0][1]['result']['errors'] == ['Unverified symbol']
    assert all((job['directory'] / 'executions').read_text() == 'x' for job in jobs)


def hard_stuck_worker(job, *, record_stage):
    signal.signal(signal.SIGALRM, signal.SIG_IGN)
    record_stage('note-features')
    (job['directory'] / 'executions').write_text('started')
    time.sleep(30)


def test_hard_deadline_stops_alarm_ignoring_worker_before_queued_work(tmp_path):
    executor = component('job_executor')
    jobs = make_jobs(tmp_path, 2)
    rows = list(executor.execute_jobs(jobs, execute_case=hard_stuck_worker, workers=1,
        case_timeout=.1, memory_limit_mib=3072, resume=False, godot_version='engine'))
    assert len(rows) == 1 and rows[0][1]['state'] == 'timed_out'
    assert 'Hard case deadline' in rows[0][1]['result']['errors'][0]
    assert not rows[0][1]['result']['captured']
    assert not (jobs[1]['directory'] / 'executions').exists()
    pid = json.loads((jobs[0]['directory'] / 'case-state.json').read_text())['pid']
    assert not Path(f'/proc/{pid}').exists()
    assert not list(tmp_path.rglob('.audit-workers/*.json'))


@pytest.mark.parametrize('tamper', ['audit.json', 'fixture.json', 'score.musicxml',
                                   'capture-manifest.json', 'pixels', 'witnesses', 'errors', 'key'])
def test_checkpoint_rejects_changed_or_incomplete_verdict_evidence(tmp_path, tamper):
    protocol = component('worker_protocol')
    checkpoint = component('case_checkpoint')
    job, = make_jobs(tmp_path, 1)
    job['run_id'] = 'run'
    protocol.run_case_worker(job, receipt_worker, 10)
    directory = job['directory']
    manifest = json.loads((directory / 'capture-manifest.json').read_text())
    manifest['renderer_dependencies_sha256'] = 'deps'
    (directory / 'capture-manifest.json').write_text(json.dumps(manifest))
    row = dict(state='completed', result=dict(captured=True, errors=[]))
    checkpoint.record_case(directory, key=job['key'], row=row)
    options = dict(key=job['key'], godot_version='engine', dependency_hash=lambda: 'deps')
    assert checkpoint.resumable_case(directory, **options)['resumed']
    if tamper.endswith('.json') or tamper.endswith('.musicxml'):
        (directory / tamper).write_text('changed')
    elif tamper == 'pixels':
        (directory / 'native-0.00000.png').write_bytes(b'changed frame')
    else:
        path = directory / 'case-result.json'
        record = json.loads(path.read_text())
        if tamper == 'witnesses':
            record['witnesses'].pop('audit.json')
        elif tamper == 'errors':
            record['result']['errors'] = None
        else:
            record['key'] = 'another-job'
        path.write_text(json.dumps(record))
    assert checkpoint.resumable_case(directory, **options) is None


def test_ownership_validates_every_owner_before_signalling_any_process():
    ownership = component('worker_ownership')
    processes = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                  start_new_session=True) for _ in range(2)]
    try:
        identities = [ownership.process_identity(p.pid) for p in processes]
        identities[1]['start_ticks'] += 1
        with pytest.raises(ValueError, match='ownership'):
            ownership.stop_owned_groups(identities)
        assert all(p.poll() is None for p in processes)
    finally:
        for process in processes:
            process.kill()
            process.wait(timeout=2)


def test_worker_modules_import_without_loading_coordinator():
    component('worker_protocol')
    result = subprocess.run([sys.executable, '-c',
        'import sys; from scripts.audits import worker_ownership, worker_protocol, '
        'case_checkpoint, case_types, job_executor; '
        'assert "scripts.check_native_verovio_overlay" not in sys.modules'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_cli_has_no_shared_case_recorder():
    from scripts import check_native_verovio_overlay as audit
    assert not hasattr(audit, '_CASE_STATE')
    assert not hasattr(audit, 'audit_stage')


def test_public_run_retains_contract_and_uses_standalone_recording(tmp_path, monkeypatch):
    from scripts import check_native_verovio_overlay as audit
    assert hasattr(audit, '_run_case'), 'Public run needs an explicit internal execution path'
    seen = []

    def execute(*args, **options):
        seen.append((args, options))
        options['record_stage']('noteheads')
        return {'passed': True}

    monkeypatch.setattr(audit, '_run_case', execute)
    case = audit.AuditCase('case', 'source.mid', 1, 1)
    prepared = object()
    assert audit.run(tmp_path, 'godot', case, all_symbols=True, strict=False,
                     reuse_captures=True, prepared=prepared) == {'passed': True}
    args, options = seen[0]
    assert args == (tmp_path, 'godot', case)
    assert {k: v for k, v in options.items() if k != 'record_stage'} == dict(
        all_symbols=True, strict=False, reuse_captures=True, prepared=prepared)
    assert not (tmp_path / 'case-state.json').exists()


def test_execute_case_jobs_composes_executor_and_preserves_yielded_mappings(tmp_path, monkeypatch):
    from scripts import check_native_verovio_overlay as audit
    executor = component('job_executor')
    job, = make_jobs(tmp_path, 1)
    job['caller_metadata'] = 'preserved'
    row = dict(state='completed', resumed=False, result=dict(captured=True, errors=[]))
    options = dict(workers=2, case_timeout=3, memory_limit_mib=1024, resume=True,
                   godot_version='engine', progress=object())

    def execute(jobs, **received):
        assert jobs == [job]
        assert received.pop('execute_case') is audit._library_job
        assert received.pop('dependency_hash') is audit.capture_dependency_hash
        assert received == options
        yield job, row

    monkeypatch.setattr(executor, 'execute_jobs', execute)
    result = list(audit.execute_case_jobs([job], **options))
    assert result[0][0] is job and result[0][1] is row


def test_recorded_case_passes_recorder_into_actual_capture_boundary(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import check_native_verovio_overlay as audit
    stages = []
    recorder = stages.append

    def capture(*_, record_stage, **__):
        assert record_stage is recorder
        record_stage('capture')
        raise RuntimeError('capture boundary reached')

    monkeypatch.setattr(audit.capture_runner, 'capture', capture)
    prepared = dict(model={}, xml='<score/>', sample_beats=[0.]), SimpleNamespace(pages=[])
    with pytest.raises(RuntimeError, match='capture boundary reached'):
        audit._run_case(tmp_path, 'godot', audit.CASES[0], prepared=prepared,
                        record_stage=recorder)
    assert stages == ['capture']


def test_library_job_passes_same_recorder_to_case_execution(tmp_path, monkeypatch):
    from scripts import check_native_verovio_overlay as audit
    assert hasattr(audit, '_run_case'), 'Library jobs need explicit recorded execution'
    monkeypatch.setattr(audit, '_library_piece', lambda *_: None)
    monkeypatch.setattr(audit, 'fixture', lambda *_, **__: (None, None))
    stages = []
    recorder = stages.append

    def execute(*_, record_stage, **__):
        assert record_stage is recorder
        record_stage('capture')
        record_stage('noteheads')
        return dict(errors=[], nonverified_symbols={}, whole_window_coverage=None)

    monkeypatch.setattr(audit, '_run_case', execute)
    job, = make_jobs(tmp_path, 1)
    result = audit._library_job(job, record_stage=recorder)
    assert result['captured'] and stages == ['prepare', 'capture', 'noteheads']


@pytest.mark.parametrize('module', ['case_types', 'worker_ownership', 'case_checkpoint',
                                   'worker_protocol', 'job_executor'])
def test_worker_protocol_sources_are_part_of_verification_identity(tmp_path, monkeypatch, module):
    from scripts import check_native_verovio_overlay as audit
    (tmp_path / 'scripts/audits').mkdir(parents=True)
    (tmp_path / 'piano_teacher').mkdir()
    (tmp_path / 'tests/fixtures/musical_fidelity').mkdir(parents=True)
    (tmp_path / 'scripts/check_native_verovio_overlay.py').write_text('# coordinator\n')
    (tmp_path / 'tests/fixtures/musical_fidelity/manifest.json').write_text('{}')
    source = tmp_path / f'scripts/audits/{module}.py'
    source.write_text('# version one\n')
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'capture_dependency_hash', lambda: 'renderer')
    before = audit.verification_inputs_hash(())
    source.write_text('# version two\n')
    assert audit.verification_inputs_hash(()) != before
