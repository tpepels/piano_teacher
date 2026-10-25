"""Canonical captures exclude only instructional fingering, never music ink."""
from dataclasses import fields
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest

from piano_teacher.music import Note, Phrase, Piece

ROOT = Path(__file__).resolve().parents[1]


def test_normalization_removes_only_technical_fingering_and_preserves_other_bytes():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    xml = '''<?xml version="1.0"?>
<!DOCTYPE score-partwise SYSTEM "score.dtd">
<?audit keep?>
<score-partwise><part id="P1"><measure number="1">
<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>
<note id="source-α"><notations id="notations-id"><technical id="technical-id">
<fingering placement="above">5</fingering><string>3</string><hammer-on number="2">H</hammer-on>
</technical><tuplet number="3"/><articulations><staccato/></articulations></notations></note>
<!-- keep this comment --><direction><words>12345</words><fingering>other vocabulary</fingering></direction>
</measure></part></score-partwise>'''
    assert canonical_musicxml(xml) == xml.replace('<fingering placement="above">5</fingering>', '')


@pytest.mark.parametrize("prefix,namespace", [("", ""), ("", ' xmlns="http://www.musicxml.org/ns/musicxml"'),
    ("m:", ' xmlns:m="http://www.musicxml.org/ns/musicxml"')])
def test_normalization_cleans_only_containers_emptied_by_removed_fingerings(prefix, namespace):
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    xml = f'<{prefix}score-partwise{namespace}><{prefix}note id="n"><{prefix}notations><{prefix}technical>\n<{prefix}fingering>1</{prefix}fingering>\n<{prefix}fingering substitution="yes">2</{prefix}fingering>\n</{prefix}technical></{prefix}notations></{prefix}note><{prefix}note id="empty"><{prefix}notations><{prefix}technical/></{prefix}notations></{prefix}note></{prefix}score-partwise>'
    result = canonical_musicxml(xml)
    assert result == f'<{prefix}score-partwise{namespace}><{prefix}note id="n"></{prefix}note><{prefix}note id="empty"><{prefix}notations><{prefix}technical/></{prefix}notations></{prefix}note></{prefix}score-partwise>'
    assert canonical_musicxml(result) == result


def test_normalization_preserves_identified_commented_and_nonempty_containers():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    for retained in (' id="keep"', ''):
        content = '' if retained else '<!-- keep --><?keep this?>'
        xml = f'<score><notations><technical{retained}>{content}<fingering>4</fingering></technical><slur number="1"/></notations></score>'
        assert canonical_musicxml(xml) == xml.replace('<fingering>4</fingering>', '')


def test_normalization_preserves_foreign_fingering_vocabulary():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    xml = '<score xmlns:x="urn:other"><technical><x:fingering>3</x:fingering></technical><fingering>2</fingering></score>'
    assert canonical_musicxml(xml) == xml


def test_normalization_is_noop_for_empty_or_annotation_free_sources():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    assert canonical_musicxml('') == ''
    xml = (ROOT / 'tests/fixtures/musical_fidelity/xml_quintuplets.musicxml').read_text()
    assert canonical_musicxml(xml) == xml


def test_normalization_handles_self_closing_fingering_and_quoted_angle_brackets():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    xml = '<score><technical><fingering print-object="no"/><fingering font-family="a>b">3</fingering><string>2</string></technical></score>'
    assert canonical_musicxml(xml) == '<score><technical><string>2</string></technical></score>'


def test_normalization_rejects_entity_generated_markup_instead_of_losing_other_ink():
    from piano_teacher.notation.audit_annotations import canonical_musicxml

    xml = '<!DOCTYPE score [<!ENTITY mixed "<fingering>3</fingering><string>2</string>">]><score><technical>&mixed;</technical></score>'
    with pytest.raises(ValueError, match='entity-generated markup'):
        canonical_musicxml(xml)


def test_canonical_piece_preserves_original_source_and_note_object_identities():
    from piano_teacher.notation.audit_annotations import canonical_piece

    note = Note(0, 1, 60, 0, 0, source_id='authoritative-source')
    phrase = Phrase(1, 1, 1, 0, 4, (note,))
    original = Piece('original', 80, (note,), (phrase,), source_musicxml=
        '<score><note id="authoritative-source"><notations><technical><fingering>4</fingering></technical></notations></note></score>')
    canonical = canonical_piece(original)
    assert canonical is not original
    assert '<fingering>' in original.source_musicxml
    assert canonical.source_musicxml == '<score><note id="authoritative-source"></note></score>'
    for field in fields(original):
        if field.name != 'source_musicxml':
            assert getattr(canonical, field.name) is getattr(original, field.name)
    assert canonical.notes[0] is note and canonical.phrases[0].notes[0] is note


def test_fixture_canonicalizes_authored_reference_without_mutating_piece(tmp_path):
    from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG
    from piano_teacher.score import import_piece
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    tree = ET.parse(ROOT / 'tests/fixtures/native_pixel_pitch_probe.musicxml')
    note = tree.find('part/measure/note')
    ET.SubElement(ET.SubElement(ET.SubElement(note, 'notations'), 'technical'), 'fingering').text = '3'
    source = tmp_path / 'authored.musicxml'
    tree.write(source)
    piece, _ = import_piece(source)
    original = piece.source_musicxml
    data, _ = fixture(AuditCase('authored', str(source), 1, 2, 'both'), piece=piece)
    assert data['capture_config'] == CANONICAL_CAPTURE_CONFIG
    assert '<fingering' not in data['xml'] and '<fingering' not in data['original_xml']
    assert piece.source_musicxml == original and '<fingering' in original


@pytest.fixture(scope='module')
def isolation_captures(tmp_path_factory):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from test_native_fingering import _godot, _run_godot
    from piano_teacher.notation.audit_annotations import CANONICAL_CAPTURE_CONFIG

    folder = tmp_path_factory.mktemp('canonical-fingering')
    data, _ = fixture(AuditCase('isolation', 'tests/fixtures/native_pixel_pitch_probe.musicxml', 1, 2, 'both'))
    data['capture_config'] = dict(CANONICAL_CAPTURE_CONFIG)
    data['sample_beats'] = [*range(8), .125]
    for event in data['model']['notation_events']:
        if event['kind'] == 'note' and event['is_attack']:
            event['fingering'] = dict(source_id=event['source_id'], finger=3,
                                     hand=event['staff'], origin='manual')
    path = folder / 'fixture.json'
    path.write_text(json.dumps(data))
    command = _godot()
    for script, output in [('canonical_fingering_isolation.gd', folder),
                           ('native_verovio_overlay.gd', folder / 'actual-canonical')]:
        output.mkdir(exist_ok=True)
        result = _run_godot([*command, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
            '--rendering-method', 'gl_compatibility', '--script', str(ROOT/'tests/godot'/script),
            '--', str(path), str(output)], timeout=60)
        log = result.stdout + result.stderr
        (output/'godot.log').write_text(log)
        assert result.returncode == 0, log
        assert 'SCRIPT ERROR' not in log and 'Parse Error' not in log, log
    return folder, data, json.loads((folder/'isolation-report.json').read_text())


def test_actual_framebuffer_is_identical_when_fingers_change_or_are_removed(isolation_captures):
    from test_native_fingering import _rgb, _verify_numbers
    from piano_teacher.notation.pixel_proof import verify_pixel_frames

    folder, data, report = isolation_captures
    assert report['editor_checks'] == []
    assert report['frames']
    for frame in report['frames']:
        original = _rgb(folder, frame['canonical'])
        assert np.array_equal(original, _rgb(folder, frame['canonical_changed']))
        assert np.array_equal(original, _rgb(folder, frame['canonical_removed']))
        assert frame['labels'], 'Normal application positive control must contain finger ink'
        _verify_numbers(folder, dict(frame, base=frame['canonical']), 16)
        assert not np.array_equal(_rgb(folder, frame['file']), _rgb(folder, frame['normal_changed']))
        assert np.array_equal(original, _rgb(folder, frame['normal_removed']))
    actual = folder/'actual-canonical'
    captured = {float(f['clock']): actual/f['file'] for f in
                json.loads((actual/'native-overlay-report.json').read_text())['frames']}
    proof = verify_pixel_frames(data['xml'], {at:path for at,path in captured.items() if at.is_integer()})
    assert proof['passed'], proof
    assert proof['notes_checked_from_pixels'] == 16
    assert np.array_equal(np.asarray(Image.open(captured[.125]).convert('RGB')),
                          _rgb(folder, report['frames'][0]['canonical']))


def test_genuine_music_corruption_near_fingering_is_still_rejected(isolation_captures, tmp_path):
    from piano_teacher.notation.pixel_proof import verify_pixel_frames
    from test_native_fingering import _rgb

    folder, data, report = isolation_captures
    actual = folder/'actual-canonical'
    screenshots = {float(f['clock']): actual/f['file'] for f in
                   json.loads((actual/'native-overlay-report.json').read_text())['frames']
                   if float(f['clock']).is_integer()}
    first = report['frames'][0]
    # These are actual score glyphs rendered with and without one musical
    # event. Reinsert the very same glyph beside a normal fingering label.
    good = np.asarray(Image.open(screenshots[0.0]).convert('RGB'))
    missing = _rgb(folder, report['missing_note']).astype('uint8')
    path = tmp_path/'removed-note.png'
    Image.fromarray(missing).save(path)
    proof = verify_pixel_frames(data['xml'], screenshots | {0.0:path})
    assert not proof['passed'], proof
    difference = np.max(np.abs(good.astype(int)-missing.astype(int)), axis=2) > 12
    ys, xs = np.where(difference)
    assert len(xs) > 12
    # Add authentic head/stem ink at the canonical position where its
    # optional finger normally lives. There is deliberately no label mask.
    label = next(v for v in first['labels'] if report['missing_id'] in v['event_ids'])
    target_x, target_y = round(good.shape[1]*.42), round(label['rect'][1])
    added = good.copy()
    dx, dy = target_x-round(np.median(xs)), target_y-round(np.median(ys))
    inside = (xs+dx >= 0) & (xs+dx < good.shape[1]) & (ys+dy >= 0) & (ys+dy < good.shape[0])
    added[ys[inside]+dy, xs[inside]+dx] = good[ys[inside], xs[inside]]
    path = tmp_path/'added-near-label.png'
    Image.fromarray(added).save(path)
    proof = verify_pixel_frames(data['xml'], screenshots | {0.0:path})
    assert not proof['passed'], proof


def test_dedicated_digit_oracle_rejects_corrupted_actual_fingering(isolation_captures, tmp_path):
    from test_native_fingering import _rgb, _verify_numbers

    folder, _, report = isolation_captures
    frame = report['frames'][0]
    label = frame['labels'][0]
    x,y,w,h = label['rect']
    x0,y0,x1,y1 = int(x),int(y),int(np.ceil(x+w)),int(np.ceil(y+h))
    pixels = _rgb(folder, frame['file']).astype('uint8')
    pixels[y0:y1,x0:x1] = _rgb(folder, frame['canonical'])[y0:y1,x0:x1]
    path = tmp_path/'erased-digit.png'
    Image.fromarray(pixels).save(path)
    with pytest.raises(AssertionError):
        _verify_numbers(folder, dict(frame, file=str(path), base=frame['canonical']), 16)
    wrong = _rgb(folder, frame['file']).astype('uint8')
    wrong[y0:y1,x0:x1] = _rgb(folder, frame['normal_changed'])[y0:y1,x0:x1]
    path = tmp_path/'wrong-digit.png'
    Image.fromarray(wrong).save(path)
    with pytest.raises(AssertionError):
        _verify_numbers(folder, dict(frame, file=str(path), base=frame['canonical']), 16)


@pytest.mark.parametrize('config', [None, {'version':1,'score_ink':'canonical','fingering_annotations':True},
    {'version':2,'score_ink':'canonical','fingering_annotations':False}])
def test_actual_capture_harness_rejects_missing_or_incompatible_annotation_mode(tmp_path, config):
    from test_native_fingering import _godot, _run_godot

    payload = tmp_path/'fixture.json'
    payload.write_text(json.dumps({} if config is None else {'capture_config':config}))
    result = _run_godot([*_godot(), '--headless', '--path', str(ROOT/'godot'), '--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(tmp_path)], timeout=10)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'canonical capture_config' in result.stdout + result.stderr
    assert not list(tmp_path.glob('native-*.png'))
