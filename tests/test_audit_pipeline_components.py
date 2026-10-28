"""Contracts for case planning, batch progress and strict proof orchestration."""
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.audits.case_types import AuditCase


def component(name):
    try:
        return importlib.import_module('scripts.audits.' + name)
    except ModuleNotFoundError as exc:
        pytest.fail(f'Independent audit pipeline component is missing: {exc.name}')


def test_plans_keep_phase_order_source_windows_and_exact_job_identity(tmp_path, monkeypatch):
    planning = component('planning')
    catalog = component('case_catalog')
    path = Path('/library/source.mid')
    piece = SimpleNamespace(bar_boundaries=(0., 4., 8.), notes=())
    stage = AuditCase('stage', str(path), 1, 1)
    focused = AuditCase('focused', str(path), 1, 2)
    monkeypatch.setattr(catalog, 'curriculum_cases', lambda *_: ((stage, None, None),))
    plan = planning.plan_source(path, piece, source_index=3, max_bars=1,
        shard_index=0, shard_count=1, focused_cases=(focused,))
    assert plan.measure_count == 2 and plan.case_count == 8
    options = dict(out=tmp_path, inputs_hash='inputs', runtime={'godot': 'engine'},
                   godot='godot', reuse_captures=True)
    phases = {phase: planning.case_jobs((plan,), phase, **options)
              for phase in ('originals', 'focused', 'stages')}
    assert [job['case'].name for job in phases['originals']] == [
        f'original-{bar:04d}-{bar:04d}-{hand}'
        for bar in (1, 2) for hand in ('right', 'left', 'both')]
    assert [job['case'].name for job in phases['focused']] == ['focused']
    assert [job['case'].name for job in phases['stages']] == ['stage']
    first = phases['originals'][0]
    assert first['directory'] == tmp_path / '03-source/original-0001-0001-right'
    assert first['key'] == '0e71a2eb3b12788ca378bd0ac907335193e620c01b6e39032fb793507e35380b'
    assert all(job['focused'] for job in phases['focused'])
    assert all(not job['focused'] for job in phases['originals'] + phases['stages'])
    assert all(job['reuse_captures'] for jobs in phases.values() for job in jobs)


def test_source_plans_partition_every_case_without_losing_silent_bars(monkeypatch):
    planning = component('planning')
    catalog = component('case_catalog')
    monkeypatch.setattr(catalog, 'curriculum_cases', lambda *_: ())
    path = Path('/library/silence.mid')
    piece = SimpleNamespace(bar_boundaries=(0., 4., 8., 12.), notes=())
    plans = [planning.plan_source(path, piece, source_index=0, max_bars=1,
        shard_index=i, shard_count=5, focused_cases=()) for i in range(5)]
    cases = [case.name for plan in plans for case, _, _ in plan.originals]
    assert len(cases) == len(set(cases)) == 9
    assert {bar for plan in plans for case, _, _ in plan.originals
            for bar in range(case.first_bar, case.last_bar + 1)} == {1, 2, 3}


def test_batch_checkpoint_ignores_other_case_identity_and_writes_pending_counts(tmp_path):
    checkpoints = component('batch_checkpoint')
    directory = tmp_path / 'source/case'
    directory.mkdir(parents=True)
    (directory / 'case-state.json').write_text(json.dumps(dict(
        key='previous', stage='old-stage', pid=123, started_at=0)))
    summary = dict(cases_expected=4, cases_checked=1)
    checkpoint = checkpoints.BatchCheckpoint(tmp_path, summary)
    job = dict(case=AuditCase('case', 'source.mid', 1, 1), directory=directory, key='current')
    checkpoint((job,), force=True)
    saved = json.loads((tmp_path / 'summary.json').read_text())
    assert saved['cases_pending'] == 3
    assert saved['active_cases'] == [dict(case='case', directory='source/case')]
    (directory / 'case-state.json').write_text(json.dumps(dict(
        key='current', stage='noteheads', pid=456, started_at=0)))
    checkpoint((job,), force=True)
    active = json.loads((tmp_path / 'summary.json').read_text())['active_cases'][0]
    assert active['stage'] == 'noteheads' and active['pid'] == 456


@pytest.mark.parametrize('ambiguous_note', [False, True])
def test_proof_execution_preserves_stage_order_unknowns_and_mismatch_precedence(tmp_path, monkeypatch,
                                                                            ambiguous_note):
    owner = component('proof_execution')
    from piano_teacher.notation import (phase3_pixels, symbol_pixel_proof, connector_pixels,
        feature_pixels, semantic_contract, visual_coverage, extra_symbol_pixels)
    notes = dict(passed=True, failures=[], measured=[dict(status='unverified', reason='ambiguous')]
                 if ambiguous_note else [])
    monkeypatch.setattr(phase3_pixels, 'verify_all_notehead_pixels', lambda *_, **__: notes)
    monkeypatch.setattr(phase3_pixels, 'verify_all_rest_pixels', lambda *_, **__: dict(
        passed=True, failures=[], measured=[]))
    monkeypatch.setattr(phase3_pixels, 'verify_scroll_pixels', lambda *_, **__: dict(measured=[]))
    for module, name in ((symbol_pixel_proof, 'verify_connector_pixels'),
                         (connector_pixels, 'verify_beam_pixels'),
                         (connector_pixels, 'verify_tuplet_pixels')):
        monkeypatch.setattr(module, name, lambda *_, **__: dict(coverage={}, observations=[]))
    for name in ('verify_note_feature_pixels', 'verify_ledger_pixels'):
        monkeypatch.setattr(feature_pixels, name, lambda *_, **__: dict(
            complete=True, coverage={}, measured=[]))
    monkeypatch.setattr(semantic_contract, 'verify_generated_contract',
                        lambda *_: dict(elements=[]))
    elements = [dict(id='bad', construct='stem', status='mismatch', reason='bad stem',
                     source=dict(measure=1), evidence={}),
                dict(id='resolved', construct='barline', status='unverified', source={}, evidence={}),
                dict(id='midi', construct='midi_written_transcription', status='unverified',
                     source={}, evidence={})]
    monkeypatch.setattr(visual_coverage, 'visual_elements', lambda *_, **__: elements)
    counted = []
    def count(rows):
        counted.extend(row['id'] for row in rows)
        return {'checked_ids': list(counted)}
    monkeypatch.setattr(visual_coverage, 'coverage_counts', count)
    monkeypatch.setattr(feature_pixels, 'verify_structure_pixels', lambda *_, **__: [
        dict(id=ident, status='verified', reason='structure', evidence={})
        for ident in ('bad', 'resolved')])
    monkeypatch.setattr(extra_symbol_pixels, 'verify_extra_symbol_pixels', lambda *_, **__: dict(
        measured=[dict(region='viewport', status='unverified', evidence={})],
        coverage=dict(frames=1, measured_frames=1, initial_viewport=True, terminal_viewport=True,
            motion_status='verified', expected_heads=0, bound_heads=0, expected_rests=0, bound_rests=0)))
    (tmp_path / 'score.musicxml').write_text('<score/>')
    stages = []
    result = owner.execute_proofs(tmp_path, AuditCase('case', 'source.mid', 1, 1),
        model={'notation_events': []}, original_xml='', record_stage=stages.append)
    assert stages == ['noteheads', 'rests', 'scroll', 'ties-and-slurs', 'beams', 'tuplets',
                      'note-features', 'ledger-lines', 'semantics', 'structure', 'unexpected-symbols']
    assert counted == ['bad', 'resolved']
    assert result.nonverified_symbols == {'stem:mismatch': 1}
    assert len(result.errors) == 1 + int(ambiguous_note)
    assert any('bad stem' in error for error in result.errors)
    if ambiguous_note:
        assert any('notehead: unverified' in error for error in result.errors)
    saved = json.loads((tmp_path / 'independent-symbols.json').read_text())
    assert saved[0]['status'] == 'mismatch' and saved[1]['status'] == 'verified'
    assert saved[2]['status'] == 'unverified'
    assert {p.name for p in tmp_path.glob('*.json')} == {
        'independent-motion.json', 'independent-rests.json', 'independent-pixels.json',
        'independent-connectors.json', 'independent-beams.json', 'independent-tuplets.json',
        'independent-ledgers.json', 'independent-features.json', 'semantics.json',
        'independent-structure.json', 'independent-symbols.json', 'independent-unexpected-symbols.json'}


@pytest.mark.parametrize('all_symbols', [False, True])
@pytest.mark.parametrize('strict', [False, True])
@pytest.mark.parametrize('corrupt', [False, True])
def test_public_case_composition_publishes_strict_failures_and_rejects_missing_ink(
        tmp_path, monkeypatch, all_symbols, strict, corrupt):
    from PIL import Image, ImageDraw
    from scripts import check_native_verovio_overlay as cli
    execution = component('case_execution')
    inputs = component('case_inputs')
    proof = component('proof_execution')
    model = dict(active_hand='both', notes=[dict(id='n')],
        measures=[dict(number=1, start_beat=0.)], notation_events=[dict(
            id='n', kind='note', note_type='quarter', dots=0, staff='right',
            is_attack=True, source_id='n')])
    payload = dict(model=model, xml='<score/>', sample_beats=[.5],
                   source_errors=['Source witness remains unverified'])
    engraving = SimpleNamespace(pages=[], layout={'notes': [dict(id='n', page=0, x=.5, y=.5)]})
    monkeypatch.setattr(inputs, 'capture_clocks', lambda _: [0.])
    proof_calls = []

    def prove(*_, **__):
        proof_calls.append(True)
        return proof.ProofResult(['Independent symbol remains unverified'],
            {'symbols': {'stem:unverified': 1}}, {'stem:unverified': 1})

    monkeypatch.setattr(proof, 'execute_proofs', prove)

    def capture(out, godot, *, payload, xml, record_stage, **options):
        record_stage('capture')
        (out / 'score.musicxml').write_text(xml)
        photo = Image.new('RGB', (120, 120), (19, 44, 35))
        if not corrupt:
            ImageDraw.Draw(photo).ellipse((45, 45, 55, 53), fill=(234, 244, 237))
        photo.save(out / 'native-0.png')
        photo.save(out / 'verovio-0.png')
        (out / 'native-overlay-report.json').write_text(json.dumps(dict(
            density=80., staff_gap=10., staff_centers={'right': 50., 'left': 80.},
            unavoidable_rest_overlaps=0, frames=[dict(file='native-0.png', clock=0.,
                noteheads={'n': [50., 50.]}, expected_noteheads={'n': 50.}, rests=[])])))
        assert payload['sample_beats'] == ([0.] if all_symbols else [.5])
        return dict(payload)

    monkeypatch.setattr(component('capture_runner'), 'capture', capture)
    case = AuditCase('case', 'source.mid', 1, 1)
    options = dict(prepared=(payload, engraving), all_symbols=all_symbols, strict=strict)
    if strict:
        with pytest.raises(AssertionError, match='Source witness remains unverified'):
            cli.run(tmp_path, 'godot', case, **options)
    else:
        assert not cli.run(tmp_path, 'godot', case, **options)['passed']
    saved = json.loads((tmp_path / 'audit.json').read_text())
    assert saved['errors'][0] == 'Source witness remains unverified'
    assert len(saved['errors']) == 1 + int(corrupt) + int(all_symbols)
    assert any('Missing rendered native notehead' in error for error in saved['errors']) == corrupt
    assert saved['nonverified_symbols'] == ({'stem:unverified': 1} if all_symbols else {})
    assert len(proof_calls) == int(all_symbols)
    assert saved['native_notehead_samples'] == saved['registered_noteheads'] == 1
    assert payload['sample_beats'] == [.5] and payload['xml'] == '<score/>'
    assert not (tmp_path / 'case-state.json').exists()
    assert cli.run is execution.run


def test_capture_runner_has_no_legacy_coordinator_adapters():
    runner = component('capture_runner')
    parameters = inspect.signature(runner.capture).parameters
    assert 'dependency_hash' not in parameters
    assert 'recover_publish' not in parameters


def test_cli_exports_declared_api_and_live_fixture_clients_only():
    from scripts import check_native_verovio_overlay as cli
    assert set(cli.__all__) == {'AuditCase', 'fixture', 'run', 'audit_library',
                               'execute_case_jobs', 'ROOT', 'AUTUMN_FILE', 'capture_clocks'}
    for obsolete in ('CANONICAL_CAPTURE_CONFIG', 'capture_dependency_hash', 'context_first_bar',
                     'readability_errors', 'feature_errors', 'library_sources', 'import_piece'):
        assert not hasattr(cli, obsolete)


def test_pipeline_owners_import_without_cli():
    component('batch_run')
    component('case_execution')
    result = subprocess.run([sys.executable, '-c',
        'import sys; from scripts.audits import planning, batch_run, case_execution, proof_execution; '
        'assert "scripts.check_native_verovio_overlay" not in sys.modules'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_verification_identity_uses_the_requested_source_root(tmp_path):
    identity = component('verification_inputs')
    root = tmp_path/'isolated-repository'
    for name in ('scripts/check_native_verovio_overlay.py', 'scripts/audits/proof.py',
                 'piano_teacher/domain.py', 'tests/fixtures/musical_fidelity/manifest.json',
                 'tests/godot/native_verovio_overlay.gd', 'godot/notation/native/view.gd',
                 'source.musicxml'):
        path = root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('before')
    sources = [root/'source.musicxml']
    before = identity.verification_inputs_hash(sources,root=root)
    assert before == identity.verification_inputs_hash(sources,root=root)
    (root/'godot/notation/native/view.gd').write_text('changed renderer in the requested repository')
    assert identity.verification_inputs_hash(sources,root=root) != before
