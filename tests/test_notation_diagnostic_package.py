"""The local verifier uploads representative real pixel/Verovio evidence."""
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.package_notation_diagnostics import package


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
