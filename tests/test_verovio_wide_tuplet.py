"""Real Peace Piece tuplets must survive a wide reference-page viewport."""
from pathlib import Path
import base64
from io import BytesIO
import json
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from piano_teacher.notation.assets.tuplets import extract_tuplets, crop_art

SOURCE = Path(__file__).parent/'fixtures/peace_wide_tuplet'


def test_actual_wide_peace_reference_retains_source_owned_number_and_bracket():
    model = json.loads((SOURCE/'group-model.json').read_text())
    expected = '|'.join(n['id'] for n in model['notation_events'])
    result = extract_tuplets([(SOURCE/'verovio-0.svg').read_text()], model)
    assert expected in result
    item = result[expected]
    assert item['note_ids'] == [n['id'] for n in model['notation_events']]
    for kind in ('number', 'bracket'):
        assert item[kind] is not None
        with Image.open(BytesIO(base64.b64decode(item[kind]['png_base64']))) as image:
            assert image.getchannel('A').getbbox()
            assert image.width*image.height < 1500*850


def test_recovered_real_numeral_has_opaque_engraved_ink():
    model = json.loads((SOURCE/'group-model.json').read_text())
    key = '|'.join(n['id'] for n in model['notation_events'])
    art = extract_tuplets([(SOURCE/'verovio-0.svg').read_text()], model)[key]['number']
    with Image.open(BytesIO(base64.b64decode(art['png_base64']))) as image:
        assert image.getchannel('A').getextrema()[1] >= 240


@pytest.fixture(scope='module')
def real_native_frames(tmp_path_factory):
    from types import SimpleNamespace
    import shutil
    from piano_teacher.application.score_preparation import assemble_layout
    from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG
    from test_native_fingering import _godot, _run_godot
    folder = tmp_path_factory.mktemp('peace-wide-tuplet')
    model = json.loads((SOURCE/'model.json').read_text())
    xml = (SOURCE/'score.musicxml').read_text()
    pages = [(SOURCE/'verovio-0.svg').read_text()]
    assets = assemble_layout(SimpleNamespace(layout={}, pages=pages), native_model=model, notation_xml=xml)
    payload = dict(model=model, assets=assets, capture_config=dict(CANONICAL_CAPTURE_CONFIG),
        sample_beats=[5.5, 5.55, 5.58333333, 5.66666667], phase3_full=True,
        full_symbol_inventory=False, hand='both')
    (folder/'fixture.json').write_text(json.dumps(payload))
    for name in ('score.musicxml', 'verovio-0.svg'):
        shutil.copy2(SOURCE/name, folder/name)
    root = Path(__file__).resolve().parents[1]
    result = _run_godot([*_godot(), '--path', str(root/'godot'),
        '--rendering-method', 'gl_compatibility', '--audio-driver', 'Dummy',
        '--script', str(root/'tests/godot/native_verovio_overlay.gd'), '--',
        str(folder/'fixture.json'), str(folder)], timeout=65)
    output = result.stdout+result.stderr
    (folder/'godot.log').write_text(output)
    assert result.returncode == 0 and 'SCRIPT ERROR' not in output, output
    return folder


def _target_proof(folder):
    from piano_teacher.notation.connector_pixels import verify_tuplet_pixels
    proof = verify_tuplet_pixels((folder/'score.musicxml').read_text(), folder, hand='both')
    expected = [n['id'] for n in json.loads((SOURCE/'group-model.json').read_text())['notation_events']]
    return next(row for row in proof['measured'] if row.get('event_ids') == expected)


def test_real_native_recovered_tuplet_has_independently_identified_number(real_native_frames):
    row = _target_proof(real_native_frames)
    evidence = row['evidence']
    assert evidence['expected_numeral'] == '3'
    assert evidence['numeral_match'] >= .79 and evidence['numeral_margin'] >= .05, row
    assert all(d['match'] >= .79 and d['margin'] >= .03 for d in evidence['digits']), row
    # Recovery makes this genuine source group renderable, not certified:
    # bracket alignment/reference downsampling remains a separate open issue.
    assert row['status'] != 'verified' and 'bracket' in row['reason'].lower(), row


@pytest.mark.parametrize('damage', ['erase', 'move'])
def test_corrupted_recovered_real_numeral_is_rejected(real_native_frames, tmp_path, damage):
    import shutil
    import numpy as np
    folder = tmp_path/damage
    shutil.copytree(real_native_frames, folder)
    row = _target_proof(folder)
    evidence = row['evidence']
    path = folder/evidence['frame']
    pixels = np.array(Image.open(path).convert('RGB'))
    left, top, right, bottom = evidence['number_bbox']
    ink = pixels[top:bottom, left:right].copy()
    pixels[top:bottom, left:right] = pixels[0, -1]
    if damage == 'move':
        pixels[top+30:bottom+30, left:right] = ink
    Image.fromarray(pixels).save(path)
    changed = _target_proof(folder)
    assert changed['status'] == 'mismatch', changed
    assert 'numeral' in changed['reason'].lower(), changed


def test_intrinsic_numeral_opacity_is_preserved():
    model = json.loads((SOURCE/'group-model.json').read_text())
    key = '|'.join(n['id'] for n in model['notation_events'])
    root = ET.fromstring((SOURCE/'verovio-0.svg').read_text())
    for node in root.iter():
        if 'tupletNum' in node.get('class', '').split():
            node.set('fill-opacity', '0.5')
    art = extract_tuplets([ET.tostring(root, encoding='unicode')], model)[key]['number']
    with Image.open(BytesIO(base64.b64decode(art['png_base64']))) as image:
        assert 110 <= image.getchannel('A').getextrema()[1] <= 140


def test_erasing_real_reference_number_does_not_invent_a_tuplet():
    root = ET.fromstring((SOURCE/'verovio-0.svg').read_text())
    for parent in root.iter():
        for child in list(parent):
            if 'tupletNum' in child.get('class', '').split():
                parent.remove(child)
    model = json.loads((SOURCE/'group-model.json').read_text())
    assert extract_tuplets([ET.tostring(root, encoding='unicode')], model) == {}


def test_adaptive_tuplet_rasterization_checks_its_allocation_before_rendering(monkeypatch):
    import cairosvg
    def forbidden(**kwargs):
        raise AssertionError('Unbounded raster allocation attempted')
    monkeypatch.setattr(cairosvg, 'svg2png', forbidden)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10000000 100"><path d="M0 0L1 1"/></svg>'
    assert crop_art(svg, .001, (0, 0), 'verovio-tuplet-number') is None
