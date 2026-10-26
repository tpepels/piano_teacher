"""Framebuffer regressions for displaced chord dots and compound barlines."""
from hashlib import sha256
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import numpy as np
from PIL import Image, ImageFilter

from piano_teacher.fingering import FingeringService, project_model
from piano_teacher.importing.pieces import import_piece
from scripts.check_native_verovio_overlay import AuditCase, fixture
from test_native_fingering import _godot, _run_godot, _verify_numbers

ROOT = Path(__file__).resolve().parents[1]
EVANS = ROOT / 'midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'


def _authored_source(folder, kind):
    root = ET.Element('score-partwise', version='4.0')
    parts = ET.SubElement(root, 'part-list')
    definition = ET.SubElement(parts, 'score-part', id='RH')
    ET.SubElement(definition, 'part-name').text = 'Right hand'
    part = ET.SubElement(root, 'part', id='RH')
    dotted = kind == 'dotted-seconds'
    # A low ledger chord reproduces the real Evans double-stroke collision.
    groups = [('C2', 'C4', 'E4', 'G4'), ('G2', 'D4', 'F4', 'A4')]
    if kind == 'repeat-dots':
        groups = [('C2', 'C4', 'E4'), ('G2', 'D4', 'F4')]
    if dotted:
        groups = [('E4', 'F4'), ('B4', 'C5'), ('E5', 'F5'), ('A4', 'B4', 'C5')]
    for bar in range(2):
        measure = ET.SubElement(part, 'measure', number=str(bar + 1))
        if bar == 0:
            attributes = ET.SubElement(measure, 'attributes')
            ET.SubElement(attributes, 'divisions').text = '4'
            meter = ET.SubElement(attributes, 'time')
            ET.SubElement(meter, 'beats').text = '6' if dotted else '4'
            ET.SubElement(meter, 'beat-type').text = '4'
            clef = ET.SubElement(attributes, 'clef')
            ET.SubElement(clef, 'sign').text = 'G'
            ET.SubElement(clef, 'line').text = '2'
        for onset in range(2):
            pitches = groups[(bar * 2 + onset) % len(groups)]
            for tone, name in enumerate(pitches):
                note = ET.SubElement(measure, 'note')
                if tone:
                    ET.SubElement(note, 'chord')
                pitch = ET.SubElement(note, 'pitch')
                ET.SubElement(pitch, 'step').text = name[0]
                ET.SubElement(pitch, 'octave').text = name[1:]
                ET.SubElement(note, 'duration').text = '12' if dotted else '8'
                ET.SubElement(note, 'voice').text = '1'
                ET.SubElement(note, 'type').text = 'half'
                if dotted:
                    ET.SubElement(note, 'dot')
                technical = ET.SubElement(ET.SubElement(note, 'notations'), 'technical')
                hint = {'default-x': '19', 'default-y': '-49'} if dotted and bar == onset == tone == 0 else {}
                if kind == 'repeat-dots' and bar == 1 and onset == 0 and tone == 2:
                    # Aim at the forward-dot lane while clearing the main
                    # barline even when uniform ink fitting reduces staff size.
                    hint = {'default-x': '-6.5', 'default-y': '-28'}
                ET.SubElement(technical, 'fingering', hint).text = str(tone + 2)
        if kind == 'double-barline' and bar == 0:
            ET.SubElement(ET.SubElement(measure, 'barline', location='right'), 'bar-style').text = 'light-light'
        if kind == 'repeat-dots' and bar == 1:
            boundary = ET.SubElement(measure, 'barline', location='left')
            ET.SubElement(boundary, 'bar-style').text = 'regular'
            ET.SubElement(boundary, 'repeat', direction='forward')
    # A separate small flagged chord exercises authentic chord non-head ink.
    if dotted:
        measure = list(part)[-1]
        notes = measure.findall('note')
        for note in notes[-3:]:
            note.find('duration').text = '3'
            note.find('type').text = 'eighth'
        rest = ET.SubElement(measure, 'note')
        ET.SubElement(rest, 'rest')
        ET.SubElement(rest, 'duration').text = '9'
        ET.SubElement(rest, 'type').text = 'quarter'
        ET.SubElement(rest, 'dot')
        ET.SubElement(rest, 'dot')
    path = folder / f'{kind}.musicxml'
    ET.ElementTree(root).write(path)
    return path


def _regressed_script(folder, kind):
    """Run the real compositor with just the pre-fix reservation restored."""
    source = (ROOT / 'godot/notation/native/view.gd').read_text()
    if kind == 'dotted-seconds':
        start = source.index('    box = glyphs.bounds["augmentation_dot"]', source.index('func _fingering_event_obstacles'))
        end = source.index('\n\n\nfunc ', start)
        source = source[:start] + '''    box = glyphs.bounds["augmentation_dot"]
    var dot_y: float = y-gap*.24+(Geometry.rest_dot_offset(kind)*gap if event["kind"] == "rest" else 0.0)
    for index in range(int(event.get("dots",0))):
        var dot_x: float = x+gap*(1.05+float(index)*.63)
        _fingering_block(Rect2(dot_x-float(box[2])*unit*.5,dot_y+float(box[1])*unit,
            float(box[2])*unit,float(box[3])*unit),bins,cell)''' + source[end:]
    else:
        start = source.index('    for boundary in boundaries:')
        end = source.index('    for grace in attached_grace_notes:', start)
        source = source[:start] + '''    for boundary in boundaries:
        if boundary.is_empty():
            continue
        var x: float = float(boundary["x"])-translation
        for segment in boundary.get("segments",[]):
            _fingering_block(Rect2(x-2.0,float(segment["top"]),4.0,
                float(segment["bottom"])-float(segment["top"])),bins,cell)
''' + source[end:]
    path = folder / 'regressed-view.gd'
    path.write_text(source)
    return str(path)


@pytest.fixture(scope='module', params=['double-barline', 'repeat-dots', 'dotted-seconds', 'evans-small'])
def obstacle_capture(request, tmp_path_factory):
    kind = request.param
    folder = tmp_path_factory.mktemp('fingering-geometry-' + kind)
    path = EVANS if kind == 'evans-small' else _authored_source(folder, kind)
    piece, _ = import_piece(path)
    plan = FingeringService(folder / 'plans').prepare(piece, sha256(path.read_bytes()).hexdigest())
    first, last = (3, 4) if kind == 'evans-small' else (1, 2)
    data, _ = fixture(AuditCase(kind, str(path), first, last, 'both'), piece=piece)
    data['model'] = project_model(data['model'], plan, source_musicxml=piece.source_musicxml)
    data['summary'] = plan.summary()
    data['kind'] = kind
    data['size'] = [1216, 455] if kind == 'evans-small' else [2048, 620]
    if kind != 'evans-small':
        data['regressed_script'] = _regressed_script(folder, kind)
    payload = folder / 'fixture.json'
    payload.write_text(json.dumps(data))
    result = _run_godot([*_godot(), '--path', str(ROOT / 'godot'), '--audio-driver', 'Dummy',
        '--rendering-method', 'gl_compatibility', '--script',
        str(ROOT / 'tests/godot/native_fingering_obstacle_geometry.gd'), '--', str(payload), str(folder)], timeout=90)
    output = result.stdout + result.stderr
    (folder / 'godot.log').write_text(output)
    assert result.returncode == 0 and 'SCRIPT ERROR' not in output and 'Parse Error' not in output, output
    return folder, data, json.loads((folder / 'report.json').read_text())


def test_actual_digits_clear_displaced_dots_and_barline_punctuation(obstacle_capture):
    folder, data, report = obstacle_capture
    expected = {e['id']: e['fingering'] for e in data['model']['notation_events'] if 'fingering' in e}
    for frame in report['frames']:
        _verify_numbers(folder, frame, len(frame['labels']))
        _verify_punctuation_clearance(folder, frame, report['punctuation_free'])
        shown = {identity for label in frame['labels'] for identity in label['event_ids']}
        missing = {identity for issue in frame['placement_issues'] for identity in issue['event_ids']}
        assert shown.isdisjoint(missing)
        for label in frame['labels']:
            assert all(label['finger'] == expected[i]['finger'] for i in label['event_ids'])
        interior = {i for i, point in frame['noteheads'].items() if i in expected and
                    3 * frame['gap'] < point[0] < data['size'][0] - 3 * frame['gap']}
        assert interior <= shown | missing
        assert not frame['placement_issues'], frame['placement_issues']
    if data['kind'] == 'evans-small':
        assert not report['local_witnesses'], 'Missing fingerings have safe bounded local positions'
        status = report['warning']
        if report['frames'][0]['placement_issues']:
            assert status['visible'] and 'space' in status['text'].lower()
            assert 'Enlarge' in status['tooltip']


def test_previous_reservations_are_rejected_by_the_actual_pixel_oracle(obstacle_capture):
    folder, data, report = obstacle_capture
    if data['kind'] == 'evans-small':
        pytest.skip('Real resized passage is a positive coverage case')
    frame = report['regressed']
    with pytest.raises(AssertionError):
        _verify_numbers(folder, frame, len(frame['labels']))
        _verify_punctuation_clearance(folder, frame, report['punctuation_free'])


def _verify_punctuation_clearance(folder, frame, punctuation_free):
    """Dim barlines need a differential mask, not a bright-note threshold."""
    if frame['file'] == 'scroll.png':
        return  # The source-ink oracle still checks the moving frame.
    base = np.asarray(Image.open(folder / frame['base']).convert('RGB')).astype(int)
    clean = np.asarray(Image.open(folder / punctuation_free).convert('RGB')).astype(int)
    punctuation = np.max(np.abs(base - clean), axis=2) > 4
    assert punctuation.any(), 'Positive control must contain actual barline ink'
    for label in frame['labels']:
        atlas = np.asarray(Image.open(folder / label['reference']).convert('RGB'))
        width = atlas.shape[1] // 5
        digit = atlas[:, (label['finger']-1)*width:label['finger']*width].max(axis=2) > 100
        x, y, _, _ = label['rect']
        mask = np.zeros(punctuation.shape, dtype=np.uint8)
        y, x = int(y), int(x)
        mask[y:y+digit.shape[0], x:x+digit.shape[1]] = digit * 255
        clearance = np.asarray(Image.fromarray(mask).filter(ImageFilter.MaxFilter(5))) > 0
        assert not (clearance & punctuation).any(), 'Fingering collides with actual barline/repeat ink'


def test_flagged_chord_uses_complete_authentic_envelope(obstacle_capture):
    _, data, report = obstacle_capture
    if data['kind'] != 'dotted-seconds':
        pytest.skip('Flagged chord is in the dotted-seconds source')
    assert any(k.startswith('eighth|') for k in data['assets']['native_chord_templates'])
    assert report['envelope']['uncovered'] == 0
    assert report['envelope']['corrupted_uncovered'] > 100
