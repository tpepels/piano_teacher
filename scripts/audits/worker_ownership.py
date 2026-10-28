"""Linux worker lifetime identity, ownership recovery and process-session cleanup."""
from contextlib import contextmanager
from functools import lru_cache
import faulthandler
import fcntl
import json
import os
from pathlib import Path
import resource
import signal
import time

from .capture_store import atomic_json

@contextmanager
def audit_lock(directory):
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.audit.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f'Another audit is already writing {directory}') from exc
        try:
            yield
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN)


@lru_cache(maxsize=1)
def _boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def process_identity(pid):
    """Read lifetime identity; the comm field can itself contain spaces/parentheses."""
    try:
        directory=Path('/proc')/str(pid)
        fields=(directory/'stat').read_text().rsplit(')',1)[1].split()
        return dict(pid=pid,start_ticks=int(fields[19]),session=int(fields[3]),
                    process_group=int(fields[2]),boot_id=_boot_id(),state=fields[0],
                    parent_pid=int(fields[1]),uid=directory.stat().st_uid)
    except FileNotFoundError:
        return None


IDENTITY_FIELDS=('pid','start_ticks','session','process_group','boot_id')

def process_snapshot():
    processes={}
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            member=process_identity(int(directory.name))
        except PermissionError:
            continue
        if member is not None:processes[member['pid']]=member
    return processes


def owned_members(owner, processes):
    """An extant session reserves its leader PID even after the leader exits."""
    if (isinstance(owner,dict) and isinstance(owner.get('boot_id'),str) and
            owner['boot_id'] and owner['boot_id']!=_boot_id()):
        return []  # Power loss/reboot: all old processes are gone; never signal new PIDs.
    if (not isinstance(owner,dict) or
            any(type(owner.get(k)) is not int or owner[k]<=0
                for k in IDENTITY_FIELDS if k!='boot_id') or
            owner.get('boot_id')!=_boot_id() or
            owner['session']!=owner['pid'] or owner['process_group']!=owner['pid']):
        raise ValueError('Cannot validate prior worker ownership identity')
    leader=processes.get(owner['pid'])
    if leader is not None and any(leader[k]!=owner[k] for k in IDENTITY_FIELDS):
        raise ValueError('Cannot validate prior worker ownership: PID lifetime changed')
    members=[]
    for member in processes.values():
        if member['session']!=owner['session'] or member['state'] in {'Z','X'}:
            continue
        if member['uid']!=os.getuid() or member['start_ticks']<owner['start_ticks']:
            raise ValueError('Cannot validate prior worker ownership of session member')
        members.append(member)
    return members


def signal_identity(identity, signum):
    # A PID can exit/recycle between /proc reads and signalling. A pidfd binds
    # the signal to the process opened here, not the later occupant of its PID.
    if not hasattr(os,'pidfd_open') or not hasattr(signal,'pidfd_send_signal'):
        raise ValueError('Cannot safely signal worker ownership without Linux pidfds')
    try:
        descriptor=os.pidfd_open(identity['pid'])
    except ProcessLookupError:
        return
    try:
        current=process_identity(identity['pid'])
        if current is None:
            return
        if current['uid']!=os.getuid() or any(current[k]!=identity[k] for k in IDENTITY_FIELDS):
            raise ValueError('Cannot validate worker ownership immediately before signalling')
        signal.pidfd_send_signal(descriptor,signum)
    except ProcessLookupError:
        pass
    finally:
        os.close(descriptor)


def stop_owned_groups(owners, *, stacks=False):
    # Validate every owner before sending any signal. Keep the session identity
    # through escalation: the worker can exit on TERM while Godot ignores it.
    processes=process_snapshot() if owners else {}
    groups=[(owner,owned_members(owner,processes)) for owner in owners]
    if stacks:
        for owner,members in groups:
            for member in members:
                if member['pid']==owner['pid']:
                    signal_identity(member,signal.SIGUSR1)
        if groups:time.sleep(.05)
    for _,members in groups:
        for member in members:
            signal_identity(member,signal.SIGTERM)
    for signum in (signal.SIGKILL,None):
        deadline=time.monotonic()+1
        while True:
            processes=process_snapshot() if owners else {}
            remaining=[member for owner in owners for member in owned_members(owner,processes)]
            if not remaining:
                return
            if time.monotonic()>=deadline:
                break
            time.sleep(.02)
        if signum is not None:
            for member in remaining:signal_identity(member,signum)
    raise ValueError('Cannot stop surviving prior worker ownership; refusing to replan')


def owner_records(directory):
    records=[]
    for path in directory.rglob('.audit-workers/*.json'):
        try:
            records.append((path,json.loads(path.read_text())))
        except (OSError,ValueError) as exc:
            raise ValueError(f'Cannot read prior worker ownership: {path}') from exc
    return records


def recover_prior_workers(out):
    records=owner_records(out)
    owners=[record for _,record in records]
    known={record.get('pid') for record in owners if isinstance(record,dict)}
    for path in out.glob('*/*/case-state.json'):
        try:
            state=json.loads(path.read_text())
        except (OSError,ValueError) as exc:
            raise ValueError(f'Cannot read prior worker ownership: {path}') from exc
        if not isinstance(state,dict):
            raise ValueError(f'Cannot read prior worker ownership: {path}')
        pid=state.get('pid')
        if pid is not None and (type(pid) is not int or pid<=0):
            raise ValueError(f'Cannot validate prior worker ownership: {path}')
        if pid and pid not in known and process_identity(pid) is not None:
            if state.get('worker_identity'):
                owners.append(state['worker_identity'])
                known.add(pid)
            elif state.get('stage') not in {'completed','error','timed_out'}:
                raise ValueError(f'Cannot validate legacy worker ownership: {path}')
    stop_owned_groups(owners)
    for path,_ in records:path.unlink(missing_ok=True)


def initialize_worker(memory_limit_mib, ownership_directory=None, run_id=None,
                   coordinator_identity=None):
    # Each worker owns its Godot process group, so cancellation also reaps
    # a renderer that is still capturing. No unrelated desktop is signalled.
    os.setsid()
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    signal.signal(signal.SIGTERM,signal.SIG_DFL)
    faulthandler.register(signal.SIGUSR1,all_threads=True)
    if ownership_directory is not None:
        identity=process_identity(os.getpid())
        atomic_json(Path(ownership_directory)/f"{os.getpid()}-{identity['start_ticks']}.json",
                    dict(identity,run_id=run_id))
    if coordinator_identity is not None:
        parent=process_identity(os.getppid())
        if parent is None or any(parent[k]!=coordinator_identity[k] for k in IDENTITY_FIELDS):
            raise ValueError('Coordinator ownership lifetime ended before worker initialization')
    if memory_limit_mib:
        limit=int(memory_limit_mib*1024**2)
        resource.setrlimit(resource.RLIMIT_AS,(limit,limit))


