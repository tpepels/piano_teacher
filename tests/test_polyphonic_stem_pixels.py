"""Independent column/run ownership for simultaneous source voice groups."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import cairosvg
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
from piano_teacher.notation.reference_font import reference_glyphs

ROOT = Path(__file__).resolve().parents[1]


def source(groups, explicit=()):
    lanes = []
    for voice, pitches in enumerate(groups, 1):
        notes = []
        for index, (step, octave) in enumerate(pitches):
            stem = f'<stem>{explicit[voice-1]}</stem>' if explicit and index == 0 else ''
            notes.append(f'<note id="v{voice}n{index}">' + ('<chord/>' if index else '') +
                f'<pitch><step>{step}</step><octave>{octave}</octave></pitch>'
                f'<duration>1</duration><voice>{voice}</voice><type>quarter</type>{stem}</note>')
        lanes.append(('' if voice == 1 else '<backup><duration>4</duration></backup>') +
            ''.join(notes)+f'<note><rest/><duration>3</duration><voice>{voice}</voice>'
            '<type>half</type><dot/></note>')
    return ('<score-partwise version="4.0"><part-list><score-part id="RH">'
        '<part-name>Right hand</part-name></score-part></part-list><part id="RH">'
        '<measure number="1"><attributes><divisions>1</divisions>'
        '<time><beats>4</beats><beat-type>4</beat-type></time>'
        '<clef><sign>G</sign><line>2</line></clef></attributes>'+
        ''.join(lanes)+'</measure></part></score-partwise>')


def picture(folder, groups, directions, *, one_shaft=False):
    """External font heads and controlled physical shafts on measured rails."""
    image = Image.new('RGB', (1000, 480), (16, 41, 35))
    pen = ImageDraw.Draw(image)
    for base in (120, 320):
        for i in range(5):
            pen.line((0, base+20*i, 999, base+20*i), fill=(73, 83, 77))
    glyph = reference_glyphs()['head_black']
    b = glyph['bounds']
    width, height = round(b[2]*20/250), round(b[3]*20/250)
    head = Image.open(BytesIO(cairosvg.svg2png(bytestring=glyph['svg'].encode(),
        output_width=width, output_height=height))).convert('RGBA')
    ys = []
    for group in groups:
        positions = [200-(octave*7+'CDEFGAB'.index(step)-30)*10 for step, octave in group]
        ys.append(positions)
        for y in positions:
            image.paste(head, (round(420-width/2), round(y+b[1]*20/250)), head.getchannel('A'))
    if one_shaft:
        pen.line((432, min(y for lane in ys for y in lane)-70,
                  432, max(y for lane in ys for y in lane)), fill=(231, 240, 232), width=2)
    else:
        for lane, direction in zip(ys, directions):
            x = 432 if direction == 'up' else 408
            top = min(lane)-70 if direction == 'up' else min(lane)
            bottom = max(lane) if direction == 'up' else max(lane)+70
            pen.line((x, top, x, bottom), fill=(231, 240, 232), width=2)
    image.save(folder/'native-0.00000.png')


def stems(report):
    return {row['source_id']:row['features']['stem'] for row in report['measured']}


@pytest.mark.parametrize('groups,directions', [
    ([(('C', 5),), (('G', 4),)], ['up', 'down']),
    ([(('G', 5),), (('E', 4),)], ['up', 'up']),
    ([(('G', 5), ('B', 5)), (('C', 4), ('E', 4))], ['up', 'down']),
])
def test_separate_voice_columns_or_disjoint_runs_have_physical_owners(tmp_path, groups, directions):
    picture(tmp_path, groups, directions)
    report = verify_note_feature_pixels(source(groups), tmp_path, hand='right')
    actual = stems(report)
    assert all(value['status'] == 'verified' for value in actual.values()), actual
    assert report['by_construct']['stem']['verified'] == sum(map(len, groups))
    assert len({value['evidence']['group_id'] for value in actual.values()}) == 2
    assert len({value['evidence']['physical_shaft_id'] for value in actual.values()}) == 2
    for voice, group in enumerate(groups, 1):
        for index in range(len(group)):
            evidence = actual[f'v{voice}n{index}']['evidence']
            assert evidence['direction'] == directions[voice-1]
            assert evidence['shared_source_ids'] == [f'v{voice}n{i}' for i in range(len(group))]


@pytest.mark.parametrize('mutation', ['missing', 'one-shared-shaft'])
def test_missing_or_duplicated_voice_shaft_cannot_borrow_another_group(tmp_path, mutation):
    groups = [(('G', 5),), (('E', 4),)]
    picture(tmp_path, groups, ['up', 'up'], one_shaft=mutation == 'one-shared-shaft')
    if mutation == 'missing':
        image = Image.open(tmp_path/'native-0.00000.png').convert('RGB')
        ImageDraw.Draw(image).rectangle((430, 130, 435, 175), fill=(16, 41, 35))
        image.save(tmp_path/'native-0.00000.png')
    report = verify_note_feature_pixels(source(groups), tmp_path, hand='right')
    actual = stems(report)
    assert actual['v2n0']['status'] != 'verified', actual
    if mutation == 'one-shared-shaft':
        assert all(row['status'] != 'verified' for row in actual.values()), actual
    else:
        assert actual['v1n0']['status'] == 'verified', actual


def test_explicit_source_stem_cannot_be_replaced_by_the_opposite_direction(tmp_path):
    groups = [(('G', 5),), (('E', 4),)]
    picture(tmp_path, groups, ['down', 'down'])
    report = verify_note_feature_pixels(source(groups, explicit=['up', 'down']), tmp_path, hand='right')
    actual = stems(report)
    assert actual['v1n0']['status'] != 'verified', actual
    assert actual['v2n0']['status'] == 'verified', actual


@pytest.mark.parametrize('groups,explicit', [
    ([(('C', 5),), (('G', 4),)], ()),
    ([(('C', 5),), (('G', 4),)], ['up', 'down']),
    ([(('C', 5),), (('G', 4),)], ['down', 'up']),
    ([(('C', 5), ('E', 5))], ['up']),
])
def test_actual_native_source_groups_own_their_shafts_and_erasure_blocks_them(tmp_path, groups, explicit):
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        pytest.skip('Actual native framebuffer needs Godot and a desktop')
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    xml = source(groups, explicit=explicit)
    path = tmp_path/'source.musicxml'
    path.write_text(xml)
    data, _ = fixture(AuditCase('polyphonic-stem', str(path), 1, 1, 'right'))
    data['sample_beats'] = [0]
    data['phase3_full'] = True
    payload = tmp_path/'fixture.json'
    payload.write_text(json.dumps(data))
    (tmp_path/'captured-score.musicxml').write_text(data['xml'])
    result = subprocess.run([binary, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
        '--rendering-method', 'gl_compatibility', '--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    (tmp_path/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    payload.unlink()
    report = verify_note_feature_pixels(xml, tmp_path, hand='right')
    (tmp_path/'stem-proof.json').write_text(json.dumps(report, indent=2))
    assert report['by_construct']['stem']['verified'] == 2, stems(report)
    target = stems(report)['v1n0']['evidence']
    x0, top, x1, bottom = target['bbox']
    y0, y1 = ((top+15, top+25) if target['direction'] == 'up' else
              (bottom-25, bottom-15))
    image = Image.open(tmp_path/'native-0.00000.png').convert('RGB')
    ImageDraw.Draw(image).rectangle((x0, y0, x1-1, y1), fill=image.getpixel((0, 0)))
    image.save(tmp_path/'native-0.00000.png')
    erased = verify_note_feature_pixels(xml, tmp_path, hand='right')
    (tmp_path/'stem-erasure-proof.json').write_text(json.dumps(erased, indent=2))
    assert stems(erased)['v1n0']['status'] != 'verified', stems(erased)


@pytest.mark.parametrize('groups', [
    [(('D', 5),), (('F', 5),)],
    [(('E', 4),), (('G', 4),)],
    [(('C', 5), ('E', 5)), (('G', 5),)],
    [(('C', 5),), (('E', 5), ('G', 5))],
])
def test_native_independent_half_voices_keep_separate_shafts_and_erasure_is_local(tmp_path, groups):
    """Pitch-only auto direction must not merge two authored voice shafts."""
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        pytest.skip('Actual native framebuffer needs Godot and a desktop')
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    tree = ET.fromstring(source(groups))
    for note in tree.findall('.//measure/note'):
        note.find('duration').text = '2'
        note.find('type').text = 'half'
        for dot in note.findall('dot'):
            note.remove(dot)
    xml = ET.tostring(tree, encoding='unicode')
    path = tmp_path/'source.musicxml'
    path.write_text(xml)
    data, _ = fixture(AuditCase('independent-half-voices', str(path), 1, 1, 'right'))
    data['sample_beats'] = [0]
    data['phase3_full'] = True
    payload = tmp_path/'fixture.json'
    payload.write_text(json.dumps(data))
    result = subprocess.run([binary, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
        '--rendering-method', 'gl_compatibility', '--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    (tmp_path/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    payload.unlink()
    report = verify_note_feature_pixels(xml, tmp_path, hand='right')
    (tmp_path/'intact-stem-proof.json').write_text(json.dumps(report, indent=2))
    actual = stems(report)
    assert len(actual) == sum(map(len, groups))
    assert all(row['status'] == 'verified' for row in actual.values()), actual
    assert len({row['evidence']['physical_shaft_id'] for row in actual.values()}) == 2

    target = actual['v1n0']['evidence']
    x0, top, x1, bottom = target['bbox']
    y0, y1 = ((top+15, top+25) if target['direction'] == 'up' else
              (bottom-25, bottom-15))
    with Image.open(tmp_path/'native-0.00000.png') as raw:
        image = raw.convert('RGB')
    image.save(tmp_path/'intact.png')
    ImageDraw.Draw(image).rectangle((x0, y0, x1-1, y1), fill=image.getpixel((0, 0)))
    image.save(tmp_path/'native-0.00000.png')
    erased = verify_note_feature_pixels(xml, tmp_path, hand='right')
    (tmp_path/'erased-stem-proof.json').write_text(json.dumps(erased, indent=2))
    after = stems(erased)
    assert all(after[f'v1n{i}']['status'] != 'verified' for i in range(len(groups[0]))), after
    assert all(after[f'v2n{i}']['status'] == 'verified' for i in range(len(groups[1]))), after


@pytest.mark.parametrize('filename,last_bar,clock', [
    ('midi_parallel_unisons.mid', 1, 0),
    ('xml_parallel_tied_voices.musicxml', 2, 4),
])
def test_actual_parallel_unison_types_need_their_own_heads_and_shafts(tmp_path, filename, last_bar, clock):
    """A filled quarter cannot certify a coincident hollow half, or vice versa."""
    binary = shutil.which('godot') or shutil.which('godot4')
    if not binary or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        pytest.skip('Actual native framebuffer needs Godot and a desktop')
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from piano_teacher.notation.feature_pixels import _register, _feature_glyphs
    from piano_teacher.notation.pixel_proof import detect_staff_lines
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.raster_matching import photographed_playhead_columns
    from piano_teacher.notation.symbol_pixel_proof import bright

    path = ROOT/'tests/fixtures/musical_fidelity'/filename
    data, _ = fixture(AuditCase('parallel-source-unisons', str(path), 1, last_bar, 'right'))
    xml = path.read_text() if path.suffix == '.musicxml' else data['xml']
    written = read_written_score(xml)
    notes = [n for n in written.symbols if n['kind'] == 'note' and float(n['beat']) == clock]
    assert len(notes) == 2 and {n['note_type'] for n in notes} == {'half', 'quarter'}
    assert {n['spelling'] for n in notes} == {('C', 0, 4)}
    data['sample_beats'] = sorted({float(n['beat']) for n in written.symbols})
    data['phase3_full'] = True
    payload = tmp_path/'fixture.json'
    payload.write_text(json.dumps(data))
    result = subprocess.run([binary, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
        '--rendering-method', 'gl_compatibility', '--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    (tmp_path/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode == 0, result.stdout+result.stderr
    payload.unlink()
    report = verify_note_feature_pixels(xml, tmp_path, hand='right')
    selected = [r for r in report['measured'] if r['beat'] == clock]
    (tmp_path/'intact-stem-proof.json').write_text(json.dumps(report, indent=2))
    assert len(selected) == 2
    assert all(r['features']['stem']['status'] == 'verified' for r in selected), selected
    assert len({r['features']['stem']['evidence']['physical_shaft_id'] for r in selected}) == 2
    filename = tmp_path/f'native-{clock:.5f}.png'
    with Image.open(filename) as raw:
        intact = raw.convert('RGB')
    intact.save(tmp_path/'intact.png')
    heads, _ = _register(bright(intact), detect_staff_lines(intact), written, notes,
        _feature_glyphs(), occlusion_columns=photographed_playhead_columns(intact))
    assert len(heads) == 2
    a, b = heads.values()
    assert a['support'].isdisjoint(b['support'])
    for note in notes:
        sid = note.get('id') or note['source']['id']
        erased = intact.copy()
        x0, y0, x1, y1 = heads[note['source']['id']]['bbox']
        ImageDraw.Draw(erased).rectangle((x0, y0, x1-1, y1-1), fill=erased.getpixel((0, 0)))
        erased.save(filename)
        proof = verify_note_feature_pixels(xml, tmp_path, hand='right')
        (tmp_path/f'erased-{note["note_type"]}-proof.json').write_text(json.dumps(proof, indent=2))
        damaged = next(r for r in proof['measured'] if r['source_id'] == sid)
        assert damaged['features']['stem']['status'] != 'verified', damaged
        assert not all(r['features']['stem']['status'] == 'verified'
            for r in proof['measured'] if r['beat'] == clock), proof
    intact.save(filename)
