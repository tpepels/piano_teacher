"""Prepare, invoke and retain a Godot capture independently of audit proofs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, Sequence
import uuid

from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG
from piano_teacher.raster import rasterize_score

from . import capture_store
from .capture_store import CaptureProvenanceError, atomic_json

ROOT = Path(__file__).resolve().parents[2]


def capture(out: Path, godot: str, *, payload: dict, xml: str, pages: Sequence[str],
            root: Path = ROOT, all_symbols: bool = False, reuse_captures: bool = False,
            record_stage: Callable[[str], None] | None = None,
            dependency_hash: Callable[[], str] | None = None,
            recover_publish: Callable[[Path], None] | None = None) -> dict:
    """Return the exact fixture payload whose capture was published or reused.

    The optional hash/publication operations preserve the coordinator's legacy
    patch points. They consume no coordinator state. Standalone callers use the
    store directly; a stage recorder is scoped to the caller's case.
    """
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    recover_publish = recover_publish or capture_store.recover_capture_publish
    dependency_hash = dependency_hash or (lambda: capture_store.capture_dependency_hash(root))
    recover_publish(out)
    data = dict(payload)
    if 'capture_config' in data and data['capture_config'] != CANONICAL_CAPTURE_CONFIG:
        raise CaptureProvenanceError('Capture configuration must explicitly select canonical audit mode')
    data['capture_config'] = dict(CANONICAL_CAPTURE_CONFIG)
    capture_sources = [root / 'tests/godot/native_verovio_overlay.gd',
                       *sorted((root / 'godot/notation').rglob('*.gd'))]
    data['capture_protocol_sha256'] = hashlib.sha256(b''.join(
        p.relative_to(root).as_posix().encode() + p.read_bytes()
        for p in capture_sources)).hexdigest()
    dependencies = dependency_hash()
    if reuse_captures:
        try:
            if json.loads((out / 'fixture.json').read_text()) != data or (
                    (out / 'score.musicxml').read_text() != xml):
                raise AssertionError('Cached capture provenance does not match current source/layout/protocol')
            capture_store.validate_capture_manifest(out, dependency_hash=dependencies,
                godot_version=subprocess.check_output([godot, '--version'], text=True).strip())
        except (OSError, ValueError, AssertionError) as exc:
            raise CaptureProvenanceError(str(exc)) from exc

    def write_inputs(directory):
        (directory / 'score.musicxml').write_text(xml, encoding='utf-8')
        (directory / 'fixture.json').write_text(json.dumps(data))
        for page, svg in enumerate(pages):
            (directory / f'verovio-{page}.svg').write_text(svg)
            if not all_symbols:
                (directory / f'verovio-{page}.png').write_bytes(rasterize_score(svg, width=2400))

    if reuse_captures:
        write_inputs(out)
        return data
    if record_stage is not None:
        record_stage('capture')
    staging = Path(tempfile.mkdtemp(prefix='.capture-' + out.name + '-', dir=out.parent))
    try:
        write_inputs(staging)
        result = subprocess.run([
            godot, '--path', str(root / 'godot'), '--rendering-method', 'gl_compatibility',
            '--windowed', '--resolution', '16x16', '--position', '-16384,-16384',
            '--disable-vsync', '--max-fps', '0', '--audio-driver', 'Dummy',
            '--script', str(root / 'tests/godot/native_verovio_overlay.gd'),
            '--', str(staging / 'fixture.json'), str(staging)],
            capture_output=True, text=True, timeout=max(180, 2 * len(data['sample_beats'])))
        (staging / 'godot.log').write_text(result.stdout + result.stderr)
        if dependency_hash() != dependencies:
            raise AssertionError('Renderer dependencies changed during actual capture; rerun the passage')
        assert result.returncode == 0 and 'NATIVE_VEROVIO_OVERLAY_FAILURES:0' in result.stdout, (
            'Actual native renderer failed:\n' + (result.stdout + result.stderr)[-9000:])
        import platform
        import verovio
        captures = [dict(file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                    for pattern in capture_store.SCREENSHOT_PATTERNS
                    for p in sorted(staging.glob(pattern))]
        atomic_json(staging / 'capture-manifest.json', dict(
            capture_config=data['capture_config'],
            capture_protocol_sha256=data['capture_protocol_sha256'],
            renderer_dependencies_sha256=dependencies, python=platform.python_version(),
            verovio=verovio.toolkit().getVersion(),
            godot=subprocess.check_output([godot, '--version'], text=True).strip(),
            screenshots=captures))
        atomic_json(out / 'capture-publish.json', dict(staging=str(staging)))
        recover_publish(out)
    except BaseException as exc:
        if staging.exists() and not (out / 'capture-publish.json').exists():
            (staging / 'capture-error.txt').write_text(f'{type(exc).__name__}: {exc}\n')
            attempt = out / ('capture-incomplete-' + uuid.uuid4().hex[:12])
            staging.rename(attempt)
        raise
    return data
