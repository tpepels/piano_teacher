"""Independent multi-page Verovio source mapping and rasterization checks."""
from io import BytesIO
from PIL import Image

import pytest

from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Note, Phrase
from piano_teacher.raster import rasterize_score
from piano_teacher.score import render_layout


@pytest.mark.parametrize('bars,held,crossed', [(2, False, False), (40, False, False),
                                           (40, True, False), (24, False, True)])
def test_reference_engraving_preserves_source_mapping_and_real_raster(bars, held, crossed):
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
    # Preserve the independent source SVG/PNG proof after retiring the
    # Godot page-strip producer. No production renderer transforms this ink.
    for page, svg in enumerate(score.pages):
        with Image.open(BytesIO(rasterize_score(svg))) as image:
            assert image.width >= 32 and image.height >= 32
            assert image.convert("RGBA").getchannel("A").getbbox() is not None
            assert all(0 <= float(note["x"]) <= 1 and 0 <= float(note["y"]) <= 1
                       for note in score.layout["notes"] if note["page"] == page)
