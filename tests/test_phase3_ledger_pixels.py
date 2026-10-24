"""Physical ledger ink is an obligation beyond identifying the notehead."""
from pathlib import Path
import json
import os
import shutil

from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_ledger_pixels

FIXTURE = Path(__file__).parent/'fixtures/native_ledger_chord'


@pytest.mark.skipif(not os.environ.get('DISPLAY'), reason='Actual framebuffer requires a display')
def test_dense_capture_clocks_do_not_hide_a_clear_neighboring_ledger_witness(tmp_path):
    from scripts.check_native_verovio_overlay import AuditCase, fixture, capture_clocks
    from test_extra_symbol_schedule import godot_run, ROOT
    source=tmp_path/'input.musicxml'
    source.write_text('''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part><score-part id="LH"><part-name>Left</part-name></score-part></part-list>
    <part id="RH"><measure number="1"><attributes><divisions>1</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>
    </attributes><note><rest/><duration>4</duration><type>whole</type></note></measure>
    <measure number="2"><note id="upper"><pitch><step>A</step><octave>5</octave></pitch>
    <duration>2</duration><type>half</type></note><note><rest/><duration>2</duration><type>half</type>
    </note></measure></part><part id="LH"><measure number="1"><attributes><divisions>1</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef>
    </attributes><note><rest/><duration>4</duration><type>whole</type></note></measure>
    <measure number="2"><note><rest/><duration>4</duration><type>whole</type></note></measure>
    </part></score-partwise>''')
    data,_=fixture(AuditCase('ledger-nearby',str(source),1,2,'right'))
    xml=data.pop('xml')
    data.update(phase3_full=True,full_symbol_inventory=True,sample_beats=capture_clocks(xml))
    payload=tmp_path/'fixture.json';payload.write_text(json.dumps(data))
    actual=godot_run(ROOT/'tests/godot/native_verovio_overlay.gd',[payload,tmp_path],graphical=True,timeout=120)
    assert actual.returncode==0,actual.stdout+actual.stderr
    report=verify_ledger_pixels(xml,tmp_path,hand='right')
    assert report['complete'],report
    row,=report['measured']
    observation=row['features']['ledger']
    assert observation['expected_steps']==[10]
    assert observation['evidence']['frame']!='native-4.00000.png'
    assert any(w.get('segments',[{}])[0].get('reason')=='Observed playhead covers required ledger ink'
               for w in observation['evidence']['witnesses'] if w.get('segments'))


def check(folder=FIXTURE):
    return verify_ledger_pixels((FIXTURE/'score.musicxml').read_text(), folder, hand='right')


def test_real_native_ledger_chord_proves_four_lines_for_three_source_events():
    report = check()
    assert report['complete'], report
    assert report['coverage']['expected'] == report['coverage']['verified'] == 4
    assert len(report['measured']) == 3
    assert sorted(r['features']['ledger']['expected_steps'] for r in report['measured']) == [[-2], [-2], [-2, -4]]
    for row in report['measured']:
        observation = row['features']['ledger']
        assert observation['status'] == 'verified'
        assert len(observation['matched_segments']) == len(observation['expected_steps'])
        for segment in observation['matched_segments']:
            assert segment['left_extension_spaces'] >= .12
            assert segment['right_extension_spaces'] >= .12
            assert segment['continuous']
        assert observation['evidence']['staff_lines']
    assert 'passed' not in report
    json.dumps(report)


@pytest.mark.parametrize('mutation', ['outside-head', 'head-only', 'detached', 'wrong-y', 'hole'])
def test_real_head_ink_or_wrong_ledger_relationship_cannot_replace_line(tmp_path, mutation):
    shutil.copytree(FIXTURE, tmp_path/'score')
    folder = tmp_path/'score'
    report = check(folder)
    row = next(r for r in report['measured'] if r['beat'] == 0.)
    observation = row['features']['ledger']
    assert observation['status'] == 'verified'
    segment = observation['matched_segments'][0]
    best_head = observation['evidence']['head_bbox']
    changed = set()
    for witness in observation['evidence']['witnesses']:
        if 'head_bbox' not in witness or witness['frame'] in changed:
            continue
        changed.add(witness['frame'])
        head = witness['head_bbox']
        delta = head[0]-best_head[0]
        left, top, right, bottom = segment['bbox']
        left, right = left+delta, right+delta
        path = folder/witness['frame']
        with Image.open(path) as raw:
            image = raw.convert('RGB')
        original = image.copy()
        draw = ImageDraw.Draw(image)
        background = image.getpixel((image.width-1, 0))
        if mutation == 'hole':
            x = head[0]-4
            draw.rectangle((x, top-1, x+1, bottom), fill=background)
        else:
            draw.rectangle((left-1, top-1, head[0]-1, bottom), fill=background)
            if mutation != 'outside-head':
                draw.rectangle((head[2], top-1, right+1, bottom), fill=background)
            if mutation in ('detached', 'wrong-y'):
                shift = round(witness['staff_gap']*.5)
                for a, b, sign in ((left, head[0], -1), (head[2], right, 1)):
                    crop = original.crop((a, top, b, bottom))
                    dx, dy = (sign*shift, 0) if mutation == 'detached' else (0, shift)
                    image.paste(crop, (a+dx, top+dy))
        image.save(path)
    assert changed
    after = check(folder)
    result = next(r for r in after['measured'] if r['source_id'] == row['source_id'])
    assert result['features']['ledger']['status'] != 'verified', result
    assert not after['complete']


def test_missing_frames_keep_all_required_source_steps_in_denominator(tmp_path):
    report = check(tmp_path)
    assert report['coverage']['expected'] == 4
    assert report['coverage']['verified'] == 0
    assert not report['complete']


def test_ledger_helper_ignores_native_geometry_and_keeps_existing_api_scope(tmp_path):
    from piano_teacher.notation.feature_pixels import verify_note_feature_pixels
    shutil.copytree(FIXTURE, tmp_path/'score')
    folder = tmp_path/'score'
    (folder/'fixture.json').write_text('not an atlas')
    (folder/'native-overlay-report.json').write_text('not geometry evidence')
    assert check(folder)['coverage']['verified'] == 4
    original = verify_note_feature_pixels((FIXTURE/'score.musicxml').read_text(), folder, hand='right')
    assert all('ledger' not in r['features'] for r in original['measured'])
