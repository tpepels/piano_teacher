"""Metadata diagnostics and source caches must not initialize engraving adapters."""
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('operation', ['health', 'source-cache'])
def test_import_only_use_cases_do_not_load_page_rendering(tmp_path, operation):
    source = r'''
from pathlib import Path
import hashlib
import sys
if sys.argv[2] == 'health':
    from piano_teacher.library_health import LibraryHealth
else:
    from piano_teacher.preprocessing_cache import PreprocessingCache
    path = Path('tests/fixtures/musical_fidelity/midi_four_four.mid')
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    cache = PreprocessingCache(Path(sys.argv[1]))
    first, _ = cache.load_import(path, fingerprint)
    second, original = cache.load_import(path, fingerprint)
    assert first == second and original is None
assert 'piano_teacher.score' not in sys.modules, 'Source importing initialized the rendering facade'
assert 'piano_teacher.rendering.legacy.engraving' not in sys.modules
'''
    run = subprocess.run([sys.executable, '-c', source, str(tmp_path), operation],
        cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stdout+run.stderr
