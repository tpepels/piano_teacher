"""Capture provenance and recoverable artifact publication, without CLI state."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Callable

from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_PATTERNS = ('native-*.png', 'rest-without-*.png', 'repeat-*.png', 'restored-*.png')
CAPTURE_PATTERNS = (*SCREENSHOT_PATTERNS, 'verovio-*.svg', 'verovio-*.png',
                    'capture-manifest.json', 'native-overlay-report.json')


class CaptureProvenanceError(AssertionError):
    """Only invalid producer evidence warrants another Godot capture."""


def atomic_json(path: Path, value: dict) -> None:
    """An interrupted write must leave the last complete checkpoint intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.pending-',
                                         encoding='utf-8', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture_dependency_hash(root: Path = ROOT) -> str:
    """Include shared theme/resources as well as notation-specific scripts."""
    sources = [root / 'tests/godot/native_verovio_overlay.gd']
    sources.extend(p for p in (root / 'godot').rglob('*')
                   if p.is_file() and '.godot' not in p.relative_to(root / 'godot').parts
                   and p.suffix in {'.gd', '.gdshader', '.gdshaderinc', '.tscn', '.tres', '.godot',
                                    '.ttf', '.otf', '.woff', '.woff2', '.png', '.svg'})
    digest = hashlib.sha256()
    for path in sorted(sources):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def validate_capture_manifest(folder: Path, *, dependency_hash: str, godot_version: str,
                              capture_config: dict = CANONICAL_CAPTURE_CONFIG) -> None:
    manifest = json.loads((folder / 'capture-manifest.json').read_text())
    _validate_capture_files(folder, manifest, dependency_hash=dependency_hash,
                            godot_version=godot_version)
    if manifest.get('capture_config') != capture_config:
        raise AssertionError('Cached capture configuration differs from the explicit canonical audit mode')


def _validate_capture_files(folder, manifest, *, dependency_hash, godot_version):
    if manifest.get('renderer_dependencies_sha256') != dependency_hash:
        raise AssertionError('Cached renderer dependencies changed or are unrecorded')
    if manifest.get('godot') != godot_version:
        raise AssertionError('Cached Godot engine version differs from the current engine')
    captures = manifest.get('screenshots')
    if not isinstance(captures, list) or not captures:
        raise AssertionError('Cached capture manifest has no actual screenshot hashes')
    observed = {path.name for pattern in SCREENSHOT_PATTERNS for path in folder.glob(pattern)}
    recorded = [entry.get('file') for entry in captures]
    if len(set(recorded)) != len(recorded) or set(recorded) != observed:
        raise AssertionError('Cached screenshot inventory differs from this capture manifest')
    for entry in captures:
        if hashlib.sha256((folder / entry['file']).read_bytes()).hexdigest() != entry['sha256']:
            raise AssertionError(f"Cached actual screenshot changed: {entry['file']}")


def copy_capture_file(source: Path, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.capture-file-',
                                     delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def recover_capture_publish(out: Path, *,
                            copy_file: Callable[[Path, Path], None] = copy_capture_file) -> None:
    """Finish an interrupted publication from its intact validated staging dir."""
    marker = out / 'capture-publish.json'
    if not marker.is_file():
        return
    staging = Path(json.loads(marker.read_text())['staging'])
    if staging.parent != out.parent or not staging.name.startswith('.capture-' + out.name + '-'):
        raise AssertionError('Capture staging directory does not belong to this case')
    manifest = json.loads((staging / 'capture-manifest.json').read_text())
    # Finish the previous producer's transaction even across a mode upgrade.
    # Publishing preserves its bytes; callers still validate current mode,
    # engine and dependencies before reuse.
    _validate_capture_files(staging, manifest,
                            dependency_hash=manifest['renderer_dependencies_sha256'],
                            godot_version=manifest['godot'])
    # Keep staging intact until every file is published, with the manifest last.
    for pattern in CAPTURE_PATTERNS:
        for artifact in out.glob(pattern):
            artifact.unlink()
    for artifact in sorted(staging.iterdir(), key=lambda p: p.name == 'capture-manifest.json'):
        copy_file(artifact, out / artifact.name)
    marker.unlink()
    shutil.rmtree(staging)
