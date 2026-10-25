"""A stuck/crashed capture must not lose completed work or certify a batch."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import time
import signal
import subprocess
import sys

import pytest

from scripts import check_native_verovio_overlay as audit


def process_running(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0] not in {'Z','X'}
    except FileNotFoundError:
        return False


def renderer_worker(case,source,variant,directory,godot,reuse,focused):
    """A renderer that survives TERM even when its Python parent exits."""
    directory.mkdir(parents=True,exist_ok=True)
    code='''import os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
'''
    subprocess.Popen([sys.executable,'-c',code,str(directory/'renderer-pid')],
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    while not (directory/'renderer-pid').exists():
        time.sleep(.01)
    (directory/'fixture.json').write_text('{}')
    (directory/'native-0.00000.png').write_bytes(b'actual partial framebuffer')
    (directory/'ready').touch()
    time.sleep(60)


def delayed_worker_limits(memory,ownership_directory,run_id,*coordinator):
    root=Path(ownership_directory).parent
    (root/'initializer-ready').write_text(str(os.getpid()))
    while not (root/'initialize-now').exists():time.sleep(.01)
    audit._worker_limits(memory,ownership_directory,run_id,*coordinator)


def test_worker_cannot_begin_queued_case_after_coordinator_dies_during_initialization(tmp_path):
    root=Path(__file__).resolve().parents[1]
    runner=tmp_path/'run.py'
    runner.write_text('''from pathlib import Path
from scripts import check_native_verovio_overlay as audit
from test_native_audit_recovery import delayed_worker_limits,renderer_worker,jobs
if __name__=='__main__':
    audit._worker_limits=delayed_worker_limits
    audit._library_job=renderer_worker
    list(audit.execute_case_jobs(jobs(Path(%r),['render']),workers=1,case_timeout=10,
         memory_limit_mib=3072,resume=False,godot_version='test-engine'))
'''%str(tmp_path))
    process=subprocess.Popen([sys.executable,str(runner)],
        env=dict(os.environ,PYTHONPATH=str(root)+os.pathsep+str(root/'tests')),
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    worker=None;children=[]
    try:
        deadline=time.monotonic()+5
        while not (tmp_path/'initializer-ready').exists() and time.monotonic()<deadline:
            assert process.poll() is None
            time.sleep(.01)
        worker=int((tmp_path/'initializer-ready').read_text())
        children=[int(p) for p in Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()]
        process.kill();process.wait(timeout=2)
        (tmp_path/'initialize-now').touch()
        deadline=time.monotonic()+2
        while process_running(worker) and not (tmp_path/'render/ready').exists() and time.monotonic()<deadline:
            time.sleep(.01)
        assert not (tmp_path/'render/ready').exists(),'Orphan worker started queued case work'
        assert not process_running(worker)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=2)
        renderer_file=tmp_path/'render/renderer-pid'
        for pid in children+([int(renderer_file.read_text())] if renderer_file.exists() else []):
            if process_running(pid):os.kill(pid,signal.SIGKILL)


def test_cancellation_stops_term_ignoring_renderer_after_its_worker_exits(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'_library_job',renderer_worker)
    directory=tmp_path/'render'
    def cancel_when_capturing(_):
        if (directory/'ready').exists():
            raise KeyboardInterrupt()
    try:
        with pytest.raises(KeyboardInterrupt):
            list(audit.execute_case_jobs(jobs(tmp_path,['render']),workers=1,case_timeout=10,
                memory_limit_mib=3072,resume=False,godot_version='test-engine',
                progress=cancel_when_capturing))
        renderer=int((directory/'renderer-pid').read_text())
        assert not process_running(renderer),'Renderer survived cancellation after its worker exited'
    finally:
        if (directory/'renderer-pid').exists():
            renderer=int((directory/'renderer-pid').read_text())
            if process_running(renderer):os.kill(renderer,signal.SIGKILL)


def test_sigkill_restart_stops_prior_owned_processes_before_planning(tmp_path):
    import mido
    from zipfile import ZipFile
    source=tmp_path/'source.mid'
    midi=mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                                     mido.Message('note_off',note=60,time=1920)]))
    midi.save(source)
    root=Path(__file__).resolve().parents[1]
    out=tmp_path/'shard'
    runner=tmp_path/'run.py'
    runner.write_text('''from pathlib import Path
from scripts import check_native_verovio_overlay as audit
from test_native_audit_recovery import renderer_worker,checkpoint_worker,process_running
if __name__=='__main__':
    import os,sys,json
    audit.library_sources=lambda **_: (Path(%r),)
    audit.curriculum_cases=lambda *_: ()
    audit.CASES=()
    audit._library_job=renderer_worker
    if os.environ.get('RESTART')=='1':
        original=audit._library_piece
        def checked_piece(path):
            pids=json.loads(Path(%r).read_text())
            stopped={kind:not process_running(pid) for kind,pid in pids.items()}
            Path(%r).write_text(json.dumps(stopped))
            assert all(stopped.values()),'Prior processes still running at source planning'
            return original(path)
        audit._library_piece=checked_piece
        audit._library_job=checkpoint_worker
    sys.argv=['audit','--out',%r,'--only','source','--resume','--workers','1','--case-timeout','15']
    sys.exit(audit.main())
'''%(str(source),str(tmp_path/'old-pids.json'),str(tmp_path/'planning-check.json'),str(out)))
    env=dict(os.environ,PYTHONPATH=str(root)+os.pathsep+str(root/'tests'))
    owned=[]
    with (tmp_path/'run.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(runner)],cwd=root,env=env,stdout=log,
                                 stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+8
            while not list(out.glob('*/*/ready')) and time.monotonic()<deadline:
                assert process.poll() is None,(tmp_path/'run.log').read_text()
                time.sleep(.02)
            ready,=out.glob('*/*/ready')
            worker=json.loads((ready.parent/'case-state.json').read_text())['pid']
            renderer=int((ready.parent/'renderer-pid').read_text())
            owned=[worker,renderer]
            children=Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
            trackers=[int(pid) for pid in children if int(pid)!=worker]
            (tmp_path/'old-pids.json').write_text(json.dumps(dict(worker=worker,renderer=renderer)))
            process.kill()
            assert process.wait(timeout=3)==-signal.SIGKILL
            assert process_running(worker) and process_running(renderer)
            restarted=subprocess.run([sys.executable,str(runner)],cwd=root,
                env=dict(env,RESTART='1'),stdout=log,stderr=subprocess.STDOUT,timeout=12)
            assert restarted.returncode==0,(tmp_path/'run.log').read_text()
            assert json.loads((tmp_path/'planning-check.json').read_text())==dict(worker=True,renderer=True)
            with ZipFile(tmp_path/'shard-interrupted.zip') as bundle:
                assert json.loads(bundle.read('summary.json'))['state']=='running'
                assert any(name.endswith('/native-0.00000.png') for name in bundle.namelist())
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=2)
            for pid in owned:
                if process_running(pid):os.kill(pid,signal.SIGKILL)
            for pid in locals().get('trackers',[]):
                if process_running(pid):os.kill(pid,signal.SIGTERM)


@pytest.mark.parametrize('tamper',['start_ticks','session','process_group','missing'])
def test_restart_rejects_unvalidated_identity_without_signalling_live_process(tmp_path,tamper):
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    try:
        fields=Path(f'/proc/{process.pid}/stat').read_text().rsplit(')',1)[1].split()
        identity=dict(pid=process.pid,start_ticks=int(fields[19]),session=int(fields[3]),
                      process_group=int(fields[2]),
                      boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        if tamper=='missing':identity.pop('start_ticks')
        else:identity[tamper]+=1
        registry=tmp_path/'.audit-workers';registry.mkdir()
        (registry/'prior.json').write_text(json.dumps(identity))
        (tmp_path/'summary.json').write_text('{"state":"running","passed":false}')
        with audit.audit_lock(tmp_path),pytest.raises(ValueError,match='ownership'):
            audit.package_previous_interruption(tmp_path)
        assert process.poll() is None,'Unvalidated process was signalled'
        assert json.loads((tmp_path/'summary.json').read_text())['state']=='running'
    finally:
        process.kill();process.wait(timeout=2)


def test_restart_retires_previous_boot_without_signalling_same_number_pid(tmp_path):
    process=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    try:
        registry=tmp_path/'.audit-workers';registry.mkdir()
        record=registry/'previous-boot.json'
        # No live process can belong to this boot, even if its PID now exists.
        record.write_text(json.dumps(dict(pid=process.pid,start_ticks=1,session=process.pid,
            process_group=process.pid,boot_id='previous-boot')))
        (tmp_path/'summary.json').write_text('{"state":"running","passed":false}')
        with audit.audit_lock(tmp_path):
            archive=audit.package_previous_interruption(tmp_path)
        assert archive.is_file()
        assert process.poll() is None,'Recovery signalled a process from the current boot'
        assert not record.exists(),'Previous-boot ownership should not block subsequent starts'
    finally:
        process.kill();process.wait(timeout=2)


def test_next_start_packages_hard_interrupted_run_before_replacing_summary(tmp_path):
    from zipfile import ZipFile
    out=tmp_path/'batch'
    case=out/'source'/'unfinished'
    case.mkdir(parents=True)
    previous=dict(state='running',passed=False,cases_checked=1,cases_expected=2,
                  active_cases=[dict(case='unfinished',stage='note-features')])
    (out/'summary.json').write_text(json.dumps(previous))
    (case/'case-state.json').write_text(json.dumps(dict(stage='note-features')))
    (case/'fixture.json').write_text('{}')
    (case/'native-0.00000.png').write_bytes(b'last captured frame')
    archive=audit.package_previous_interruption(out)
    with ZipFile(archive) as bundle:
        assert json.loads(bundle.read('summary.json')) == previous
        assert any(name.endswith('native-0.00000.png') for name in bundle.namelist())
    assert json.loads((out/'summary.json').read_text()) == previous


def checkpoint_worker(case, source, variant, directory, godot, reuse, focused):
    directory.mkdir(parents=True, exist_ok=True)
    marker=directory/'executions'
    marker.write_text(marker.read_text()+'x' if marker.exists() else 'x')
    if case.name=='stuck' and not (directory/'allow-completion').exists():
        time.sleep(30)
    if case.name=='crash':
        import os
        os._exit(23)
    frame=directory/'native-0.00000.png'
    frame.write_bytes(b'actual worker output')
    (directory/'fixture.json').write_text(json.dumps(dict(case=case.name)))
    (directory/'score.musicxml').write_text('<score-partwise/>')
    (directory/'audit.json').write_text(json.dumps(dict(passed=True,errors=[])))
    (directory/'capture-manifest.json').write_text(json.dumps(dict(
        renderer_dependencies_sha256=audit.capture_dependency_hash(),godot='test-engine',
        screenshots=[dict(file=frame.name,sha256=hashlib.sha256(frame.read_bytes()).hexdigest())])))
    return dict(errors=[],error_count=0,captured=True,nonverified_symbols={},symbols={})


def blocking_worker(case,source,variant,directory,godot,reuse,focused):
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'fixture.json').write_text('{"hand":"both"}')
    (directory/'native-0.00000.png').write_bytes(b'captured before interruption')
    (directory/'ready').touch()
    time.sleep(30)


def jobs(tmp_path, names):
    return [dict(case=audit.AuditCase(name,'source.mid',1,1),source_phrase=None,
                 variant=None,directory=tmp_path/name,godot='godot',focused=False,
                 key='same-inputs-'+name) for name in names]


def test_resume_reuses_completed_cases_and_keeps_their_captures(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'_library_job',checkpoint_worker)
    pending=jobs(tmp_path,['one','two'])
    first=list(audit.execute_case_jobs(pending,workers=1,case_timeout=10,
        memory_limit_mib=3072,resume=True,godot_version='test-engine'))
    assert len(first)==2 and all(row['state']=='completed' for _,row in first)
    assert not list(tmp_path.rglob('.audit-workers/*.json'))
    assert all((job['directory']/'native-0.00000.png').exists() for job in pending)
    second=list(audit.execute_case_jobs(pending,workers=1,case_timeout=10,
        memory_limit_mib=3072,resume=True,godot_version='test-engine'))
    assert all(row['resumed'] for _,row in second)
    assert [(job['directory']/'executions').read_text() for job in pending]==['x','x']
    pending[1]['key']='changed-verifier-inputs'
    third=list(audit.execute_case_jobs(pending,workers=1,case_timeout=10,
        memory_limit_mib=3072,resume=True,godot_version='test-engine'))
    assert [row['resumed'] for _,row in third]==[True,False]
    assert [(job['directory']/'executions').read_text() for job in pending]==['x','xx']


def test_one_stuck_case_has_a_deadline_and_completed_work_survives(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'_library_job',checkpoint_worker)
    start=time.monotonic()
    result=list(audit.execute_case_jobs(jobs(tmp_path,['one','stuck','unstarted']),
        workers=1,case_timeout=1,memory_limit_mib=3072,resume=True,godot_version='test-engine'))
    assert time.monotonic()-start<10
    assert result[0][1]['state']=='completed'
    assert result[1][1]['state']=='timed_out'
    assert 'deadline' in result[1][1]['result']['errors'][0].lower()
    assert (tmp_path/'one'/'case-result.json').is_file()
    assert not (tmp_path/'unstarted'/'executions').exists()
    assert (tmp_path/'stuck'/'worker-stack.log').is_file()


def test_worker_crash_is_explicit_and_does_not_hang_pool_shutdown(tmp_path,monkeypatch):
    monkeypatch.setattr(audit,'_library_job',checkpoint_worker)
    result=list(audit.execute_case_jobs(jobs(tmp_path,['crash','unstarted']),
        workers=1,case_timeout=5,memory_limit_mib=3072,resume=True,godot_version='test-engine'))
    assert result[0][1]['state']=='interrupted'
    assert result[0][1]['result']['captured'] is False
    assert not (tmp_path/'unstarted'/'executions').exists()


def test_interrupted_checkpoint_write_keeps_last_valid_json(tmp_path,monkeypatch):
    path=tmp_path/'summary.json'
    path.write_text('{"state":"running","cases_checked":3}')
    def failed_replace(*_):raise OSError('interrupted filesystem write')
    monkeypatch.setattr(audit.os,'replace',failed_replace)
    with pytest.raises(OSError,match='interrupted filesystem'):
        audit.atomic_json(path,dict(state='passed',cases_checked=4))
    assert json.loads(path.read_text())==dict(state='running',cases_checked=3)
    assert sorted(p.name for p in tmp_path.iterdir())==['summary.json']


@pytest.mark.parametrize('filename',['fixture.json','score.musicxml','native-0.00000.png'])
def test_changed_capture_evidence_cannot_reuse_a_completed_verdict(tmp_path,monkeypatch,filename):
    monkeypatch.setattr(audit,'_library_job',checkpoint_worker)
    pending=jobs(tmp_path,['one'])
    options=dict(workers=1,case_timeout=10,memory_limit_mib=3072,resume=True,godot_version='test-engine')
    list(audit.execute_case_jobs(pending,**options))
    (tmp_path/'one'/filename).write_bytes(b'changed evidence')
    rechecked=list(audit.execute_case_jobs(pending,**options))
    assert not rechecked[0][1]['resumed']
    assert (tmp_path/'one'/'executions').read_text()=='xx'


def test_batch_timeout_summary_resumes_without_repeating_completed_cases(tmp_path,monkeypatch):
    import mido
    source=tmp_path/'source.mid'
    midi=mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                                      mido.Message('note_off',note=60,time=1920)]))
    midi.save(source)
    monkeypatch.setattr(audit,'library_sources',lambda **_:(source,))
    monkeypatch.setattr(audit,'original_cases',lambda path,piece,**_:
        (audit.AuditCase(name,str(path),1,1) for name in ('one','stuck')))
    monkeypatch.setattr(audit,'curriculum_cases',lambda *_:())
    monkeypatch.setattr(audit,'CASES',())
    monkeypatch.setattr(audit,'_library_job',checkpoint_worker)
    monkeypatch.setattr(audit.subprocess,'check_output',lambda *_,**__:'test-engine')
    out=tmp_path/'out'
    first=audit.audit_library(out,'godot',include_fixtures=False,workers=1,
                              case_timeout=1,resume=True)
    assert first['state']=='interrupted' and not first['passed']
    assert (first['cases_checked'],first['cases_expected'],first['cases_pending'])==(1,2,1)
    assert json.loads((out/'summary.json').read_text())['state']=='interrupted'
    directory=out/'00-source'
    (directory/'stuck'/'allow-completion').touch()
    second=audit.audit_library(out,'godot',include_fixtures=False,workers=1,
                               case_timeout=1,resume=True)
    assert second['passed'] and second['state']=='passed'
    assert second['cases_resumed']==1 and second['cases_checked']==second['cases_expected']==2
    assert (directory/'one'/'executions').read_text()=='x'
    assert (directory/'stuck'/'executions').read_text()=='xx'


def test_second_writer_cannot_overwrite_an_active_capture_directory(tmp_path):
    frame=tmp_path/'native-0.00000.png';frame.write_bytes(b'current frame')
    with audit.audit_lock(tmp_path):
        with pytest.raises(ValueError,match='already writing'):
            with audit.audit_lock(tmp_path):
                frame.unlink()
    assert frame.read_bytes()==b'current frame'


def test_unreadable_source_keeps_denominators_explicitly_incomplete(tmp_path,monkeypatch):
    source=tmp_path/'broken.mid';source.write_bytes(b'not MIDI')
    monkeypatch.setattr(audit,'library_sources',lambda **_:(source,))
    report=audit.audit_library(tmp_path/'out','godot',include_fixtures=False,workers=1)
    assert not report['passed']
    assert not report['denominators_complete']
    assert report['sources_discovered']==1
    assert any('broken.mid' in message for message in report['failures'])


@pytest.mark.parametrize('phase',['worker','planning'])
def test_sigterm_checkpoints_packages_and_reaps_the_active_worker(tmp_path,phase):
    import mido
    import os
    from zipfile import ZipFile
    source=tmp_path/'source.mid'
    midi=mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=80),
                                      mido.Message('note_off',note=60,time=1920)]));midi.save(source)
    root=Path(__file__).resolve().parents[1]
    out=tmp_path/'shard'
    runner=tmp_path/'run.py'
    runner.write_text('''from pathlib import Path
from scripts import check_native_verovio_overlay as audit
from test_native_audit_recovery import blocking_worker
if __name__=='__main__':
    import os,sys,time
    audit.library_sources=lambda **_: (Path(%r),)
    audit.curriculum_cases=lambda *_: ()
    audit.CASES=()
    audit._library_job=blocking_worker
    if os.environ.get('BLOCK_PLANNING')=='1':
        def blocked_piece(*_):
            Path(%r).touch()
            time.sleep(30)
        audit._library_piece=blocked_piece
    sys.argv=['audit','--out',%r,'--only','source','--resume','--workers','1','--case-timeout','30']
    sys.exit(audit.main())
''' % (str(source),str(tmp_path/'planning-ready'),str(out)))
    env=dict(os.environ,PYTHONPATH=str(root)+os.pathsep+str(root/'tests'))
    if phase=='planning':env['BLOCK_PLANNING']='1'
    with (tmp_path/'run.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(runner)],cwd=root,env=env,stdout=log,
                                 stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+8
            def is_ready():
                return (tmp_path/'planning-ready').exists() if phase=='planning' else bool(list(out.glob('*/*/ready')))
            while not is_ready() and time.monotonic()<deadline:
                assert process.poll() is None,(tmp_path/'run.log').read_text()
                time.sleep(.02)
            assert is_ready()
            if phase=='worker':
                ready,=out.glob('*/*/ready')
                worker=json.loads((ready.parent/'case-state.json').read_text())['pid']
            process.terminate()
            assert process.wait(timeout=6)==143,(tmp_path/'run.log').read_text()
            summary=json.loads((out/'summary.json').read_text())
            assert summary['state']=='interrupted' and not summary['passed']
            assert summary['cases_checked']==0
            if phase=='worker':
                assert summary['cases_expected']==3 and summary['denominators_complete']
                assert not Path(f'/proc/{worker}').exists()
                assert 'blocking_worker' in (ready.parent/'worker-stack.log').read_text()
            else:
                assert not summary['denominators_complete']
            with ZipFile(tmp_path/'triage.zip') as archive:
                assert 'summary.json' in archive.namelist()
                if phase=='worker':
                    assert any(name.endswith('/native-0.00000.png') for name in archive.namelist())
        finally:
            if process.poll() is None:
                process.kill();process.wait(timeout=2)
