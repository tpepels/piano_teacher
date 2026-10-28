"""One worker case: explicit stage recording, deadline and durable result receipt."""
import faulthandler
import os
import resource
import signal
import time

from .case_checkpoint import StageRecorder, record_case
from .worker_ownership import process_identity


def run_case_worker(job, function, case_timeout):
    directory=job['directory']
    directory.mkdir(parents=True,exist_ok=True)
    recorder=StageRecorder(directory,key=job['key'],run_id=job['run_id'],
                           worker_identity=process_identity(os.getpid()))
    recorder('starting')
    deadline=[False]
    def expired(*_):
        deadline[0]=True
        raise TimeoutError(f'Case deadline exceeded ({case_timeout:g}s)')
    previous=signal.signal(signal.SIGALRM,expired)
    start=time.monotonic()
    with (directory/'worker-stack.log').open('a') as stack:
        faulthandler.register(signal.SIGUSR1,file=stack,all_threads=True)
        faulthandler.dump_traceback_later(max(.1,case_timeout*.8),file=stack)
        signal.setitimer(signal.ITIMER_REAL,case_timeout)
        try:
            result=function(job,record_stage=recorder)
            status='timed_out' if deadline[0] else 'completed' if result.get('captured') else 'error'
        except Exception as exc:
            status='timed_out' if deadline[0] else 'error'
            result=dict(errors=[f'{type(exc).__name__}: {exc}'],error_count=1,captured=False,
                        symbols={},nonverified_symbols={})
        finally:
            signal.setitimer(signal.ITIMER_REAL,0)
            faulthandler.cancel_dump_traceback_later()
            faulthandler.unregister(signal.SIGUSR1)
            faulthandler.register(signal.SIGUSR1,all_threads=True)
            signal.signal(signal.SIGALRM,previous)
    if deadline[0]:
        result['captured']=False
        result['errors']=[f'Case deadline exceeded ({case_timeout:g}s); see worker-stack.log']
    row=dict(state=status,result=result,resumed=False,elapsed_seconds=round(time.monotonic()-start,3),
             worker_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
             renderer_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    recorder(status)
    record_case(directory,key=job['key'],row=row)
    return row

