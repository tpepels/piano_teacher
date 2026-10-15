"""Synthetic Verovio-shaped SVG/timemap regression tests (no engine required)."""
import math
import pytest

from piano_teacher.score_geometry import (
    parse_svg_geometry, layout_from_pages, locate_beat, _transform, _apply,
)


def svg(body, *, viewbox="0 0 1000 600"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">{body}</svg>'


def note(identifier, x, y, cls="note"):
    return (f'<g class="{cls}" id="{identifier}">'
            f'<g class="notehead"><use x="{x}" y="{y}" href="#E0A4"/></g></g>')


def test_transforms_and_viewbox_are_normalized():
    content = svg('<g class="system" id="sys1" transform="translate(100,50)">'
                  '<g transform="scale(2)">' + note("n1", 150, 100) + '</g></g>',
                  viewbox="100 50 800 400")
    page = parse_svg_geometry(content)
    x, y, system = page.elements["n1"]
    assert x == pytest.approx((400 - 100) / 800)
    assert y == pytest.approx((250 - 50) / 400)
    assert system == "sys1"


def test_matrix_transform_composition():
    assert _apply(_transform("translate(50,30) scale(2,3)"), 10, 20) == (70, 90)
    assert _apply(_transform("matrix(2,0,0,2,50,30)"), 10, 20) == (70, 70)


def test_playhead_tracks_engravings_not_linear_percentage():
    # Quarter-note spacing is intentionally nonuniform: x=0.1, 0.4, 0.9.
    first = svg('<g class="system" id="line1">' + note('a',100,150) +
                note('b',400,160) + note('c',900,170) + '</g>')
    map_ = [dict(qstamp=0,on=['a']),dict(qstamp=1,on=['b']),dict(qstamp=2,on=['c'])]
    layout = layout_from_pages([first],map_,4)
    assert locate_beat(layout,0)['x'] == pytest.approx(0.1)
    assert locate_beat(layout,0.5)['x'] == pytest.approx(0.25)
    assert locate_beat(layout,1.5)['x'] == pytest.approx(0.65)
    assert locate_beat(layout,3)['x'] == pytest.approx(0.9)


def test_chords_share_one_timing_anchor_and_derive_full_vertical_extent():
    first = svg('<g class="system" id="line1">' + note('treble',300,100)
                + note('bass',310,450) + '</g>')
    layout = layout_from_pages([first],[dict(qstamp=0,on=['treble','bass'])],2)
    assert len(layout['anchors']) == 1
    marker = locate_beat(layout,0)
    assert marker['x'] == pytest.approx(0.305)
    assert marker['top'] < 100/600
    assert marker['bottom'] > 450/600


def test_system_wrap_does_not_sweep_backwards():
    s = svg('<g class="system" id="first">' + note('a',100,100) + note('b',800,150) + '</g>'
            '<g class="system" id="second">' + note('c',120,350) + note('d',600,370) + '</g>')
    events = [dict(qstamp=0,on=['a']),dict(qstamp=1,on=['b']),
              dict(qstamp=2,on=['c']),dict(qstamp=3,on=['d'])]
    layout=layout_from_pages([s],events,4)
    assert locate_beat(layout,1.5)['x'] == pytest.approx(0.8)
    assert locate_beat(layout,2)['x'] == pytest.approx(0.12)
    assert locate_beat(layout,2)['system'] == 'second'
    assert locate_beat(layout,2.5)['x'] == pytest.approx(0.36)


def test_page_changes_follow_note_ids():
    a=svg('<g class="system" id="page1">'+note('a',150,100)+'</g>')
    b=svg('<g class="system" id="page2">'+note('b',200,100)+'</g>')
    layout=layout_from_pages([a,b],[dict(qstamp=0,on=['a']),dict(qstamp=4,on=['b'])],8)
    assert locate_beat(layout,3.99)['page'] == 0
    assert locate_beat(layout,4)['page'] == 1
    assert layout['pages'] == 2


def test_no_false_precision_when_missing_timed_glyphs():
    doc=svg('<g class="system" id="empty"></g>')
    with pytest.raises(ValueError,match='no engraved/timed note matches'):
        layout_from_pages([doc],[dict(qstamp=0,on=['not-present'])],2)
    with pytest.raises(ValueError,match='viewBox'):
        parse_svg_geometry('<svg xmlns="http://www.w3.org/2000/svg"/>')
    with pytest.raises(ValueError,match='duration'):
        layout_from_pages([doc],[],0)



def test_nested_verovio_svg_viewbox_maps_notehead_to_outer_page():
    # Actual Verovio pattern: CSS-sized page and a separate 22000-unit
    # engraving coordinate system inside <svg class="definition-scale">.
    from piano_teacher.score_geometry import parse_svg_geometry, layout_from_pages
    xml = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1056 255">'
        '<svg class="definition-scale" viewBox="0 0 22000 5310">'
        '<g class="page-margin" transform="translate(500, 500)">'
        '<g class="system" id="s">'
        '<g class="note" id="a"><g class="notehead">'
        '<use transform="translate(3500, 1254) scale(0.72, 0.72)"/>'
        '</g></g>'
        '<g class="note" id="b"><g class="notehead">'
        '<use transform="translate(17000, 3000) scale(0.72, 0.72)"/>'
        '</g></g>'
        '</g></g></svg></svg>'
    )
    page = parse_svg_geometry(xml)
    x, y, _ = page.elements["a"]
    assert 0.15 < x < 0.22
    assert 0.30 < y < 0.36
    assert 0.0 < page.elements["b"][0] < 1.0
    layout = layout_from_pages(
        [xml],
        [{"qstamp": 0.0, "on": ["a"]}, {"qstamp": 1.0, "on": ["b"]}],
        total_beats=2.0
    )
    assert all(0 <= p["x"] <= 1 for p in layout["anchors"])
    assert all(0 <= p["top"] <= p["bottom"] <= 1 for p in layout["anchors"])
