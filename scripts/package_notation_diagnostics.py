#!/usr/bin/env python3
"""Package representative native-notation failure evidence in a bounded ZIP."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

MARKERS = (
    ('unowned-symbol', 'Unowned authentic timed-symbol contour'),
    ('source-tracking', 'Incomplete source clock or glyph tracking evidence'),
    ('reference-group', 'Reference source event IDs are absent or ambiguous'),
    ('boundary', 'measure: unverified'),
    ('tie', 'tie: mismatch'),
    ('flag-absence', 'flag_absence: unverified'),
    ('note-pixels', 'Independent native pixel check:'),
    ('ledger', 'ledger: mismatch'),
    ('rest', 'rest_placement: mismatch'),
    ('articulation', 'accidental: ambiguous'),
    ('dot', 'dot: ambiguous'),
)
MAX_CASES = 11
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
FRAME_PATTERN = re.compile(r'native--?\d+\.\d+\.png')


class TerminationSignals:
    """Interrupt work once; defer further unwinding while publishing evidence."""

    def __init__(self):
        self.received = None
        self._deferred = 0

    @property
    def exit_status(self):
        return 128 + self.received if self.received is not None else 0

    def _stop(self, signum, _frame):
        # A later signal must neither replace the first status nor interrupt
        # checkpoint/worker cleanup or the one atomic archive publication.
        if self.received is None:
            self.received = signum
            if not self._deferred:
                raise KeyboardInterrupt()

    def __enter__(self):
        self._handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        for signum in self._handlers:
            signal.signal(signum, self._stop)
        return self

    def __exit__(self, *_exc):
        for signum, handler in self._handlers.items():
            signal.signal(signum, handler)

    @contextmanager
    def defer(self):
        self._deferred += 1
        try:
            yield
        finally:
            self._deferred -= 1


@contextmanager
def atomic_archive(output):
    with tempfile.NamedTemporaryFile(dir=output.parent,prefix='.triage-',suffix='.zip',delete=False) as stream:
        temporary=Path(stream.name)
    try:
        with ZipFile(temporary,'w',ZIP_DEFLATED,strict_timestamps=False) as archive:
            yield archive
        os.replace(temporary,output)
    finally:
        temporary.unlink(missing_ok=True)


def read_record(path):
    try:
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):
        return {}


def classify(message: str) -> str:
    for label, marker in MARKERS:
        if marker in message:
            return label
    return 'other'


def package(shard: Path, output: Path) -> dict:
    shard = shard.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    selections = {}
    interrupted={}
    directories={p.parent for pattern in ('*/*/fixture.json','*/*/case-state.json','*/*/case-result.json')
                 for p in shard.glob(pattern)}
    for directory in sorted(directories):
        fixture=directory/'fixture.json'
        audit=directory/'audit.json'
        state=read_record(directory/'case-state.json')
        result=read_record(directory/'case-result.json')
        stale=audit.is_file() and fixture.is_file() and audit.stat().st_mtime<fixture.stat().st_mtime
        partial=(state and state.get('stage')!='completed') or (result and result.get('state')!='completed')
        if not audit.is_file() or stale or partial:
            interrupted[directory]=dict(stale_audit=stale,stage=state.get('stage','unrecorded'))
    if interrupted:
        counts['interrupted']=len(interrupted)
        first=next(iter(interrupted))
        selections['interrupted']=(first/'audit.json','Incomplete case: '+interrupted[first]['stage'])
    cases = sorted(shard.rglob('audit.json'))
    for audit in cases:
        if audit.parent in interrupted:
            continue
        try:
            record = json.loads(audit.read_text())
        except (OSError, ValueError):
            continue
        for message in record.get('errors', []):
            category = classify(message)
            counts[category] += 1
            if category != 'other' and category not in selections:
                selections[category] = (audit, message)
    summary = {'audit_files': len(cases), 'error_counts': counts,
               'interrupted_cases':[str(p.relative_to(shard)) for p in interrupted],
               'selected_examples': {kind: str(file.relative_to(shard))
                                     for kind, (file, _) in selections.items()}}
    total = 0
    with atomic_archive(output) as archive:
        included = set()

        def add(path: Path, name=None) -> None:
            nonlocal total
            if not path.is_file() or path in included:
                return
            size = path.stat().st_size
            if size > MAX_FILE_BYTES or total + size > MAX_ARCHIVE_BYTES:
                return
            archive.write(path, name or path.relative_to(shard).as_posix())
            included.add(path)
            total += size

        for name in ('summary.json', 'run.log','quick.log','coordinator-error.log','investigation.json'):
            add(shard / name)
        archive.writestr('triage-summary.json', json.dumps(summary, indent=2) + '\n')
        for kind, (audit, trigger) in list(selections.items())[:MAX_CASES]:
            directory = audit.parent
            if interrupted.get(directory,{}).get('stale_audit'):
                add(audit,(directory.relative_to(shard)/'previous-audit.json').as_posix())
            else:
                add(audit)
            for name in ('case-state.json','case-result.json','worker-stack.log',
                         'interruption-stack.log','capture-manifest.json','fixture.json','godot.log',
                         'capture-publish.json'):
                add(directory/name)
            attempts=sorted(directory.glob('capture-incomplete-*'),key=lambda p:p.stat().st_mtime,reverse=True)
            for attempt in attempts[:1]:
                for name in ('godot.log','capture-error.txt','fixture.json','score.musicxml'):
                    add(attempt/name)
                for frame in sorted(attempt.glob('native-*.png'))[:2]:
                    add(frame)
            for filename in ('independent-connectors.json', 'independent-beams.json',
                             'independent-tuplets.json', 'independent-structure.json',
                             'independent-ledgers.json', 'independent-features.json'):
                add(directory / filename)
            for path in sorted(directory.glob('verovio-*.svg'))[:1]:
                add(path)
            for pattern in ('*.musicxml', '*.xml'):
                for path in sorted(directory.glob(pattern))[:1]:
                    add(path)
            frames = FRAME_PATTERN.findall(trigger)
            if not frames:
                frames = [p.name for p in sorted(directory.glob('native-*.png'))[:2]]
            for name in dict.fromkeys(frames):
                add(directory / name)
            if kind == 'unowned-symbol':
                detail = directory / 'independent-unexpected-symbols.json'
                if detail.is_file():
                    try:
                        data = json.loads(detail.read_text())
                        excerpt = [r for r in data.get('measured', [])
                                   if r.get('status') == 'mismatch'][:3]
                        arcname = str(directory.relative_to(shard) / 'unexpected-excerpt.json')
                        archive.writestr(arcname, json.dumps(excerpt, indent=2) + '\n')
                        for row in excerpt:
                            add(directory / row['frame'])
                    except (ValueError, OSError, KeyError):
                        pass
    summary['archive_bytes_uncompressed'] = total
    summary['archive'] = str(output)
    return summary


def main():
    args = sys.argv[1:]
    publication_status = args[-1:] == ['--publication-status']
    if publication_status:
        args = args[:-1]
    if len(args) != 2:
        raise SystemExit('Usage: package_notation_diagnostics.py SHARD_DIRECTORY ZIP_PATH [--publication-status]')
    with TerminationSignals() as signals, signals.defer():
        try:
            result = package(Path(args[0]), Path(args[1]))
            print('Saved ' + result['archive'], flush=True)
            print('Common error families:', dict(result['error_counts'].most_common(8)), flush=True)
        except Exception as exc:
            print(f'Could not package diagnostics: {exc}', file=sys.stderr, flush=True)
            return 1 if publication_status else signals.exit_status or 1
        # The outer driver already owns the audit's first-signal status.
        # Report publication success independently, so a later, different
        # signal cannot turn a completed archive into a false failure message.
        return 0 if publication_status else signals.exit_status


if __name__ == '__main__':
    sys.exit(main())
