"""Dense actual head ownership must terminate without accepting shared ink."""
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_actual_five_head_registration_finishes_with_bounded_resources():
    # This retained production frame stalled a corpus worker inside pixel
    # augmentation for hours. Bound the regression process as well as the API.
    code = '''
from pathlib import Path
from PIL import Image
from piano_teacher.notation.head_registration import register_noteheads
from piano_teacher.notation.reference_font import feature_glyphs
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.proof import read_written_score
from piano_teacher.notation.raster_matching import photographed_playhead_columns
from piano_teacher.notation.pixel_ink import bright
root=Path("tests/fixtures")
written=read_written_score((root/"native_dense_registration.musicxml").read_text())
notes=[n for n in written.symbols if n["kind"]=="note" and n["beat"]==2]
assert len(notes)==5
with Image.open(root/"native_dense_registration.png") as raw:
    image=raw.convert("RGB")
heads,errors=register_noteheads(bright(image),detect_staff_lines(image),written,notes,
    feature_glyphs(),occlusion_columns=photographed_playhead_columns(image))
assert set(heads).isdisjoint(errors)
assert len(heads)+len(errors)==5
owned=set()
for head in heads.values():
    assert head["score"]>=.79
    assert owned.isdisjoint(head["support"])
    owned.update(head["support"])
print("bounded",len(heads),len(errors))
'''
    try:
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
            capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        pytest.fail('Five-head registration exceeded five seconds; ownership work is not bounded')
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'bounded' in result.stdout
