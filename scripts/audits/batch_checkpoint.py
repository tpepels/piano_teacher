"""Atomic batch progress publication from current case receipts."""
import json
from pathlib import Path
import time
from .capture_store import atomic_json

class BatchCheckpoint:
    def __init__(self, out: Path, summary: dict):
        self.out = out
        self.summary = summary
        self._last_progress = 0.

    def __call__(self, active=(), *, force=False):
        if not force and time.monotonic()-self._last_progress<15:
            return
        self._last_progress=time.monotonic()
        current=[]
        for job in active:
            detail=dict(case=job['case'].name,directory=str(job['directory'].relative_to(self.out)))
            try:
                state=json.loads((job['directory']/'case-state.json').read_text())
                if state.get('key')==job['key']:
                    detail.update(stage=state.get('stage'),pid=state.get('pid'),
                                  elapsed_seconds=round(time.time()-state['started_at'],1))
            except (OSError,ValueError,KeyError):
                pass
            current.append(detail)
        self.summary.update(active_cases=current,updated_at=time.time(),
                       cases_pending=self.summary['cases_expected']-self.summary['cases_checked'])
        atomic_json(self.out/'summary.json',self.summary)
        if current:
            print(f"PROGRESS {self.summary['cases_checked']}/{self.summary['cases_expected']} cases; "
                  +'; '.join(f"{j['case']} {j.get('stage','queued')} {j.get('elapsed_seconds',0):g}s"
                             for j in current),flush=True)
