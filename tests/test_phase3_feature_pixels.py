"""CPU-only regressions on retained, real native PNGs (no atlas or renderer)."""
from pathlib import Path
import json
import shutil

from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.feature_pixels import verify_note_feature_pixels

FIXTURES = Path(__file__).parent / 'fixtures/feature_pixels'
STATUSES = ('verified', 'unverified', 'ambiguous', 'unsupported', 'mismatch')


def score(case):
    return (FIXTURES / case / 'source.musicxml').read_text()


def check(case, folder=None, **kwargs):
    return verify_note_feature_pixels(score(case), folder or FIXTURES / case,
                                      hand='right', **kwargs)


def feature(report, beat, construct, spelling=None):
    rows = [r for r in report['measured'] if r['beat'] == beat
            and (spelling is None or tuple(r['spelling']) == spelling)]
    assert len(rows) == 1
    return rows[0]['features'][construct]


def copied(case, tmp_path):
    dest = tmp_path / case
    shutil.copytree(FIXTURES / case, dest)
    return dest


def erase(folder, beat, bbox):
    path = folder / f'native-{beat:.5f}.png'
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    # Local actual background; no renderer diagnostics or geometry.
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = bbox
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=image.getpixel((image.width - 1, 0)))
    image.save(path)


def test_retained_rhythm_features_have_bound_event_evidence():
    report = check('rhythms')
    assert 'passed' not in report  # bounded feature coverage is not a global proof
    assert report['coverage']['expected'] == 11
    assert report['by_construct']['stem']['verified'] == 7
    assert report['by_construct']['flag']['verified'] == 3
    assert report['by_construct']['dot']['ambiguous'] == 1
    assert not report['complete']
    for row in report['measured']:
        assert {'source_id', 'measure', 'staff', 'voice', 'beat', 'spelling', 'features'} <= row.keys()
        for result in row['features'].values():
            assert result['reason'] and result['evidence']
    json.dumps(report)


def test_all_retained_explicit_accidentals_identify_the_expected_family():
    report = check('accidentals')
    assert report['by_construct']['accidental']['expected'] == 8
    assert report['by_construct']['accidental']['verified'] == 8
    assert report['by_construct']['stem']['verified'] == 8


@pytest.mark.parametrize(('case', 'beat', 'construct'), [
    ('rhythms', 7., 'stem'), ('rhythms', 7., 'flag'),
    ('waltz', 3., 'dot'), ('accidentals', 0., 'accidental'),
])
def test_erasure_cannot_borrow_nearby_real_ink(case, beat, construct, tmp_path):
    folder = copied(case, tmp_path)
    before = check(case, folder)
    result = feature(before, beat, construct)
    assert result['status'] == 'verified', result
    erase(folder, beat, result['evidence']['bbox'])
    after = check(case, folder)
    assert feature(after, beat, construct)['status'] != 'verified'
    assert not after['complete']


def test_wrong_flag_count_does_not_pass_the_existing_family_margin():
    xml = score('rhythms').replace('<type>eighth</type>', '<type>16th</type>')
    report = verify_note_feature_pixels(xml, FIXTURES / 'rhythms', hand='right')
    assert feature(report, 7., 'flag')['status'] != 'verified'
    assert report['by_construct']['flag']['verified'] == 0


def test_wrong_accidental_and_double_dot_do_not_pass_neighbor_ink():
    xml = score('accidentals').replace('<accidental>sharp</accidental>', '<accidental>flat</accidental>')
    report = verify_note_feature_pixels(xml, FIXTURES / 'accidentals', hand='right')
    assert feature(report, 0., 'accidental')['status'] != 'verified'
    xml = score('rhythms').replace('<dot/>', '<dot/><dot/>')
    report = verify_note_feature_pixels(xml, FIXTURES / 'rhythms', hand='right')
    assert feature(report, 8., 'dot')['status'] != 'verified'


def test_source_chords_legitimately_share_stem_evidence():
    report = check('chords')
    assert report['by_construct']['stem']['expected'] == 24
    assert report['by_construct']['stem']['verified'] == 12
    assert report['by_construct']['stem']['unverified'] == 12
    rows = [r for r in report['measured'] if r['beat'] == 4.]
    ids = {r['features']['stem']['evidence']['group_id'] for r in rows}
    assert len(ids) == 1
    assert all(len(r['features']['stem']['evidence']['shared_source_ids']) == 3 for r in rows)


def test_erased_common_chord_stem_blocks_all_group_members(tmp_path):
    folder = copied('chords', tmp_path)
    report = check('chords', folder)
    result = feature(report, 4., 'stem', ('G', 0, 4))
    erase(folder, 4., result['evidence']['bbox'])
    report = check('chords', folder)
    rows = [r for r in report['measured'] if r['beat'] == 4.]
    assert all(r['features']['stem']['status'] != 'verified' for r in rows)


def test_stale_or_forged_pitch_report_cannot_authorize_erased_image(tmp_path):
    folder = copied('rhythms', tmp_path)
    forged = dict(measured=[dict(source_id='forged', beat=7., staff='right',
                                status='verified', target_y=253., match=1.)])
    result = feature(check('rhythms', folder), 7., 'flag')
    erase(folder, 7., result['evidence']['bbox'])
    report = check('rhythms', folder, pitch_report=forged)
    assert feature(report, 7., 'flag')['status'] != 'verified'


def test_missing_frames_and_dense_voices_remain_blocking(tmp_path):
    folder = copied('chords', tmp_path)
    (folder / 'native-0.00000.png').unlink()
    report = check('chords', folder)
    assert not report['complete']
    assert sum(report['coverage'][s] for s in STATUSES) == report['coverage']['expected']
    assert report['by_construct']['stem']['unverified'] >= 3
    # All three notes become separate same-onset voices. They cannot share
    # one physical stem merely because their onset and staff agree.
    xml = '''<score-partwise><part-list><score-part id="RH"><part-name>Right</part-name>
    </score-part></part-list><part id="RH"><measure number="1"><attributes>
    <divisions>1</divisions><clef><sign>G</sign><line>2</line></clef></attributes>
    <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
    <backup><duration>1</duration></backup>
    <note><pitch><step>E</step><octave>4</octave></pitch><duration>1</duration><voice>2</voice><type>quarter</type></note>
    <backup><duration>1</duration></backup>
    <note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration><voice>3</voice><type>quarter</type></note>
    </measure></part></score-partwise>'''
    report = verify_note_feature_pixels(xml, FIXTURES / 'chords')
    assert report['by_construct']['stem']['verified'] == 0
    assert not report['complete']


def test_implicit_accidentals_use_source_spelling_state_not_just_explicit_tags():
    xml = score('accidentals')
    import re
    xml = re.sub(r'<accidental>[^<]+</accidental>', '', xml)
    report = verify_note_feature_pixels(xml, FIXTURES / 'accidentals', hand='right')
    assert report['by_construct']['accidental']['expected'] == 8
    assert report['by_construct']['accidental']['verified'] == 8


def test_unsupported_supported_notation_is_blocking_and_hand_validation():
    xml = score('rhythms').replace('<type>eighth</type>', '<type>256th</type>')
    report = verify_note_feature_pixels(xml, FIXTURES / 'rhythms', hand='right')
    assert report['by_construct']['flag']['unsupported'] == 3
    assert not report['complete']
    with pytest.raises(ValueError):
        verify_note_feature_pixels(score('rhythms'), FIXTURES / 'rhythms', hand='feet')


def test_fixture_atlas_and_native_diagnostics_are_never_opened(tmp_path):
    folder = copied('accidentals', tmp_path)
    (folder / 'fixture.json').write_text('invalid atlas, deliberately unreadable JSON')
    (folder / 'native-overlay-report.json').write_text('invalid renderer geometry')
    assert check('accidentals', folder)['by_construct']['accidental']['verified'] == 8
