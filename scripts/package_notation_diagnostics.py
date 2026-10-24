#!/usr/bin/env python3
"""Package representative native-notation failure evidence in a bounded ZIP."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys
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
    cases = sorted(shard.rglob('audit.json'))
    for audit in cases:
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
               'selected_examples': {kind: str(file.relative_to(shard))
                                     for kind, (file, _) in selections.items()}}
    total = 0
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        included = set()

        def add(path: Path) -> None:
            nonlocal total
            if not path.is_file() or path in included:
                return
            size = path.stat().st_size
            if size > MAX_FILE_BYTES or total + size > MAX_ARCHIVE_BYTES:
                return
            archive.write(path, path.relative_to(shard).as_posix())
            included.add(path)
            total += size

        for name in ('summary.json', 'run.log'):
            add(shard / name)
        archive.writestr('triage-summary.json', json.dumps(summary, indent=2) + '\n')
        for kind, (audit, trigger) in list(selections.items())[:MAX_CASES]:
            directory = audit.parent
            add(audit)
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


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: package_notation_diagnostics.py SHARD_DIRECTORY ZIP_PATH')
    result = package(Path(sys.argv[1]), Path(sys.argv[2]))
    print('Saved ' + result['archive'])
    print('Common error families:', dict(result['error_counts'].most_common(8)))
