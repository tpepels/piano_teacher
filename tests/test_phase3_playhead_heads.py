"""A photographed timing line may occlude a small part of a real hollow head."""
from pathlib import Path
from shutil import copytree

import numpy as np
from PIL import Image
import pytest

from piano_teacher.notation.phase3_pixels import verify_all_notehead_pixels
from piano_teacher.notation.reference_font import reference_glyphs
from piano_teacher.notation.pixel_ink import rasterize_outline

FIXTURE = Path(__file__).parent/'fixtures/native_playhead_half'


def test_actual_half_chord_is_identified_around_photographed_timing_line():
    report = verify_all_notehead_pixels((FIXTURE/'score.musicxml').read_text(), FIXTURE, hand='right')
    assert report['complete'], report
    assert report['coverage']['verified'] == report['coverage']['expected'] == 8
    row = next(r for r in report['measured'] if r['beat'] == 3 and tuple(r['spelling']) == ('F',0,4))
    evidence = row['joint_assignment']
    assert .75 <= evidence['visible_reference_pixels']/evidence['reference_pixels'] < 1


def test_same_photographed_half_head_can_anchor_a_connector():
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_head
    written = read_written_score((FIXTURE/'score.musicxml').read_text())
    note = next(n for n in written.symbols if n['beat']==3 and n.get('spelling')==('F',0,4))
    with Image.open(FIXTURE/'native-3.00000.png') as image:
        assert _connector_head(image,written,note,image.width*.42) is not None


def test_timing_rule_never_censors_uncovered_pixels_in_the_same_column():
    from piano_teacher.notation.raster_matching import photographed_playhead_columns, _comparison
    image=Image.new('RGB',(100,240),(16,41,35))
    rgb=np.array(image)
    rgb[100:220,49:51]=(111,218,179)
    occlusion=photographed_playhead_columns(Image.fromarray(rgb))
    assert occlusion
    template=np.ones((10,10),dtype=bool)
    observed=template.copy();observed[:,4:6]=False
    intersections,expected,_=_comparison(observed[None,None],template,[45],[20],
                                        occlusion_columns=occlusion)
    assert int(expected[0,0])==100
    assert int(intersections.sum())==80


@pytest.mark.parametrize('mutation', ['erased', 'filled', 'wrong-pitch', 'wide-occluder'])
def test_timing_line_never_supplies_missing_or_wrong_head_ink(tmp_path, mutation):
    folder = tmp_path/'changed'
    copytree(FIXTURE, folder)
    path = folder/'native-3.00000.png'
    with Image.open(path) as image:
        pixels = np.array(image.convert('RGB'))
    # F4 is centered at the photographed line. Keep every other source head,
    # staff rule and stem; modify only this authentic head's local contour.
    x, y, width, height = 631, 208, 29, 23
    if mutation == 'wide-occluder':
        pixels[104:440, 636:654] = (111, 218, 179)
    else:
        pixels[y:y+height, x:x+width] = pixels[0, -1]
        if mutation != 'erased':
            glyph = reference_glyphs()['head_black' if mutation == 'filled' else 'head_half']
            b = glyph['bounds'];gap = 21.875
            w, h = round(b[2]*gap/250), round(b[3]*gap/250)
            left = round(645-b[2]*gap/500)
            top = round(219.56+b[1]*gap/250+(gap/2 if mutation == 'wrong-pitch' else 0))
            pixels[top:top+h,left:left+w][rasterize_outline(glyph['svg'],w,h)] = (229,242,234)
        pixels[104:440, 644:646] = (111, 218, 179)
    Image.fromarray(pixels).save(path)
    report = verify_all_notehead_pixels((folder/'score.musicxml').read_text(),folder,hand='right')
    row = next(r for r in report['measured'] if r['beat'] == 3 and tuple(r['spelling']) == ('F',0,4))
    assert row['status'] != 'verified', row
    assert not report['complete']
