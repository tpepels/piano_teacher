#!/usr/bin/env python3
"""Discover every local MIDI file, then reuse the independent whole-piece audits.

This supplemental corpus never replaces the pinned Phase 3 release corpus.
Freeze discovery first; added, missing or modified files invalidate that snapshot.
All modes and both categories remain required even during incremental execution.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.aggregate_phase3_corpus import aggregate, HANDS


def discover(directory: Path) -> dict:
    directory = Path(directory)
    sources = []
    for path in sorted(directory.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.mid', '.midi'):
            continue
        if path.is_symlink():
            raise ValueError(f'Symlinked MIDI source is not immutable: {path}')
        name = path.relative_to(directory).as_posix()
        source = name if '/' not in name else 'midi/' + name
        data = path.read_bytes()
        sources.append(dict(source_index=len(sources), source=source,
                            source_sha256=sha256(data).hexdigest(), size_bytes=len(data)))
    if not sources:
        raise ValueError(f'No MIDI sources found in {directory}')
    return dict(schema_version=1, report_kind='phase5_source_inventory',
                required_cases=len(sources)*len(HANDS)*2, sources=sources)


def validate_inventory(inventory: dict, directory: Path) -> list[str]:
    errors = []
    if not isinstance(inventory, dict):
        return ['Source inventory must be an object']
    if type(inventory.get('schema_version')) is not int or inventory['schema_version'] != 1:
        errors.append('Unsupported source inventory schema')
    if inventory.get('report_kind') != 'phase5_source_inventory':
        errors.append('Wrong source inventory kind')
    rows = inventory.get('sources')
    if not isinstance(rows, list) or not rows:
        return errors + ['Missing source inventory']
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or type(row.get('source_index')) is not int or row['source_index'] != i:
            errors.append(f'Invalid source identity at index {i}')
    try:
        actual = discover(directory)
    except (OSError, ValueError) as exc:
        return errors + [str(exc)]
    if rows != actual['sources']:
        errors.append('Discovered source names, order, hashes or sizes differ from frozen inventory')
    if type(inventory.get('required_cases')) is not int or inventory['required_cases'] != actual['required_cases']:
        errors.append('Wrong source inventory case denominator')
    return errors


def summarize(inventory: dict, reports: Path, *, kind: str = 'complete') -> dict:
    from scripts.audit_native_release import grouped, empty_coverage, add_coverage
    errors = validate_inventory(inventory, ROOT / 'midi')
    names = tuple(row['source'] for row in inventory.get('sources', [])
                  if isinstance(row, dict) and isinstance(row.get('source'), str))
    report = aggregate(reports, scores=len(names), kind=kind, source_names=names,
                       source_root=ROOT, include_elements=True)
    report.update(report_kind='phase5_supplemental_notation',
                  supplemental_to_pinned_release_corpus=True,
                  release_ready=False, inventory=inventory, inventory_errors=errors)
    report['errors'] = errors + report['errors']
    categories = {}
    for boundary in (('semantic', 'visual') if kind == 'complete' else (kind,)):
        jobs = [job for job in report['jobs'] if job['verification_kind'] == boundary]
        coverage = empty_coverage()
        for job in jobs:
            add_coverage(coverage, job['coverage'])
        categories[boundary] = dict(coverage=coverage,
            complete=bool(jobs) and all(job['complete'] for job in jobs) and not errors,
            **{f'by_{dimension}': grouped(jobs, dimension)
               for dimension in ('score', 'hand', 'measure', 'feature')})
    report['categories'] = categories
    gaps = report['unverified_elements']
    report['findings'] = {
        'semantic_defects': [row for row in gaps if row['status']=='mismatch'
                             and row['verification_kind']=='semantic'
                             and row['construct'] != 'runtime_error'],
        'visual_defects': [row for row in gaps if row['status']=='mismatch'
                           and row['verification_kind']=='visual'],
        'unsupported_features': [row for row in gaps if row['status']=='unsupported'],
        'framework_limitations': [row for row in gaps if row['status'] in ('unverified','ambiguous')
                                 or row['construct']=='runtime_error'],
    }
    if errors:
        report.update(passed=False, complete=False, status='blocked')
    return report


def audit_visual(name: str, index: int, hand: str, destination: Path,
                 corpus_size: int, *, window_bars: int, reuse: bool) -> dict:
    # Imported only at the visual boundary; semantic audits need no renderer.
    from scripts.audit_phase3_whole_pieces import audit_piece
    from piano_teacher.notation.visual_coverage import coverage_counts, source_inventory
    from scripts.notation_release_provenance import current_provenance
    path = ROOT / (name if '/' in name else 'midi/' + name)
    result, errors = None, []
    godot = shutil.which('godot') or shutil.which('godot4')
    try:
        if not godot:
            raise RuntimeError('Actual Godot renderer is mandatory')
        result = audit_piece(name, destination / 'raw', godot, max_bars=window_bars,
                             hand=hand, reuse_captures=reuse)
        if not result['passed']:
            errors.append(dict(score=name, errors=result['errors']))
        elements = result['visual_elements']
    except Exception as exc:
        errors.append(dict(score=name, error=f'{type(exc).__name__}: {exc}'))
        elements = [dict(row, status='unverified', reason=str(exc))
                    for row in source_inventory(None, hand, source_name=name)]
    return dict(schema_version=1, verification_kind='visual', source=name,
                source_index=index, source_sha256=sha256(path.read_bytes()).hexdigest(),
                hand=hand, passed=not errors,
                complete=bool(elements) and not errors and all(e['status']=='verified' for e in elements),
                scores_total=corpus_size, scores_attempted=[name], scores_passed=int(not errors),
                scores_failed=errors, scores=[result] if result else [],
                elements=elements, coverage=coverage_counts(elements), provenance=current_provenance())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-inventory', type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--kind', choices=('semantic', 'visual', 'complete'), default='complete')
    parser.add_argument('--index', type=int, help='Incremental execution; other cases stay required')
    parser.add_argument('--hand', choices=HANDS, help='Incremental execution; other modes stay required')
    parser.add_argument('--window-bars', type=int, default=4)
    parser.add_argument('--reuse-captures', action='store_true')
    parser.add_argument('--summarize-only', action='store_true')
    args = parser.parse_args(argv)
    if args.write_inventory:
        inventory = discover(ROOT / 'midi')
        args.write_inventory.parent.mkdir(parents=True, exist_ok=True)
        args.write_inventory.write_text(json.dumps(inventory, indent=2, ensure_ascii=False)+'\n')
        print(f"Inventoried {len(inventory['sources'])} MIDI sources, {inventory['required_cases']} required cases")
        return 0
    if not args.inventory or not args.out:
        parser.error('--inventory and --out are required to audit or summarize')
    inventory = json.loads(args.inventory.read_text())
    errors = validate_inventory(inventory, ROOT / 'midi')
    if errors:
        parser.error('; '.join(errors))
    rows = inventory['sources']
    if args.index is not None and not 0 <= args.index < len(rows):
        parser.error('Source index outside frozen inventory')
    if args.window_bars < 1:
        parser.error('--window-bars must be positive')
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.summarize_only:
        selected = rows if args.index is None else [rows[args.index]]
        for row in selected:
            for hand in (HANDS if args.hand is None else (args.hand,)):
                for kind in (('semantic', 'visual') if args.kind == 'complete' else (args.kind,)):
                    prefix = 'phase3-semantic-report' if kind=='semantic' else 'phase3-report'
                    destination = args.out / f'{prefix}-{row["source_index"]}-{hand}'
                    destination.mkdir(parents=True, exist_ok=True)
                    if kind == 'semantic':
                        from scripts.audit_phase3_semantics import audit_source
                        report = audit_source(row['source'], source_index=row['source_index'],
                                              hand=hand, artifact_dir=destination)
                    else:
                        report = audit_visual(row['source'], row['source_index'], hand, destination,
                                              len(rows), window_bars=args.window_bars,
                                              reuse=args.reuse_captures)
                    (destination / 'summary.json').write_text(json.dumps(report, indent=2)+'\n')
                    print(f"{kind} {row['source_index']} {hand}: {report['coverage']}", flush=True)
    result = summarize(inventory, args.out, kind=args.kind)
    (args.out / f'phase5-{args.kind}.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f"Phase 5 {args.kind}: {result['jobs_with_results']}/{result['required_jobs']} reports; "
          f"{result['coverage']}", flush=True)
    return int(not result['complete'])


if __name__ == '__main__':
    raise SystemExit(main())
