"""Supplemental real scores never replace or weaken the pinned release corpus."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import audit_phase5_scores as audit


def midi(path):
    path.write_bytes(bytes.fromhex('4d546864000000060000000101e04d54726b0000000c00903c408360803c4000ff2f00'))
    return path


def test_discovery_covers_all_midi_names_and_preserves_bytes(tmp_path):
    midi(tmp_path / 'Étude.midi')
    midi(tmp_path / 'B.MID')
    (tmp_path / 'readme.txt').write_text('not a score')
    inventory = audit.discover(tmp_path)
    assert [r['source'] for r in inventory['sources']] == ['B.MID', 'Étude.midi']
    assert inventory['required_cases'] == 12
    for row in inventory['sources']:
        assert row['source_sha256'] == hashlib.sha256((tmp_path / row['source']).read_bytes()).hexdigest()
    assert not audit.validate_inventory(inventory, tmp_path)


@pytest.mark.parametrize('mutation', ['add', 'remove', 'modify', 'duplicate', 'renumber'])
def test_inventory_changes_fail_closed(tmp_path, mutation):
    path = midi(tmp_path / 'A.midi')
    inventory = audit.discover(tmp_path)
    if mutation == 'add':
        midi(tmp_path / 'B.midi')
    elif mutation == 'remove':
        path.unlink()
    elif mutation == 'modify':
        path.write_bytes(path.read_bytes() + b'extra')
    elif mutation == 'duplicate':
        inventory['sources'].append(dict(inventory['sources'][0]))
    else:
        inventory['sources'][0]['source_index'] = True
    assert audit.validate_inventory(inventory, tmp_path)


def test_empty_discovery_is_not_a_complete_corpus(tmp_path):
    with pytest.raises(ValueError, match='No MIDI'):
        audit.discover(tmp_path)


def test_missing_reports_restore_independent_original_denominators(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    (root / 'midi').mkdir(parents=True)
    midi(root / 'midi/A.midi')
    monkeypatch.setattr(audit, 'ROOT', root)
    inventory = audit.discover(root / 'midi')
    result = audit.summarize(inventory, tmp_path / 'reports', kind='complete')
    assert not result['complete']
    assert result['required_jobs'] == 6
    assert result['jobs_with_results'] == 0
    assert result['coverage']['unverified'] > 0
    assert result['coverage']['expected'] > 0
    assert len(result['jobs']) == 6
    assert result['release_ready'] is False
    assert result['supplemental_to_pinned_release_corpus'] is True
    assert set(result['categories']) == {'semantic', 'visual'}
    for category in result['categories'].values():
        assert not category['complete']
        for dimension in ('score', 'hand', 'measure', 'feature'):
            assert sum(row['coverage']['expected'] for row in category[f'by_{dimension}']) == category['coverage']['expected']
    assert result['findings']['framework_limitations']


def test_unchanged_counts_cannot_hide_changed_source_bytes(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    (root / 'midi').mkdir(parents=True)
    path = midi(root / 'midi/A.midi')
    monkeypatch.setattr(audit, 'ROOT', root)
    inventory = audit.discover(root / 'midi')
    path.write_bytes(path.read_bytes().replace(b'\x90\x3c', b'\x90\x3d'))
    result = audit.summarize(inventory, tmp_path / 'reports')
    assert result['inventory_errors']
    assert not result['complete'] and not result['release_ready']


def test_visual_runtime_failure_remains_an_explicit_required_case(tmp_path, monkeypatch):
    from scripts import audit_phase3_whole_pieces
    root = tmp_path / 'repo'
    (root / 'midi').mkdir(parents=True)
    midi(root / 'midi/A.midi')
    monkeypatch.setattr(audit, 'ROOT', root)
    monkeypatch.setattr(audit.shutil, 'which', lambda _: 'godot')
    def failure(*args, **kwargs):
        raise RuntimeError('capture failed deliberately')
    monkeypatch.setattr(audit_phase3_whole_pieces, 'audit_piece', failure)
    result = audit.audit_visual('A.midi', 0, 'left', tmp_path, 1, window_bars=4, reuse=False)
    assert not result['passed'] and not result['complete']
    assert result['scores_attempted'] == ['A.midi']
    assert result['coverage']['unverified'] > 0
    assert 'capture failed deliberately' in result['scores_failed'][0]['error']


def test_existing_pinned_corpus_is_not_replaced():
    from scripts.aggregate_phase3_corpus import PINNED_SOURCES
    assert len(PINNED_SOURCES) == 17
    assert PINNED_SOURCES[9].endswith('xml_parallel_tied_voices.musicxml')


def test_absent_detector_is_not_a_proven_unsupported_application_feature():
    row = dict(status='unsupported', verification_kind='visual', construct='stem',
               source=dict(id='n1'), reason='No independent pixel detector for stem')
    findings = audit.classify_findings([row])
    assert findings['unsupported_features'] == []
    assert findings['unsupported_features_assessment'] == 'not_established_by_verification_status'
    assert findings['framework_limitations'] == [row]
    assert not findings['visual_defects'] and not findings['semantic_defects']


def test_phase5_regressions_are_required_release_mutations():
    from scripts.record_notation_mutations import SUITES
    assert {'tests/test_phase5_authored_rests.py', 'tests/test_phase5_beam_metadata.py',
            'tests/test_phase5_midi_contract.py', 'tests/test_phase5_midi_overlaps.py',
            'tests/test_phase5_written_metadata.py'} <= set(SUITES['semantic'])
    assert 'tests/test_phase5_corpus.py' in SUITES['release_contract']
    assert 'tests/test_phase5_staff_detection.py' in SUITES['visual']
    assert 'tests/test_phase5_rest_identity.py' in SUITES['visual']


def test_semantic_runtime_failure_retains_every_original_obligation(tmp_path, monkeypatch):
    from scripts import audit_phase3_semantics as runner
    from piano_teacher.notation.semantic_contract import source_inventory
    def failure(*args, **kwargs):
        raise RuntimeError('deliberate importer failure')
    monkeypatch.setattr(runner, 'import_piece', failure)
    name = runner.ALL_SOURCES[7]
    expected = source_inventory(runner.source_path(name))
    result = runner.audit_source(name, source_index=7, artifact_dir=tmp_path)
    by_id = {row['id']: row for row in result['elements']}
    assert set(row['id'] for row in expected) <= by_id.keys()
    assert all(by_id[row['id']]['status']=='unverified' for row in expected)
    assert result['coverage']['verified'] == 0
    assert not result['passed'] and not result['complete']
