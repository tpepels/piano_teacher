"""The local verifier uploads representative real pixel/Verovio evidence."""
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.package_notation_diagnostics import package


def test_interrupted_case_without_an_audit_is_packaged(tmp_path):
    root=tmp_path/'shard';case=root/'Liszt'/'unfinished';case.mkdir(parents=True)
    (root/'run.log').write_text('PROGRESS 631/632; note-features\n')
    (root/'summary.json').write_text('{partial JSON from a killed old run')
    (case/'case-state.json').write_text(json.dumps(dict(stage='note-features',pid=123)))
    (case/'fixture.json').write_text('{"hand":"both"}')
    (case/'worker-stack.log').write_text('raster_matching.py claim\n')
    (case/'score.musicxml').write_text('<score-partwise/>')
    (case/'verovio-0.svg').write_text('<svg/>')
    (case/'native-0.00000.png').write_bytes(b'retained framebuffer')
    output=tmp_path/'triage.zip'
    summary=package(root,output)
    assert summary['interrupted_cases']==['Liszt/unfinished']
    with ZipFile(output) as archive:
        names=set(archive.namelist())
        assert {'summary.json','run.log','Liszt/unfinished/case-state.json',
                'Liszt/unfinished/worker-stack.log','Liszt/unfinished/score.musicxml',
                'Liszt/unfinished/verovio-0.svg','Liszt/unfinished/native-0.00000.png'}<=names


def test_old_audit_cannot_hide_a_newer_incomplete_capture(tmp_path):
    import os
    root=tmp_path/'shard';case=root/'piece'/'case';case.mkdir(parents=True)
    (case/'audit.json').write_text('{"passed":true,"errors":[]}')
    os.utime(case/'audit.json',(100,100))
    (case/'fixture.json').write_text('{"new_capture":true}')
    (case/'native-0.00000.png').write_bytes(b'new frame')
    output=tmp_path/'triage.zip'
    result=package(root,output)
    assert result['interrupted_cases']==['piece/case']
    with ZipFile(output) as archive:
        assert 'piece/case/previous-audit.json' in archive.namelist()
        assert 'piece/case/audit.json' not in archive.namelist()


def test_failure_package_has_source_and_real_frame_witnesses(tmp_path):
    root = tmp_path / 'shard'
    case = root / 'piano' / 'original-0001-0004-right'
    case.mkdir(parents=True)
    (root / 'summary.json').write_text(json.dumps({'passed': False, 'failures': ['bad']}))
    (root / 'run.log').write_text('FAIL original-0001-0004-right\n')
    errors = ['Unexpected-symbol check native-0.00000.png beat 0.0: '
              'Unowned authentic timed-symbol contour',
              'measure 1 right voice 1 tuplet: unverified '
              'Reference source event IDs are absent or ambiguous']
    (case / 'audit.json').write_text(json.dumps({'errors': errors, 'passed': False}))
    (case / 'native-0.00000.png').write_bytes(b'actual-capture-placeholder')
    (case / 'verovio-0.svg').write_text('<svg/>')
    (case / 'independent-unexpected-symbols.json').write_text(json.dumps({
        'measured': [{'status': 'mismatch', 'frame': 'native-0.00000.png',
                      'evidence': {'unexpected': [{'family': 'head',
                                                 'bbox': [20, 30, 40, 50]}]}}]}))
    output = tmp_path / 'triage.zip'
    summary = package(root, output)
    assert summary['error_counts']['unowned-symbol'] == 1
    assert summary['error_counts']['reference-group'] == 1
    with ZipFile(output) as archive:
        names = set(archive.namelist())
        assert 'triage-summary.json' in names
        assert 'summary.json' in names and 'run.log' in names
        assert 'piano/original-0001-0004-right/audit.json' in names
        assert 'piano/original-0001-0004-right/verovio-0.svg' in names
        assert 'piano/original-0001-0004-right/native-0.00000.png' in names
        excerpt = json.loads(archive.read('piano/original-0001-0004-right/unexpected-excerpt.json'))
        assert excerpt[0]['evidence']['unexpected'][0]['bbox'] == [20, 30, 40, 50]
