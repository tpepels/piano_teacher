#!/usr/bin/env python3
"""Headless original-source semantic evidence, independently of screenshot jobs.

One CI artifact: --index I --hand H --out phase3-semantic-report-I-H
Whole corpus: --all --all-hands --out /tmp/phase3-semantics
`passed` means no mismatches; `complete` also requires every ledger row verified.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata as package_metadata
import json
from pathlib import Path
import platform
import sys

# Also support direct script execution from a source checkout.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from piano_teacher.importing.pieces import import_piece
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.semantic_contract import (
    _Ledger, combine_reports, verify_generated_contract, verify_midi_performance,
    verify_musicxml_contract, source_inventory,
)
from scripts.notation_release_provenance import current_provenance

# Same pinned ordering as audit_phase3_whole_pieces, without importing its
# screenshots, native assets, Verovio or Godot orchestration. The manifest is
# the shared reference inventory; no filesystem discovery selects easy scores.
BUNDLED_MIDI = (
    'Ala_–_Joep_Beving.midi',
    'Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi',
    'Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi',
    'Danny_Boy(Bill_Evans_Ver_).midi',
    'Merry-Go-Round-of-Life.midi',
    'Peace_Piece_-_Bill_Evans_(Piano_Solo).midi',
    'Waltz_for_Debby.midi',
)
MANIFEST = json.loads((ROOT / 'tests/fixtures/musical_fidelity/manifest.json').read_text())
MUSICXML_REFERENCE = tuple('tests/fixtures/musical_fidelity/' + c['file']
                          for c in MANIFEST['supported'] if c['file'].endswith('.musicxml'))
ALL_SOURCES = BUNDLED_MIDI + MUSICXML_REFERENCE


def source_path(name: str) -> Path:
    return ROOT / (name if '/' in name else 'midi/' + name)


def _environment() -> dict:
    packages = {}
    for package in ('piano-teacher', 'mido', 'music21'):
        try:
            packages[package] = package_metadata.version(package)
        except package_metadata.PackageNotFoundError:
            packages[package] = None
    return dict(python=dict(version=platform.python_version(), implementation=platform.python_implementation(),
                            executable=sys.executable), packages=packages, platform=platform.platform())


def audit_source(name: str, *, source_index: int, hand: str = 'both',
                 artifact_dir: Path | None = None) -> dict:
    path = source_path(name)
    metadata = dict(schema_version=1, verification_kind='semantic', source_index=source_index,
                    source=name, source_sha256=None, hand=hand, environment=_environment(), artifacts={},
                    provenance=current_provenance())
    if artifact_dir is not None:
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
    inventory = []

    def retain(key, filename, data):
        if artifact_dir is not None:
            (artifact_dir / filename).write_bytes(data)
            metadata['artifacts'][key] = dict(path=filename, sha256=hashlib.sha256(data).hexdigest())

    try:
        source_bytes = path.read_bytes()
        metadata['source_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        original_name = 'original' + path.suffix.lower()
        retain('original', original_name, source_bytes)
        captured = artifact_dir / original_name if artifact_dir is not None else path
        inventory = source_inventory(captured)
        piece, _ = import_piece(captured)
        phrase = Phrase(1, 1, len(piece.bar_boundaries)-1, piece.bar_boundaries[0],
                        piece.bar_boundaries[-1], piece.notes)
        score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes, barlines=piece.barlines,
            source_musicxml=piece.source_musicxml,
            default_clefs=infer_piece_clefs(piece.notes) if not piece.source_musicxml else None)
        retain('generated', 'generated.musicxml', score.musicxml.encode('utf-8'))
        model = build_score_model(score, boundaries=piece.bar_boundaries, hand=hand)
        if path.suffix.lower() in ('.mid', '.midi'):
            # Observed warning input is audited against independently decoded
            # source dispositions, never treated as a proof assertion.
            model['import_warnings'] = list(piece.import_warnings)
        retain('native', 'model.json', (json.dumps(model, indent=2) + '\n').encode('utf-8'))
        if path.suffix.lower() in ('.mid', '.midi'):
            midi_report = verify_midi_performance(captured, model, hand=hand,
                                                   generated_xml=score.musicxml)
            result = combine_reports(midi_report,
                                     verify_generated_contract(score.musicxml, model))
            result['midi_transcription_rules'] = midi_report['midi_transcription_rules']
            retain('midi_transcription_rules', 'midi-transcription-rules.json',
                   (json.dumps(result['midi_transcription_rules'], indent=2) + '\n').encode('utf-8'))
        else:
            result = verify_musicxml_contract(source_bytes.decode('utf-8'), score.musicxml,
                                              model, hand=hand)
        result.update(original_attack_count=len(piece.notes),
                      generated_event_count=len(model['notation_events']),
                      generated_musicxml_sha256=hashlib.sha256(score.musicxml.encode()).hexdigest(),
                      import_warnings=list(piece.import_warnings), source_inventory=inventory)
        return {**metadata, **result}
    except Exception as exc:
        # A runtime failure is evidence, never an omitted corpus case.
        ledger = _Ledger()
        ledger.add('pipeline', 'runtime_error', dict(id=f'source:{source_index}'),
                   'auditable original/generated/native score', f'{type(exc).__name__}: {exc}')
        # Preserve the original denominator at the producer as well as at the
        # independent aggregator. An importer/model crash cannot erase source
        # obligations from a standalone case artifact.
        ledger.elements.extend({**row, 'status': 'unsupported'
                                if row['construct']=='midi_written_transcription' else 'unverified',
                                'reason': f'Pipeline failed before verification: {type(exc).__name__}: {exc}'}
                               for row in inventory)
        return {**metadata, **ledger.report(), 'source_inventory': inventory,
                'runtime_error': f'{type(exc).__name__}: {exc}'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--index', type=int, help='Zero-based pinned corpus index')
    parser.add_argument('--hand', choices=('both', 'right', 'left'), default='both')
    parser.add_argument('--all-hands', action='store_true')
    args = parser.parse_args(argv)
    if args.index is not None and not 0 <= args.index < len(ALL_SOURCES):
        parser.error(f'Index outside 0..{len(ALL_SOURCES)-1}')
    indices = range(len(ALL_SOURCES)) if args.all else (args.index,)
    hands = ('both', 'right', 'left') if args.all_hands else (args.hand,)
    reports = []
    for index in indices:
        for hand in hands:
            destination = args.out if not args.all and not args.all_hands else (
                args.out / f'phase3-semantic-report-{index}-{hand}')
            destination.mkdir(parents=True, exist_ok=True)
            report = audit_source(ALL_SOURCES[index], source_index=index, hand=hand,
                                  artifact_dir=destination)
            (destination / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
            reports.append(report)
            print(f'SEMANTIC {index} {hand} {report["source"]}: '
                  f'passed={report["passed"]} complete={report["complete"]} '
                  f'coverage={report["coverage"]}', flush=True)
    if args.all or args.all_hands:
        aggregate = dict(schema_version=1, verification_kind='semantic-matrix',
                         passed=all(r['passed'] for r in reports),
                         complete=len(reports) == len(ALL_SOURCES)*3 and
                         all(r['complete'] for r in reports),
                         scores_total=len(ALL_SOURCES), scores=reports)
        (args.out / 'summary.json').write_text(json.dumps(aggregate, indent=2) + '\n')
    return int(any(not r['passed'] for r in reports))


if __name__ == '__main__':
    raise SystemExit(main())
