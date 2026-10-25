"""Exercise the real local shell driver with bounded external stand-ins."""
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

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def local_driver(tmp_path):
    (tmp_path/'scripts').mkdir()
    for name in ('verify-notation.sh','package_notation_diagnostics.py'):
        shutil.copyfile(ROOT/'scripts'/name,tmp_path/'scripts'/name)
    binary=tmp_path/'.venv/bin';binary.mkdir(parents=True)
    python=binary/'python'
    python.write_text('#!'+sys.executable+'\n'+textwrap.dedent('''
        import json,os,signal,sys,time
        from pathlib import Path
        args=sys.argv[1:]
        if args[:2]==['-m','pytest']:
            print('60 fast regressions passed',flush=True)
            raise SystemExit(int(os.environ.get('TEST_DRIVER_QUICK_STATUS','0')))
        if args and args[0].endswith('package_notation_diagnostics.py'):
            if os.environ.get('TEST_DRIVER_PACKAGE_STATUS'):
                raise SystemExit(int(os.environ['TEST_DRIVER_PACKAGE_STATUS']))
            os.execv(sys.executable,[sys.executable,*args])
        if args and args[0]=='-u':args.pop(0)
        folder=Path(args[args.index('--out')+1]);folder.mkdir(parents=True,exist_ok=True)
        case=folder/'piece/partial';case.mkdir(parents=True,exist_ok=True)
        (case/'fixture.json').write_text('{"hand":"both"}')
        (case/'native-0.00000.png').write_bytes(b'retained framebuffer')
        (case/'verovio-0.svg').write_text('<svg/>')
        (case/'case-state.json').write_text('{"stage":"note-features"}')
        (folder/'started.json').write_text(json.dumps(dict(pid=os.getpid(),args=args)))
        if os.environ.get('TEST_DRIVER_EDIT_RUNNER')=='1':
            runner=Path('scripts/verify-notation.sh')
            runner.write_text(runner.read_text().replace('  attempted=$((attempted+1))',
                '  attempted=$((attempted + 1))\\n'*100))
        def stop(*_):
            (folder/'summary.json').write_text('{"state":"interrupted","passed":false}')
            print('Audit interrupted; checkpoints retained',flush=True)
            raise SystemExit(143)
        signal.signal(signal.SIGTERM,stop)
        if os.environ.get('TEST_DRIVER_BLOCK')=='1':time.sleep(30)
        if os.environ.get('TEST_DRIVER_FIRST_FAILURE_ONLY')=='1' and folder.name!='shard-0-of-24':
            (folder/'summary.json').write_text('{"state":"passed","passed":true}')
            raise SystemExit(0)
        (folder/'summary.json').write_text('{"state":"failed","passed":false}')
        print('A failing batch',flush=True)
        raise SystemExit(int(os.environ.get('TEST_DRIVER_AUDIT_STATUS','1')))
    '''))
    python.chmod(0o755)
    for name,body in (
        ('godot','#!/bin/sh\nexit "${TEST_DRIVER_ENGINE_STATUS:-0}"\n'),
        ('xvfb-run','#!/bin/sh\nshift\nshift\nshift\nexec "$@"\n')):
        path=binary/name;path.write_text(body);path.chmod(0o755)
    return tmp_path,dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],DISPLAY=':test')


def test_failed_batch_is_packaged_and_uses_resumable_bounded_defaults(local_driver):
    folder,env=local_driver
    result=subprocess.run(['bash','scripts/verify-notation.sh'],cwd=folder,env=env,
                          capture_output=True,text=True,timeout=10)
    assert result.returncode==1,result.stdout+result.stderr
    output=folder/'notation-check-results'
    assert not (output/'shard-1-of-24').exists()
    args=json.loads((output/'shard-0-of-24/started.json').read_text())['args']
    assert args[args.index('--workers')+1]=='2'
    assert '--resume' in args and '--reuse-captures' in args
    with ZipFile(output/'triage.zip') as archive:
        assert 'piece/partial/native-0.00000.png' in archive.namelist()
        assert 'piece/partial/case-state.json' in archive.namelist()


@pytest.mark.parametrize('signum',[signal.SIGINT,signal.SIGTERM])
def test_terminating_driver_stops_owned_batch_and_packages_partial_evidence(local_driver,signum):
    folder,env=local_driver
    env['TEST_DRIVER_BLOCK']='1'
    output=folder/'notation-check-results'
    started=output/'shard-0-of-24/started.json'
    with (folder/'driver.log').open('w') as log:
        process=subprocess.Popen(['bash','scripts/verify-notation.sh'],cwd=folder,env=env,
                                 stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        worker=None
        try:
            deadline=time.monotonic()+5
            while not started.exists() and time.monotonic()<deadline:
                time.sleep(.02)
            assert started.exists(),(folder/'driver.log').read_text()
            worker=json.loads(started.read_text())['pid']
            process.send_signal(signum)
            assert process.wait(timeout=7)==128+signum
            assert not Path(f'/proc/{worker}').exists()
            assert (folder/'driver.log').read_text().count('Saved ')==1
            with ZipFile(output/'triage.zip') as archive:
                assert json.loads(archive.read('summary.json'))['state']=='interrupted'
                assert 'piece/partial/native-0.00000.png' in archive.namelist()
        finally:
            if process.poll() is None:
                process.kill();process.wait(timeout=2)
            if worker and Path(f'/proc/{worker}').exists():
                os.kill(worker,signal.SIGKILL)


def test_continue_mode_packages_a_failed_batch_even_if_last_batch_passes(local_driver):
    folder,env=local_driver
    env.update(PIANO_VERIFY_CONTINUE_ON_FAILURE='1',TEST_DRIVER_FIRST_FAILURE_ONLY='1')
    result=subprocess.run(['bash','scripts/verify-notation.sh'],cwd=folder,env=env,
                          capture_output=True,text=True,timeout=15)
    assert result.returncode==1,result.stdout+result.stderr
    output=folder/'notation-check-results'
    assert json.loads((output/'shard-23-of-24/summary.json').read_text())['passed']
    with ZipFile(output/'triage.zip') as archive:
        assert json.loads(archive.read('summary.json'))['state']=='failed'
