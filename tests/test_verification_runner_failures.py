"""Real CLI/import and outer-shell failures, without launching corpus captures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from zipfile import ZipFile

import pytest

from test_verify_notation_recovery import local_driver

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_audit(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('check_native_verovio_overlay.py', 'package_notation_diagnostics.py', 'check_godot_parse.py'):
        shutil.copyfile(ROOT / 'scripts' / name, scripts / name)
    shutil.copytree(ROOT / 'scripts/audits', scripts / 'audits',
                    ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('tests', 'godot', 'piano_teacher'):
        (tmp_path / name).symlink_to(ROOT / name, target_is_directory=True)
    (tmp_path / 'midi').mkdir()
    (tmp_path / 'midi' / 'broken.mid').write_bytes(b'genuinely invalid MIDI input')
    binary = tmp_path / 'bin'
    binary.mkdir()
    godot = binary / 'godot'
    godot.write_text('#!/bin/sh\nif [ "$1" = --version ]; then\n'
                     '  echo test-engine\n  exit "${TEST_ENGINE_STATUS:-0}"\nfi\nexit 99\n')
    godot.chmod(0o755)
    # Keep nested driver defaults independent of the enclosing audit settings.
    env = {key:value for key,value in os.environ.items() if not key.startswith('PIANO_VERIFY_')}
    env['PATH'] = str(binary) + os.pathsep + os.environ['PATH']
    env.pop('PYTHONPATH', None)
    return tmp_path, env


@pytest.mark.parametrize('invocation', ['direct', 'module'])
@pytest.mark.parametrize('previous_interruption', [False, True])
def test_real_failed_batch_packages_in_both_python_invocations(isolated_audit, invocation,
                                                             previous_interruption):
    folder, env = isolated_audit
    out = folder / 'batch'
    if previous_interruption:
        out.mkdir()
        (out / 'summary.json').write_text('{"state":"running","passed":false}')
    command = (['scripts/check_native_verovio_overlay.py'] if invocation == 'direct'
               else ['-m', 'scripts.check_native_verovio_overlay'])
    result = subprocess.run([sys.executable, *command, '--out', str(out), '--only', 'broken'],
                            cwd=folder, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'ModuleNotFoundError' not in result.stderr
    assert result.stdout.count('Diagnostic package:') == 1
    with ZipFile(folder / 'triage.zip') as archive:
        assert archive.testzip() is None
        summary = json.loads(archive.read('summary.json'))
        assert not summary['passed'] and summary['state'] == 'failed'
        assert any('broken.mid' in failure for failure in summary['failures'])
    assert (folder / 'batch-interrupted.zip').exists() == previous_interruption


def test_unexpected_coordinator_failure_has_a_summary_and_valid_zip(isolated_audit):
    folder, env = isolated_audit
    env['TEST_ENGINE_STATUS'] = '37'
    result = subprocess.run([sys.executable, 'scripts/check_native_verovio_overlay.py',
                             '--out', str(folder / 'batch'), '--only', 'broken'],
                            cwd=folder, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert 'CalledProcessError' in result.stderr
    with ZipFile(folder / 'triage.zip') as archive:
        assert archive.testzip() is None
        summary = json.loads(archive.read('summary.json'))
        assert not summary['passed'] and summary['state'] == 'error'
        assert 'CalledProcessError' in summary['failures'][-1]
        assert 'CalledProcessError' in archive.read('coordinator-error.log').decode()


def test_coordinator_validation_keeps_its_original_status_two(isolated_audit):
    folder, env = isolated_audit
    result = subprocess.run([sys.executable, 'scripts/check_native_verovio_overlay.py',
                             '--out', str(folder / 'batch'), '--only', 'nonexistent-source'],
                            cwd=folder, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2, result.stdout + result.stderr
    with ZipFile(folder / 'triage.zip') as archive:
        summary = json.loads(archive.read('summary.json'))
        assert not summary['passed'] and summary['state'] == 'error'
        assert 'ValueError' in summary['failures'][-1]


def test_direct_packaging_failure_keeps_the_real_batch_failure(isolated_audit):
    folder, env = isolated_audit
    (folder / 'triage.zip').mkdir()  # Atomic ZIP publication genuinely fails.
    result = subprocess.run([sys.executable, 'scripts/check_native_verovio_overlay.py',
                             '--out', str(folder / 'batch'), '--only', 'broken'],
                            cwd=folder, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 1
    assert 'Could not package diagnostics:' in result.stderr
    assert 'Native notation:' in result.stdout
    summary = json.loads((folder / 'batch/summary.json').read_text())
    assert summary['state'] == 'failed' and not summary['passed']


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_real_direct_coordinator_interruption_packages_without_import_failure(isolated_audit, signum):
    folder, env = isolated_audit
    godot = folder / 'bin/godot'
    ready = folder / 'engine-ready'
    godot.write_text('#!' + sys.executable + '\n' + textwrap.dedent(f'''
        from pathlib import Path
        import time
        Path({str(ready)!r}).touch()
        time.sleep(30)
    '''))
    with (folder / 'run.log').open('w') as log:
        process = subprocess.Popen([sys.executable, 'scripts/check_native_verovio_overlay.py',
            '--out', str(folder / 'batch'), '--only', 'broken'], cwd=folder, env=env,
            stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                assert process.poll() is None, (folder / 'run.log').read_text()
                time.sleep(.01)
            assert ready.exists()
            process.send_signal(signum)
            assert process.wait(timeout=5) == 128 + signum, (folder / 'run.log').read_text()
            with ZipFile(folder / 'triage.zip') as archive:
                assert archive.testzip() is None
                summary = json.loads(archive.read('summary.json'))
                assert summary['state'] == 'interrupted' and not summary['passed']
                assert not summary['denominators_complete']
            assert (folder / 'run.log').read_text().count('Diagnostic package:') == 1
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)


@pytest.mark.parametrize('coordinator_crash', [False, True])
def test_actual_outer_bash_and_real_direct_coordinator_package_once(isolated_audit, coordinator_crash):
    folder, env = isolated_audit
    shutil.copyfile(ROOT / 'scripts/verify-notation.sh', folder / 'scripts/verify-notation.sh')
    binary = folder / '.venv/bin'
    binary.mkdir(parents=True)
    python = binary / 'python'
    python.write_text('#!' + sys.executable + '\n' + textwrap.dedent('''
        import os,sys
        args=sys.argv[1:]
        if args[:2]==['-m','pytest']:
            raise SystemExit(0)
        if args and args[0]=='-u':args.pop(0)
        if args and args[0].endswith('check_native_verovio_overlay.py'):
            args.extend(['--only','broken'])
        os.execv(sys.executable,[sys.executable,*args])
    '''))
    python.chmod(0o755)
    godot = folder / 'bin/godot'
    godot.write_text('#!/bin/sh\nif [ "$1" = --version ]; then\n'
                     '  echo test-engine\n  exit "${TEST_ENGINE_STATUS:-0}"\nfi\nexit 0\n')
    display = folder / 'bin/xvfb-run'
    display.write_text('#!/bin/sh\nshift\nshift\nshift\nexec "$@"\n')
    display.chmod(0o755)
    if coordinator_crash:
        env['TEST_ENGINE_STATUS'] = '37'
    result = subprocess.run(['bash', 'scripts/verify-notation.sh'], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count('Saved ') == 1
    assert 'Diagnostic package:' not in result.stdout
    assert 'ModuleNotFoundError' not in result.stderr
    output = folder / 'notation-check-results'
    assert not (output / 'shard-1-of-24').exists()
    with ZipFile(output / 'triage.zip') as archive:
        assert archive.testzip() is None
        summary = json.loads(archive.read('summary.json'))
        assert not summary['passed']
        assert summary['state'] == ('error' if coordinator_crash else 'failed')
        assert 'run.log' in archive.namelist()


@pytest.mark.parametrize('phase,status', [('quick', 7), ('engine', 9), ('success', 0)])
def test_ci_outer_driver_propagates_quick_check_status(local_driver, phase, status):
    folder, env = local_driver
    env['TEST_DRIVER_' + phase.upper() + '_STATUS'] = str(status)
    result = subprocess.run(['bash', 'scripts/verify-notation.sh', '--ci'], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == status, result.stdout + result.stderr
    assert not (folder / 'notation-check-results').exists()


@pytest.mark.parametrize('phase,status', [('quick', 7), ('engine', 9), ('audit', 23)])
def test_outer_bash_preserves_original_failure_status_and_packages_once(local_driver, phase, status):
    folder, env = local_driver
    env['TEST_DRIVER_' + phase.upper() + '_STATUS'] = str(status)
    result = subprocess.run(['bash', 'scripts/verify-notation.sh'], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == status, result.stdout + result.stderr
    assert result.stdout.count('Saved ') == 1
    assert 'syntax error' not in result.stderr and 'break:' not in result.stderr
    output = folder / 'notation-check-results'
    assert not (output / 'shard-1-of-24').exists()
    with ZipFile(output / 'triage.zip') as archive:
        assert archive.testzip() is None
        assert ('quick.log' if phase != 'audit' else 'summary.json') in archive.namelist()


def test_outer_packaging_failure_cannot_replace_audit_exit_status(local_driver):
    folder, env = local_driver
    env.update(TEST_DRIVER_AUDIT_STATUS='23', TEST_DRIVER_PACKAGE_STATUS='41')
    result = subprocess.run(['bash', 'scripts/verify-notation.sh'], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 23, result.stdout + result.stderr
    assert 'Could not package diagnostics' in result.stderr


def test_outer_driver_parses_its_body_before_a_running_file_is_edited(local_driver):
    folder, env = local_driver
    env['TEST_DRIVER_EDIT_RUNNER'] = '1'
    result = subprocess.run(['bash', 'scripts/verify-notation.sh'], cwd=folder, env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'syntax error' not in result.stderr and 'break:' not in result.stderr
    with ZipFile(folder / 'notation-check-results/triage.zip') as archive:
        assert archive.testzip() is None


def _compression_logs(out):
    """Real, incompressible evidence keeps the bounded ZIP open for signals."""
    out.mkdir(parents=True, exist_ok=True)
    payload = os.urandom(7 * 1024 * 1024)
    names = ('run.log', 'quick.log', 'coordinator-error.log')
    for name in names:
        (out / name).write_bytes(payload)
    return names, hashlib.sha256(payload).hexdigest()


def _signal_owned_group(process, signum):
    assert process.poll() is None
    # Never signal the test runner's group or a group inherited from a caller.
    # start_new_session=True must have made this exact child its own leader.
    assert os.getsid(process.pid) == os.getpgid(process.pid) == process.pid
    assert process.pid not in (os.getsid(0), os.getpgrp())
    os.killpg(process.pid, signum)


def _interrupt_compression(process, directory, first_signal, *, process_group=False,
                           last_signal=None):
    deadline = time.monotonic() + 8
    while not list(directory.glob('.triage-*.zip')) and time.monotonic() < deadline:
        assert process.poll() is None, 'Process exited before atomic ZIP compression'
        time.sleep(.001)
    assert list(directory.glob('.triage-*.zip')), 'Atomic ZIP compression did not begin'
    other = signal.SIGTERM if first_signal == signal.SIGINT else signal.SIGINT
    # End with a different signal so a last-signal-wins implementation fails.
    for signum in (first_signal, other, other if last_signal is None else last_signal):
        assert process.poll() is None, 'Signal aborted packaging before the archive completed'
        if process_group:
            _signal_owned_group(process, signum)
        else:
            process.send_signal(signum)
        time.sleep(.01)


@pytest.mark.parametrize('invocation', ['direct', 'module'])
@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_real_coordinator_defers_repeated_signals_during_packaging(
        isolated_audit, invocation, recovery, signum):
    folder, env = isolated_audit
    out = folder / 'batch'
    names, digest = _compression_logs(out)
    previous = dict(state='running', passed=False, cases_checked=3)
    if recovery:
        (out / 'summary.json').write_text(json.dumps(previous))
    command = (['scripts/check_native_verovio_overlay.py'] if invocation == 'direct'
               else ['-m', 'scripts.check_native_verovio_overlay'])
    with (folder / 'driver.log').open('w') as log:
        process = subprocess.Popen([sys.executable, *command, '--out', str(out), '--only', 'broken'],
            cwd=folder, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            _interrupt_compression(process, folder, signum)
            assert process.wait(timeout=8) == 128 + signum, (folder / 'driver.log').read_text()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
    output = (folder / 'driver.log').read_text()
    assert 'KeyboardInterrupt' not in output
    archive_path = folder / ('batch-interrupted.zip' if recovery else 'triage.zip')
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        for name in names:
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        summary = json.loads(archive.read('summary.json'))
        if recovery:
            assert summary == previous
        else:
            assert summary['state'] == 'failed'
    assert not list(folder.glob('.triage-*.zip'))
    if recovery:
        assert output.count('Previous interrupted run diagnostics:') == 1
        assert not (folder / 'triage.zip').exists(), 'Do not start a new run after recovery was interrupted'
        assert json.loads((out / 'summary.json').read_text()) == previous
    else:
        assert output.count('Diagnostic package:') == 1


@pytest.mark.parametrize('process_group', [False, True])
@pytest.mark.parametrize('interrupt_audit', [False, True])
@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
def test_outer_exit_packaging_defers_signals_and_keeps_the_first_status(
        local_driver, process_group, interrupt_audit, signum):
    folder, env = local_driver
    env['TEST_DRIVER_AUDIT_STATUS'] = '23'
    if interrupt_audit:
        env['TEST_DRIVER_BLOCK'] = '1'
    out = folder / 'notation-check-results'
    shard = out / 'shard-0-of-24'
    names, digest = _compression_logs(shard)
    with (folder / 'driver.log').open('w') as log:
        process = subprocess.Popen(['bash', 'scripts/verify-notation.sh'], cwd=folder, env=env,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if interrupt_audit:
                deadline = time.monotonic() + 5
                while not (shard / 'started.json').exists() and time.monotonic() < deadline:
                    assert process.poll() is None
                    time.sleep(.01)
                assert (shard / 'started.json').exists()
                process.send_signal(signum)
            during_packaging = (signal.SIGTERM if signum == signal.SIGINT else signal.SIGINT) \
                if interrupt_audit else signum
            last_signal = signal.SIGTERM if signum == signal.SIGINT else signal.SIGINT
            _interrupt_compression(process, out, during_packaging, process_group=process_group,
                                   last_signal=last_signal)
            assert process.wait(timeout=8) == 128 + signum, (folder / 'driver.log').read_text()
        finally:
            if process.poll() is None:
                _signal_owned_group(process, signal.SIGKILL)
                process.wait(timeout=2)
    output = (folder / 'driver.log').read_text()
    assert output.count('Saved ') == 1, output
    assert 'KeyboardInterrupt' not in output
    assert 'Could not package diagnostics' not in output, output
    assert not list(out.glob('.triage-*.zip'))
    with ZipFile(out / 'triage.zip') as archive:
        assert archive.testzip() is None
        # tee appends the current coordinator log to the retained run.log.
        for name in names[1:]:
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        summary = json.loads(archive.read('summary.json'))
        assert summary['state'] == ('interrupted' if interrupt_audit else 'failed')
