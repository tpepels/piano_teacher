"""Terminal-beat geometry is taken from SVG barlines, never guessed."""
import pytest
from piano_teacher.score_geometry import layout_from_pages, locate_beat, parse_svg_geometry

def svg(body):
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600">' + body + '</svg>'

def note(identifier, x, y):
    return (f'<g class="note" id="{identifier}"><g class="notehead">'
            f'<use x="{x}" y="{y}"/></g></g>')

def test_final_note_moves_to_actual_engraved_barline():
    doc = svg('<g class="system" id="last">' + note('n', 300, 200) +
              '<g class="barLine"><path d="M900 100 L900 500"/></g></g>')
    layout = layout_from_pages([doc], [{'qstamp': 0, 'on': ['n']}], 4)
    assert layout['anchors'][-1]['terminal'] is True
    assert locate_beat(layout, 2)['x'] == pytest.approx(.6)
    assert locate_beat(layout, 4)['x'] == pytest.approx(.9)

def test_line_and_transformed_barline_supported():
    doc = svg('<g class="system" id="s" transform="translate(100,0)">' +
              note('n', 200, 200) +
              '<g class="barLine"><line x1="700" y1="100"/></g></g>')
    assert parse_svg_geometry(doc).system_ends['s'] == pytest.approx(.8)
    layout = layout_from_pages([doc], [{'qstamp': 0, 'on': ['n']}], 4)
    assert locate_beat(layout, 4)['x'] == pytest.approx(.8)

def test_unmeasurable_end_does_not_invent_position():
    doc = svg('<g class="system" id="s">' + note('n', 300, 200) + '</g>')
    layout = layout_from_pages([doc], [{'qstamp': 0, 'on': ['n']}], 4)
    assert len(layout['anchors']) == 1
    assert locate_beat(layout, 4)['x'] == pytest.approx(.3)

def test_wrap_does_not_sweep_across_next_staff():
    doc = svg('<g class="system" id="first">' + note('a', 600, 150) +
              '<g class="barLine"><line x1="900" y1="150"/></g></g>' +
              '<g class="system" id="last">' + note('b', 100, 400) +
              '<g class="barLine"><line x1="850" y1="400"/></g></g>')
    layout = layout_from_pages([doc], [
        {'qstamp': 0, 'on': ['a']}, {'qstamp': 2, 'on': ['b']}], 4)
    assert locate_beat(layout, 1)['system'] == 'first'
    assert locate_beat(layout, 2)['system'] == 'last'
    assert locate_beat(layout, 4)['x'] == pytest.approx(.85)

def test_left_or_relative_barline_ignored():
    doc = svg('<g class="system" id="s">' + note('n', 900, 300) +
              '<g class="barLine"><path d="m 100 200 v 30"/></g>' +
              '<g class="barLine"><line x1="700" y1="200"/></g></g>')
    layout = layout_from_pages([doc], [{'qstamp': 0, 'on': ['n']}], 4)
    assert len(layout['anchors']) == 1
