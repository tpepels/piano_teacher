"""Stitch real Verovio systems/pages with Godot's actual texture geometry."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.raster import rasterize_score
from piano_teacher.score import render_layout


ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which('godot') or shutil.which('godot4')


@pytest.mark.skipif(GODOT is None, reason='Godot 4 is not installed')
@pytest.mark.parametrize('bars,held,crossed', [(2, False, False), (40, False, False),
                                           (40, True, False), (24, False, True)])
def test_real_score_system_tiles_preserve_notehead_and_feedback_geometry(tmp_path, bars, held, crossed):
    pytest.importorskip('verovio')
    pytest.importorskip('music21')
    def pitch(i, hand):
        if crossed:
            swap = (i // 32) % 2 == 1
            return (60 if swap else 76) if hand == 'right' else (76 if swap else 48)
        return (76 if hand == 'right' else 48) + i % 5

    notes = tuple(Note(float(i), i + (4 if held else .8), pitch(i, hand),
                       0, 0, hand)
                  for i in range(0, bars * 4, 4 if held else 1) for hand in ('right', 'left'))
    phrase = Phrase(1, 1, bars, 0, bars * 4, notes)
    score = render_layout(build_lesson_score(phrase), 1, bars, total_beats=bars * 4)
    require_lesson_alignment(phrase, score.layout, 'both')
    if crossed:
        gaps = [(lines[5] - lines[0]) / (lines[1] - lines[0])
                for system in score.layout['systems'] if len(lines := system['staff_lines']) == 10]
        # This fixture needs about 11.81 staff spaces. A huge fixed gap would
        # align the rails while making every ordinary passage much smaller.
        assert gaps and all(11.8 <= gap <= 12.5 for gap in gaps)
    if bars > 2:
        assert score.layout['pages'] > 1
        assert len(score.layout['systems']) > 2
    (tmp_path / 'layout.json').write_text(json.dumps(score.layout))
    for page, svg in enumerate(score.pages):
        (tmp_path / f'page-{page}.png').write_bytes(rasterize_score(svg))
    result = subprocess.run(
        [GODOT, '--headless', '--path', str(ROOT / 'godot'), '--script',
         str(ROOT / 'tests/godot/notation/legacy/strip.gd'), '--', str(tmp_path)],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'SCORE_STRIP_FAILURES:0' in result.stdout, result.stdout + result.stderr
