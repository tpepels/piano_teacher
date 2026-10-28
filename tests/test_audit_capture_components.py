"""Capture ownership contracts, exercised without the audit coordinator."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG


def component(name):
    try:
        return importlib.import_module('scripts.audits.' + name)
    except ModuleNotFoundError as exc:
        pytest.fail(f'Independently callable capture component is missing: {exc.name}')


def retained_capture(folder, *, config=CANONICAL_CAPTURE_CONFIG):
    folder.mkdir(parents=True, exist_ok=True)
    screenshots = []
    for name in ('native-0.00000.png', 'rest-without-0-0.00000.png',
                 'repeat-0.00000.png', 'restored-0.00000.png'):
        content = ('actual ' + name).encode()
        (folder / name).write_bytes(content)
        screenshots.append(dict(file=name, sha256=hashlib.sha256(content).hexdigest()))
    manifest = dict(renderer_dependencies_sha256='deps', godot='engine',
                    screenshots=screenshots)
    if config is not None:
        manifest['capture_config'] = config
    (folder / 'capture-manifest.json').write_text(json.dumps(manifest))
    return manifest


@pytest.mark.parametrize('tamper', [None, 'bytes', 'extra', 'missing', 'duplicate',
                                  'dependencies', 'engine', 'config'])
def test_store_validates_exact_capture_inventory_and_producer(tmp_path, tamper):
    store = component('capture_store')
    manifest = retained_capture(tmp_path)
    if tamper == 'bytes':
        (tmp_path / 'native-0.00000.png').write_bytes(b'changed')
    elif tamper == 'extra':
        (tmp_path / 'repeat-9.00000.png').write_bytes(b'unrecorded')
    elif tamper == 'missing':
        (tmp_path / 'restored-0.00000.png').unlink()
    elif tamper == 'duplicate':
        manifest['screenshots'].append(manifest['screenshots'][0])
    elif tamper == 'dependencies':
        manifest['renderer_dependencies_sha256'] = 'old'
    elif tamper == 'engine':
        manifest['godot'] = 'old'
    elif tamper == 'config':
        manifest.pop('capture_config')
    (tmp_path / 'capture-manifest.json').write_text(json.dumps(manifest))
    if tamper:
        with pytest.raises(AssertionError):
            store.validate_capture_manifest(tmp_path, dependency_hash='deps', godot_version='engine')
    else:
        store.validate_capture_manifest(tmp_path, dependency_hash='deps', godot_version='engine')


def test_store_resumes_publication_from_intact_staging_and_publishes_manifest_last(tmp_path):
    store = component('capture_store')
    out = tmp_path / 'case'
    out.mkdir()
    staging = tmp_path / '.capture-case-attempt'
    retained_capture(staging)
    for name in ('fixture.json', 'score.musicxml', 'verovio-0.svg', 'verovio-0.png',
                 'native-overlay-report.json', 'godot.log'):
        (staging / name).write_text('current ' + name)
    for name in ('native-9.00000.png', 'rest-without-9.png', 'repeat-9.png',
                 'restored-9.png', 'verovio-9.svg', 'verovio-9.png'):
        (out / name).write_text('old')
    (out / 'case-result.json').write_text('existing checkpoint')
    (out / 'capture-publish.json').write_text(json.dumps(dict(staging=str(staging))))
    copied = []

    def interrupted_copy(source, destination):
        if copied:
            raise OSError('interrupted publication')
        store.copy_capture_file(source, destination)
        copied.append(destination.name)

    with pytest.raises(OSError, match='interrupted publication'):
        store.recover_capture_publish(out, copy_file=interrupted_copy)
    assert staging.is_dir() and (out / 'capture-publish.json').is_file()
    copied.clear()

    def tracked_copy(source, destination):
        store.copy_capture_file(source, destination)
        copied.append(destination.name)

    store.recover_capture_publish(out, copy_file=tracked_copy)
    assert copied[-1] == 'capture-manifest.json'
    assert not staging.exists() and not (out / 'capture-publish.json').exists()
    assert (out / 'case-result.json').read_text() == 'existing checkpoint'
    assert not list(out.glob('*9*'))
    store.validate_capture_manifest(out, dependency_hash='deps', godot_version='engine')


@pytest.mark.parametrize('invalid', ['foreign', 'corrupt'])
def test_store_rejects_invalid_staging_before_removing_existing_evidence(tmp_path, invalid):
    store = component('capture_store')
    out = tmp_path / 'case'
    out.mkdir()
    frame = out / 'native-0.00000.png'
    frame.write_bytes(b'previous valid capture')
    staging = tmp_path / ('.capture-other-attempt' if invalid == 'foreign' else '.capture-case-attempt')
    retained_capture(staging)
    if invalid == 'corrupt':
        (staging / 'native-0.00000.png').write_bytes(b'broken')
    (out / 'capture-publish.json').write_text(json.dumps(dict(staging=str(staging))))
    with pytest.raises(AssertionError):
        store.recover_capture_publish(out)
    assert frame.read_bytes() == b'previous valid capture'
    assert (out / 'capture-publish.json').exists()


def test_store_preserves_historical_transaction_but_refuses_current_reuse(tmp_path):
    store = component('capture_store')
    out = tmp_path / 'case'
    out.mkdir()
    staging = tmp_path / '.capture-case-historical'
    retained_capture(staging, config=None)
    (out / 'capture-publish.json').write_text(json.dumps(dict(staging=str(staging))))
    store.recover_capture_publish(out)
    assert (out / 'native-0.00000.png').exists()
    with pytest.raises(AssertionError, match='capture configuration'):
        store.validate_capture_manifest(out, dependency_hash='deps', godot_version='engine')


@pytest.fixture
def producer(tmp_path):
    root = tmp_path / 'project'
    (root / 'tests/godot').mkdir(parents=True)
    (root / 'tests/godot/native_verovio_overlay.gd').write_text('extends SceneTree\n')
    (root / 'godot/notation').mkdir(parents=True)
    (root / 'godot/notation/view.gd').write_text('extends Control\n')
    binary = tmp_path / 'godot'
    binary.write_text('#!' + sys.executable + '\n' + '''import json, sys
from pathlib import Path
if sys.argv[1:] == ['--version']:
    print('engine')
    sys.exit(0)
out = Path(sys.argv[-1])
data = json.loads(Path(sys.argv[-2]).read_text())
(out / 'invocation.json').write_text(json.dumps(sys.argv[1:]))
(out / 'native-0.00000.png').write_bytes(b'fresh framebuffer')
(out / 'native-overlay-report.json').write_text('{"frames":[]}')
print('renderer stderr', file=sys.stderr)
print('NATIVE_VEROVIO_OVERLAY_FAILURES:0')
sys.exit(data.get('test_exit', 0))
''')
    binary.chmod(0o755)
    payload = dict(model={}, sample_beats=[0.], assets={})
    return root, str(binary), payload


def test_runner_invokes_godot_in_staging_and_produces_reusable_evidence(tmp_path, producer):
    runner = component('capture_runner')
    store = component('capture_store')
    root, godot, payload = producer
    out = tmp_path / 'case'
    stages = []
    data = runner.capture(out, godot, payload=payload, xml='<score-partwise/>', pages=[],
                          root=root, all_symbols=True, record_stage=stages.append)
    args = json.loads((out / 'invocation.json').read_text())
    assert args[:-2] == ['--path', str(root / 'godot'), '--rendering-method', 'gl_compatibility',
                        '--windowed', '--resolution', '16x16', '--position', '-16384,-16384',
                        '--disable-vsync', '--max-fps', '0', '--audio-driver', 'Dummy',
                        '--script', str(root / 'tests/godot/native_verovio_overlay.gd'), '--']
    staging = Path(args[-1])
    assert staging.parent == out.parent and staging.name.startswith('.capture-case-')
    assert args[-2] == str(staging / 'fixture.json') and not staging.exists()
    assert stages == ['capture']
    assert data['capture_config'] == CANONICAL_CAPTURE_CONFIG
    assert 'capture_config' not in payload and 'capture_protocol_sha256' not in payload
    assert json.loads((out / 'fixture.json').read_text()) == data
    assert (out / 'score.musicxml').read_text() == '<score-partwise/>'
    assert 'renderer stderr' in (out / 'godot.log').read_text()
    store.validate_capture_manifest(out, dependency_hash=store.capture_dependency_hash(root),
                                    godot_version='engine')


def test_runner_failure_retains_previous_capture_and_partial_diagnostics(tmp_path, producer):
    runner = component('capture_runner')
    root, godot, payload = producer
    out = tmp_path / 'case'
    retained_capture(out)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    payload['test_exit'] = 7
    with pytest.raises(AssertionError, match='Actual native renderer failed'):
        runner.capture(out, godot, payload=payload, xml='<score/>', pages=[], root=root,
                       all_symbols=True)
    assert {name: (out / name).read_bytes() for name in before} == before
    attempt, = out.glob('capture-incomplete-*')
    assert (attempt / 'native-0.00000.png').read_bytes() == b'fresh framebuffer'
    assert 'renderer stderr' in (attempt / 'godot.log').read_text()
    assert 'AssertionError' in (attempt / 'capture-error.txt').read_text()
    assert not (out / 'capture-publish.json').exists()


@pytest.mark.parametrize('tamper', [None, 'fixture', 'xml', 'pixels', 'config'])
def test_runner_reuses_only_current_matching_provenance(tmp_path, producer, monkeypatch, tamper):
    runner = component('capture_runner')
    store = component('capture_store')
    root, godot, payload = producer
    out = tmp_path / 'case'
    options = dict(payload=payload, xml='<score/>', pages=[], root=root, all_symbols=True)
    runner.capture(out, godot, **options)
    if tamper == 'fixture':
        (out / 'fixture.json').write_text('{}')
    elif tamper == 'xml':
        (out / 'score.musicxml').write_text('<changed/>')
    elif tamper == 'pixels':
        (out / 'native-0.00000.png').write_bytes(b'changed')
    elif tamper == 'config':
        payload['capture_config'] = {'mode': 'incompatible'}

    def forbidden_capture(*_, **__):
        pytest.fail('Reuse must never invoke Godot capture')

    monkeypatch.setattr(runner.subprocess, 'run', forbidden_capture)
    monkeypatch.setattr(runner.subprocess, 'check_output', lambda *_, **__: 'engine')
    if tamper:
        with pytest.raises(store.CaptureProvenanceError):
            runner.capture(out, godot, **options, reuse_captures=True)
    else:
        runner.capture(out, godot, **options, reuse_captures=True)


def test_capture_components_do_not_import_coordinator():
    component('capture_runner')
    result = subprocess.run([sys.executable, '-c',
        'import sys; from scripts.audits import capture_runner, capture_store; '
        'assert "scripts.check_native_verovio_overlay" not in sys.modules'],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('change', ['edit', 'add', 'remove'])
def test_verification_identity_includes_all_extracted_audit_modules(tmp_path, monkeypatch, change):
    from scripts import check_native_verovio_overlay as audit
    (tmp_path / 'scripts/audits/nested').mkdir(parents=True)
    (tmp_path / 'piano_teacher').mkdir()
    (tmp_path / 'tests/fixtures/musical_fidelity').mkdir(parents=True)
    (tmp_path / 'scripts/check_native_verovio_overlay.py').write_text('# coordinator\n')
    (tmp_path / 'tests/fixtures/musical_fidelity/manifest.json').write_text('{}')
    module = tmp_path / 'scripts/audits/nested/capture_store.py'
    module.write_text('# store version one\n')
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'capture_dependency_hash', lambda: 'renderer')
    before = audit.verification_inputs_hash(())
    if change == 'edit':
        module.write_text('# store version two\n')
    elif change == 'add':
        (module.parent / 'capture_runner.py').write_text('# runner\n')
    else:
        module.unlink()
    assert audit.verification_inputs_hash(()) != before
