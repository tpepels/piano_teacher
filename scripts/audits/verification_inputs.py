"""Input and code identity for exact-revision audit completion and resume."""
import hashlib
import json
from pathlib import Path
from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG

from .capture_store import ROOT, capture_dependency_hash

def verification_inputs_hash(sources, *, root: Path = ROOT) -> str:
    """A long sweep must finish against the inputs and code it started with."""
    paths=[*sources,root/'scripts/check_native_verovio_overlay.py',
           *sorted((root/'scripts/audits').rglob('*.py')),
           *sorted((root/'piano_teacher').rglob('*.py')),
           root/'tests/fixtures/musical_fidelity/manifest.json']
    digest=hashlib.sha256(capture_dependency_hash(root).encode())
    digest.update(json.dumps(CANONICAL_CAPTURE_CONFIG,sort_keys=True).encode()+b'\0')
    for path in sorted(paths):
        digest.update(str(path).encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()

