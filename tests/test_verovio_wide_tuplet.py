"""Real Peace Piece tuplets must survive a wide reference-page viewport."""
from pathlib import Path
import base64
from io import BytesIO
import json
import xml.etree.ElementTree as ET

from PIL import Image

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
