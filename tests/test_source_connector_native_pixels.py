"""Actual native framebuffer witnesses and PNG mutations, not renderer reports."""
from pathlib import Path
import json
import os
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def captures(tmp_path_factory):
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        pytest.skip('Actual native framebuffer needs Godot and a desktop')
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    root = tmp_path_factory.mktemp('source-connector-native')
    specimens = {}
    tie = (ROOT/'tests/fixtures/native_pixel_tie_probe.musicxml').read_text()
    # A quarter tie across a barline leaves independently separable curve
    # ink. Compressed ties can overlap the head bounding rectangles; the
    # production contour's visibility there has its own framebuffer test.
    from xml.etree import ElementTree as ET
    tree = ET.fromstring(tie)
    rh = tree.find("part[@id='RH']")
    first, second = rh.findall('measure')
    a = first.find('note')
    b = second.find('note')
    a.find('duration').text = '8'
    a.find('type').text = 'quarter'
    b.find('duration').text = '8'
    b.find('type').text = 'quarter'
    opening = ET.Element('note')
    ET.SubElement(opening, 'rest')
    ET.SubElement(opening, 'duration').text = '24'
    ET.SubElement(opening, 'voice').text = '1'
    ET.SubElement(opening, 'type').text = 'half'
    ET.SubElement(opening, 'dot')
    first.insert(1, opening)
    rest = second.findall('note')[1]
    rest.find('duration').text = '24'
    rest.find('type').text = 'half'
    rest.append(ET.Element('dot'))
    for kind, xml, bars, beats in (
        ('tie', ET.tostring(tree, encoding='unicode'), 2, [3, 4]),
        ('slur', (ROOT/'tests/fixtures/native_pixel_slur_probe.musicxml').read_text(), 2, [0, 1.5, 3]),
    ):
        folder = root/kind
        folder.mkdir()
        source = folder/'source.musicxml'
        source.write_text(xml)
        data, _ = fixture(AuditCase(f'connector-{kind}', str(source), 1, bars, 'right'))
        data['sample_beats'] = beats
        payload = folder/'fixture.json'
        payload.write_text(json.dumps(data))
        result = subprocess.run([binary, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
            '--rendering-method', 'gl_compatibility', '--script',
            str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(folder)],
            capture_output=True, text=True, timeout=120)
        (folder/'godot.log').write_text(result.stdout+result.stderr)
        assert result.returncode == 0, (result.stdout+result.stderr)[-4000:]
        assert 'NATIVE_VEROVIO_OVERLAY_FAILURES:0' in result.stdout
        payload.unlink()  # Neither atlas nor telemetry is available to authorize proof.
        for path in folder.glob('*report.json'):
            path.unlink()
        specimens[kind] = (xml, folder)
    return specimens


@pytest.mark.parametrize('kind', ['tie', 'slur'])
def test_actual_native_curve_is_owned_by_its_written_source_endpoints(captures, kind):
    xml, folder = captures[kind]
    result = verify_connector_pixels(xml, folder, constructs=(kind,))
    (folder/'connector-proof.json').write_text(json.dumps(result, indent=2))
    assert result['coverage']['expected'] == 1
    assert result['complete'], result


@pytest.mark.parametrize('kind', ['tie', 'slur'])
@pytest.mark.parametrize('mutation', ['erased', 'wrong-endpoints', 'straight-line'])
def test_actual_png_erasure_wrong_attachments_and_line_cannot_prove_a_curve(captures, kind, mutation, tmp_path):
    xml, folder = captures[kind]
    baseline = verify_connector_pixels(xml, folder, constructs=(kind,))
    assert baseline['complete'], baseline
    for path in folder.glob('native-*.png'):
        image = Image.open(path).convert('RGB')
        # Measure the curve in each PNG using a folder containing only this
        # common image plus the original independent onset registrations.
        shutil.copy(path, tmp_path/path.name)
    # Mutate every retained frame, leaving the independently matched heads.
    from piano_teacher.notation import symbol_pixel_proof as proof
    from piano_teacher.notation.proof import read_written_score
    written = read_written_score(xml)
    pair, = proof._connector_pairs(xml, written, (kind,), 'both')
    mutated = 0
    for path in sorted(tmp_path.glob('native-*.png')):
        original = Image.open(path).convert('RGB')
        heads = []
        for note in pair['notes']:
            onset = float(note['beat'])
            source_path = next(p for p in folder.glob('native-*.png')
                               if abs(float(p.stem[7:])-onset) < 1e-7)
            source = Image.open(source_path).convert('RGB')
            own = proof._connector_head(source, written, note, source.width*.42)
            shift = proof._connector_shift(original, source)
            assert own and shift
            head = proof._connector_head(original, written, note, own['x']+shift['shift'])
            assert head
            heads.append(head)
        ink = proof._connector_curve(original, heads, kind)
        # A clipped/overlapping frame never supplied the baseline proof.
        # Erase every usable witness so no fallback frame can rescue it.
        if ink['status'] != 'verified':
            continue
        mutated += 1
        image = original.copy()
        pen = ImageDraw.Draw(image)
        background = tuple(np.asarray(original)[0, 0])
        points = []
        for y, a, b in ink['pixel_runs']:
            pen.line((a, y, b-1, y), fill=background)
            points.extend((x, y) for x in range(a, b))
        if mutation == 'wrong-endpoints':
            for x, y in points:
                pen.point((x, y+round(heads[0]['gap']*2)), fill=(231, 240, 232))
        elif mutation == 'straight-line':
            first = min(points, key=lambda p: p[0])
            last = max(points, key=lambda p: p[0])
            pen.line((*first, *last), fill=(231, 240, 232), width=2)
        image.save(path)
    assert mutated > 0
    assert not verify_connector_pixels(xml, tmp_path, constructs=(kind,))['complete']
