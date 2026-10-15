"""Real staff geometry and rest timing drive the moving teaching score."""
from io import BytesIO
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase
from piano_teacher.raster import rasterize_score
from piano_teacher.score import _fade_inactive_staff, render_layout
from piano_teacher.score_geometry import layout_from_pages


def svg(body):
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">' + body + '</svg>'


def glyph(identifier, x, y, kind="note"):
    return (f'<g class="{kind}" id="{identifier}"><g class="notehead">'
            f'<use x="{x}" y="{y}"/></g></g>')


def staff(left, right, top):
    return '<g class="staff">' + ''.join(
        f'<path d="M{left} {top + i * 10} L{right} {top + i * 10}"/>'
        for i in range(5)) + '</g>'


def test_real_rest_on_key_adds_timed_anchors_without_moving_simultaneous_note():
    doc = svg('<g class="system" id="s">' + glyph('n', 100, 100)
              + glyph('inactive', 300, 400, 'rest') + glyph('r', 500, 100, 'rest') + '</g>')
    layout = layout_from_pages([doc], [
        {'qstamp': 0, 'on': ['n'], 'restsOn': ['inactive']},
        {'qstamp': 1, 'restsOn': ['r']},
    ], 2)
    assert [(a['beat'], a['x']) for a in layout['anchors']] == [(0, .1), (1, .5)]


def test_staff_lines_are_measured_deduplicated_and_cover_both_staves():
    # Verovio emits a separate staff group in every measure of the system.
    doc = svg('<g class="system" id="s" transform="translate(20,30)">'
              + staff(80, 480, 100) + staff(80, 480, 300)
              + staff(480, 880, 100) + staff(480, 880, 300)
              + glyph('n', 100, 110) + '</g>')
    layout = layout_from_pages([doc], [{'qstamp': 0, 'on': ['n']}], 4)
    system = layout['systems'][0]
    assert system['page'] == 0 and system['system'] == 's'
    assert system['left'] == pytest.approx(.1)
    assert system['right'] == pytest.approx(.9)
    assert system['staff_lines'] == pytest.approx(
        [130/600, 140/600, 150/600, 160/600, 170/600,
         330/600, 340/600, 350/600, 360/600, 370/600])
    assert system['top'] < 130/600 and system['bottom'] > 370/600
    assert layout['anchors'][0]['top'] == system['top']
    assert layout['anchors'][0]['bottom'] == system['bottom']


def test_inactive_staff_fades_in_every_measure_of_a_system():
    doc = svg('<g class="system">' + ''.join(
        '<g class="measure"><g class="staff"/><g class="staff"/></g>'
        for _ in range(3)) + '</g>')
    for hand, expected in [('right', [None, '0.48']), ('left', ['0.48', None])]:
        root = ET.fromstring(_fade_inactive_staff(doc, hand))
        measures = [e for e in root.iter() if e.get('class') == 'measure']
        assert [[s.get('opacity') for s in m] for m in measures] == [expected] * 3


def test_real_verovio_staff_and_note_coordinates_match_transparent_raster():
    pytest.importorskip('verovio')
    pytest.importorskip('music21')
    from PIL import Image

    phrase = Phrase(1, 1, 2, 0, 6, tuple(
        Note(float(i), i + .5, 77 if i < 3 else 76, 0, 0, 'right') for i in range(6)))
    score = render_layout(build_lesson_score(phrase), 1, 2, 'right', total_beats=6)
    image = Image.open(BytesIO(rasterize_score(score.pages[0]))).convert('RGBA')
    system = score.layout['systems'][0]
    assert len(system['staff_lines']) == 10
    assert len(score.layout['anchors']) > 7  # half-beat rests remain time-bearing
    for head in score.layout['notes']:
        x, y = round(head['x'] * image.width), round(head['y'] * image.height)
        # The SVG glyph origin is at the notehead's left edge; permit raster rounding.
        assert image.getchannel('A').crop((x-1, y-2, x+8, y+3)).getextrema()[1] > 128
        assert system['top'] < head['y'] < system['bottom']
    root = ET.fromstring(score.pages[0])
    staves = [e for e in root.iter() if e.get('class') == 'staff']
    assert [s.get('opacity') for s in staves] == [None, '0.48', None, '0.48']
