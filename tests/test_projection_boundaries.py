"""Exact source boundaries, after-grace input, and complete span omissions."""
from dataclasses import asdict, replace
from fractions import Fraction
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.notation.source import SourceNotation
from piano_teacher.practice import PlayedNote, evaluate


def import_xml(tmp_path, measures):
    path = tmp_path / 'projection.musicxml'
    path.write_text('<score-partwise version="4.0"><part-list><score-part id="P">'
        '<part-name>Right hand</part-name></score-part></part-list><part id="P">'
        + measures + '</part></score-partwise>')
    return load_musicxml(path, bpm=60)


def compile_piece(piece, first=1, last=None, notes=None):
    last = last or len(piece.bar_boundaries)-1
    start, end = piece.bar_boundaries[first-1], piece.bar_boundaries[last]
    phrase = Phrase(1, first, last, start, end, tuple(n for n in
        (piece.notes if notes is None else notes) if start <= n.start < end))
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, clef_changes=piece.clef_changes,
        source_notation=piece.source_notation)
    return score, build_score_model(score, boundaries=piece.bar_boundaries)


def fractional_piece(tmp_path):
    return import_xml(tmp_path, '''<measure number="1"><attributes><divisions>3</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>C</step><octave>5</octave></pitch><duration>5</duration>
        <type>half</type><time-modification><actual-notes>6</actual-notes>
        <normal-notes>5</normal-notes></time-modification></note></measure>
        <measure number="2"><note><pitch><step>D</step><octave>5</octave></pitch>
        <duration>1</duration><type>eighth</type><time-modification>
        <actual-notes>3</actual-notes><normal-notes>2</normal-notes>
        </time-modification></note><forward><duration>2</duration></forward></measure>
        <measure number="3"><note><pitch><step>E</step><octave>5</octave></pitch>
        <duration>3</duration><type>quarter</type></note></measure>''')


@pytest.mark.parametrize('first,last', [(2, 2), (1, 1), (1, 3)])
def test_fractional_measure_boundaries_preserve_attacks_and_written_offsets(tmp_path, first, last):
    piece = fractional_piece(tmp_path)
    score, model = compile_piece(piece, first, last)
    selected = [n for n in piece.notes if score.phrase.start <= n.start < score.phrase.end]
    assert {n['id'] for n in model['notes']} == {n.source_id for n in selected}
    assert {e['source_id'] for e in model['notation_events'] if e['kind']=='note'} == {n.source_id for n in selected}
    divisions = int(ET.fromstring(score.musicxml).findtext('./part/measure/attributes/divisions'))
    pitched = [n for n in ET.fromstring(score.musicxml).findall('./part/measure/note') if n.find('pitch') is not None]
    assert [Fraction(int(n.findtext('duration')), divisions) for n in pitched] == {
        (2, 2): [Fraction(1, 3)], (1, 1): [Fraction(5, 3)],
        (1, 3): [Fraction(5, 3), Fraction(1, 3), Fraction(1)]}[first, last]
    assert [(n.start, n.end, n.source_id) for n in score.phrase.notes] == [(n.start, n.end, n.source_id) for n in selected]
    # The forward at the end of measure 2 is real empty time, not a longer D.
    if first == 2:
        assert model['notation_events'][0]['beat'] == 0
        assert model['notation_events'][0]['duration_beats'] == pytest.approx(1/3)


def test_fractional_grid_survives_source_cache_round_trip(tmp_path):
    piece = fractional_piece(tmp_path)
    source = SourceNotation.from_dict(json.loads(json.dumps(asdict(piece.source_notation))))
    score, model = compile_piece(replace(piece, source_notation=source), 2, 2)
    assert len(model['notes']) == 1
    assert model['notes'][0]['id'] == piece.notes[1].source_id
    assert score.note_bindings


def after_grace_piece(tmp_path):
    return import_xml(tmp_path, '''<measure number="1"><attributes><divisions>1</divisions>
        <time><beats>2</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note>
        <note><grace steal-time-previous="20"/><pitch><step>D</step><octave>5</octave></pitch><type>eighth</type></note>
        <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type></note></measure>''')


def test_after_grace_stays_after_its_principal_with_its_source_beat(tmp_path):
    piece = after_grace_piece(tmp_path)
    score, model = compile_piece(piece)
    notes = [n for n in ET.fromstring(score.musicxml).findall('./part/measure/note') if n.find('pitch') is not None]
    assert [(n.findtext('pitch/step'), n.find('grace') is not None) for n in notes] == [('C', False), ('D', True), ('E', False)]
    grace, = model['visual_events']
    assert (grace['position'], grace['beat'], grace['anchor_source_id']) == ('after', 1, piece.notes[0].source_id)
    assert [(n['id'], n['onset_beats']) for n in model['notes']] == [(piece.notes[0].source_id, 0), (piece.notes[1].source_id, 1)]


def test_after_grace_at_anchor_end_is_optional_without_hiding_required_misses(tmp_path):
    piece = after_grace_piece(tmp_path)
    score, model = compile_piece(piece)
    required = [PlayedNote(72, 0, 1), PlayedNote(76, 1, 2)]
    grace = PlayedNote(74, .95, 1)
    result = evaluate(score.phrase, 'right', 60, required+[grace], optional_notes=score.visual_events)
    assert result.clean and result.correct == 2 and result.extra_notes == 0
    assert evaluate(score.phrase, 'right', 60, required, optional_notes=score.visual_events).clean
    only_grace = evaluate(score.phrase, 'right', 60, [grace], optional_notes=score.visual_events)
    assert [n.status for n in only_grace.notes] == ['missed', 'missed']
    assert only_grace.extra_notes == 0 and not only_grace.clean


@pytest.mark.parametrize('remove_endpoint', [False, True])
def test_continuation_markers_follow_the_whole_slur_projection(tmp_path, remove_endpoint):
    piece = import_xml(tmp_path, '''<measure number="1"><attributes><divisions>1</divisions>
        <time><beats>3</beats><beat-type>4</beat-type></time></attributes>
        <note><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type>
        <notations><slur type="start" number="1"/></notations></note>
        <note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type>
        <notations><slur type="continue" number="1"/></notations></note>
        <note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type>
        <notations><slur type="stop" number="1"/></notations></note></measure>''')
    source = SourceNotation.from_dict(json.loads(json.dumps(asdict(piece.source_notation))))
    score, model = compile_piece(replace(piece, source_notation=source), notes=piece.notes[:-1] if remove_endpoint else None)
    markers = ET.fromstring(score.musicxml).findall('.//slur')
    if remove_endpoint:
        assert markers == []
        row, = [r for r in score.projection_report if r['kind']=='slur']
        assert (row['status'], row['reason']) == ('omitted', 'endpoint_removed')
        assert not model['groups']
    else:
        assert [n.get('type') for n in markers] == ['start', 'continue', 'stop']
        assert len([g for g in model['groups'] if g['kind']=='slur']) == 1


def after_grace_art(tmp_path):
    import verovio
    from piano_teacher.notation.assets.annotations import annotation_fragments, restore_annotation_ids
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.svg_geometry import parse_svg_geometry
    score, model = compile_piece(after_grace_piece(tmp_path))
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({'inputFrom':'xml', 'svgViewBox':True,
        'svgBoundingBoxes':True, 'svgContentBoundingBoxes':True, 'breaks':'none'})
    assert toolkit.loadData(score.musicxml)
    restore_annotation_ids(toolkit, model)
    svg = toolkit.renderToSVG(1)
    atlas = annotation_fragments([svg], model)
    grace, = model['visual_events']
    assert (grace['beat'], grace['layout_beat']) == (1, 0)
    geometry = parse_svg_geometry(svg)
    first, following = [e for e in model['notation_events'] if e['kind']=='note']
    x0, _, system = geometry.elements[first['id']]
    x1 = geometry.elements[following['id']][0]
    lines = geometry.staff_systems[system]['staff_lines']
    density = (x1-x0)*geometry.width/geometry.height*18/(lines[1]-lines[0])
    assert atlas[grace['id']]['parts'][0]['bounds'][0] > 0
    return model, atlas, density


def test_after_grace_layout_beat_must_match_the_original_principal(tmp_path):
    from piano_teacher.notation.assets.annotations import annotation_fragments
    model, _, _ = after_grace_art(tmp_path)
    model['visual_events'][0]['layout_beat'] = .5
    with pytest.raises(ValueError, match='grace.*layout|layout.*grace'):
        annotation_fragments([], model)


def test_native_after_grace_keeps_original_pixels_and_layout_culling(tmp_path):
    import os
    import shutil
    import subprocess
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary:
        pytest.skip('Godot unavailable')
    model, atlas, density = after_grace_art(tmp_path)
    fixture = tmp_path/'after-grace.json'
    fixture.write_text(json.dumps({'model':model,'native_annotation_fragments':atlas,
        'source_density':density}))
    root = Path(__file__).resolve().parents[1]
    pixels = bool(os.environ.get('DISPLAY'))
    options = ['--windowed','--resolution','640x700','--rendering-method','gl_compatibility'] if pixels else ['--headless']
    result = subprocess.run([binary, *options, '--path',str(root/'godot'),
        '--script',str(root/'tests/godot/native_after_grace.gd')],
        env={**os.environ,'PIANO_TEACHER_NATIVE_NOTATION':'1',
            'PIANO_TEACHER_AFTER_GRACE_FIXTURE':str(fixture),
            'PIANO_TEACHER_AFTER_GRACE_PIXELS':'1' if pixels else '0'},
        text=True, capture_output=True, timeout=45)
    output = result.stdout+result.stderr
    assert result.returncode == 0, output
    assert 'NATIVE_AFTER_GRACE_FAILURES:0' in output, output
    assert 'SCRIPT ERROR' not in output and 'Parse Error' not in output, output
