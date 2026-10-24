"""Source-pair ownership and real connected curve ink, independent of native assets."""
from io import BytesIO
from pathlib import Path
import json

import cairosvg
import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation import symbol_pixel_proof as proof
from piano_teacher.notation.reference_font import reference_glyphs


def score(*, construct='tie', voice='1', extra=''):
    start = ('<tie type="start"/><notations><tied type="start"/></notations>'
             if construct == 'tie' else '<notations><slur type="start" number="7"/></notations>')
    stop = ('<tie type="stop"/><notations><tied type="stop"/></notations>'
            if construct == 'tie' else '<notations><slur type="stop" number="7"/></notations>')
    return ('<score-partwise version="4.0"><part-list><score-part id="RH">'
            '<part-name>Right hand</part-name></score-part></part-list><part id="RH">'
            '<measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats>'
            '<beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>'
            f'<note id="a"><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration>'
            f'<voice>{voice}</voice><type>half</type>{start}</note>'
            f'<note id="b"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>'
            f'<voice>{voice}</voice><type>quarter</type>{stop}</note>'
            f'<note><rest/><duration>1</duration><voice>{voice}</voice><type>quarter</type></note>'
            +extra+'</measure></part></score-partwise>')


def _stamp(image, name, x, y=150, gap=20):
    glyph = reference_glyphs()[name]
    b = glyph['bounds']
    w, h = max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250))
    png = cairosvg.svg2png(bytestring=glyph['svg'].encode(), output_width=w, output_height=h)
    image.paste(Image.open(BytesIO(png)), (round(x-w/2), round(y+b[1]*gap/250)),
                Image.open(BytesIO(png)).getchannel('A'))


def pictures(folder, *, curve='arc', displacement=0, bow=24):
    """Controlled ink with an actual 240-pixel translation between onset frames."""
    folder.mkdir(exist_ok=True)
    for beat, shift in ((0, 0), (2, -240)):
        image = Image.new('RGB', (1000, 480), (16, 41, 35))
        pen = ImageDraw.Draw(image)
        for base in (120, 320):
            for i in range(5):
                pen.line((0, base+20*i, 999, base+20*i), fill=(73, 83, 77))
        _stamp(image, 'head_half', 420+shift)
        _stamp(image, 'head_black', 660+shift)
        if curve != 'none':
            points = [(round(436+shift+t*208), round(157+displacement+4*bow*t*(1-t)))
                      for t in np.linspace(0, 1, 209)]
            if curve in ('line', 'beam'):
                points = [points[0], points[-1]]
            pen.line(points, fill=(231, 240, 232), width=7 if curve == 'beam' else 2)
        image.save(folder/f'native-{beat:.5f}.png')


def observe(xml, folder, **kwargs):
    api = getattr(proof, 'verify_connector_pixels', None)
    assert callable(api), 'Missing per-source-pair connector pixel API'
    return api(xml, folder, **kwargs)


def test_connector_endpoint_cannot_identify_a_filled_ledger_head_as_half():
    from piano_teacher.notation.proof import read_written_score
    xml = score().replace('<step>C</step><octave>5</octave>', '<step>C</step><octave>4</octave>')
    written = read_written_score(xml)
    image = Image.new('RGB',(400,240),(16,41,35))
    pen = ImageDraw.Draw(image)
    for bottom in (100,194):
        for line in range(5):
            y = round(bottom+(line-4)*8.5)
            pen.line((0,y,399,y),fill=(73,83,77))
    _stamp(image,'head_black',168,y=108.5,gap=8.5)
    pen.line((158,107,177,107),fill=(229,242,234),width=2)
    note = next(n for n in written.symbols if n['id']=='a')
    assert proof._connector_head(image,written,note,168) is None


def test_tie_has_per_source_pair_connected_curvature_and_attachment_evidence(tmp_path):
    pictures(tmp_path)
    report = observe(score(), tmp_path, constructs=('tie',))
    assert report['complete'], report
    row, = report['observations']
    assert row['source_ids'] == ['a', 'b'] and row['construct'] == 'tie'
    assert row['status'] == 'verified'
    evidence = row['evidence']
    assert evidence['connected_pixels'] > 100
    assert evidence['curvature_spaces'] > .2
    assert len(evidence['heads']) == 2 and evidence['pixel_runs']
    json.dumps(report)  # Canonical runner can retain this observation verbatim.


@pytest.mark.parametrize('curve,displacement', [('none', 0), ('line', 0), ('beam', 0), ('arc', 35)])
def test_erasure_straight_beam_and_wrong_endpoint_cannot_replace_tie(tmp_path, curve, displacement):
    pictures(tmp_path, curve=curve, displacement=displacement)
    row, = observe(score(), tmp_path, constructs=('tie',))['observations']
    assert row['status'] != 'verified', row


def test_gap_in_curve_is_not_a_connected_tie(tmp_path):
    pictures(tmp_path)
    for path in tmp_path.glob('*.png'):
        image = Image.open(path).convert('RGB')
        x = 540 if '0.00000' in path.name else 300
        ImageDraw.Draw(image).rectangle((x, 155, x+5, 190), fill=(16, 41, 35))
        image.save(path)
    assert not observe(score(), tmp_path, constructs=('tie',))['complete']


def test_missing_offscreen_endpoint_and_malformed_orphan_are_explicit_unverified(tmp_path):
    pictures(tmp_path)
    (tmp_path/'native-2.00000.png').unlink()
    row, = observe(score(), tmp_path, constructs=('tie',))['observations']
    assert row['status'] == 'unverified' and row['evidence']['reason']
    orphan = score().replace('<tie type="start"/>', '').replace('<tied type="start"/>', '')
    row, = observe(orphan, tmp_path, constructs=('tie',))['observations']
    assert row['source_ids'] == ['b'] and row['status'] == 'unverified'


def test_native_reports_or_atlas_cannot_authorize_missing_connector_ink(tmp_path):
    pictures(tmp_path, curve='none')
    for name in ('fixture.json', 'native-overlay-report.json', 'independent-pixels.json'):
        (tmp_path/name).write_text(json.dumps(dict(complete=True, status='verified',
            density=1, noteheads=[dict(id='a', x=420, y=150)], ties=[dict(source_ids=['a', 'b'])])))
    assert not observe(score(), tmp_path, constructs=('tie',))['complete']


def test_overlapping_stem_is_explicit_unverified_not_a_thin_curve(tmp_path):
    pictures(tmp_path)
    for path in tmp_path.glob('*.png'):
        image = Image.open(path).convert('RGB')
        x = 540 if '0.00000' in path.name else 300
        ImageDraw.Draw(image).line((x, 130, x, 210), fill=(231, 240, 232), width=2)
        image.save(path)
    row, = observe(score(), tmp_path)['observations']
    assert row['status'] == 'unverified'
    assert 'overlap' in row['evidence']['reason'].lower()


@pytest.mark.parametrize('bow', [12, -36])
def test_slur_endpoints_have_source_ownership_without_prescribing_a_curve_shape(tmp_path, bow):
    pictures(tmp_path, bow=bow)
    report = observe(score(construct='slur'), tmp_path, constructs=('slur',))
    row, = report['observations']
    assert row['source_ids'] == ['a', 'b'] and row['construct'] == 'slur'
    assert row['status'] == 'verified', report


def test_one_real_curve_cannot_certify_both_a_tie_and_a_slur(tmp_path):
    pictures(tmp_path)
    xml = score().replace('<tied type="start"/>', '<tied type="start"/><slur type="start"/>')
    xml = xml.replace('<tied type="stop"/>', '<tied type="stop"/><slur type="stop"/>')
    report = observe(xml, tmp_path, constructs=('tie', 'slur'))
    assert len(report['observations']) == 2
    assert all(row['status'] == 'unverified' for row in report['observations'])
    assert all('shared' in row['evidence']['reason'] for row in report['observations'])


def test_slur_orphan_is_retained_in_the_denominator(tmp_path):
    pictures(tmp_path)
    xml = score(construct='slur').replace('<slur type="start" number="7"/>', '')
    report = observe(xml, tmp_path, constructs=('slur',))
    row, = report['observations']
    assert row['source_ids'] == ['b'] and row['status'] == 'unverified'


def test_tie_continuation_is_two_written_pairs_not_one_collapsed_attack(tmp_path):
    pictures(tmp_path)
    xml = score().replace('<tie type="stop"/>', '<tie type="stop"/><tie type="start"/>')
    xml = xml.replace('<tied type="stop"/>', '<tied type="stop"/><tied type="start"/>')
    xml = xml.replace('<note><rest/><duration>1</duration><voice>1</voice><type>quarter</type></note>',
        '<note id="c"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>'
        '<voice>1</voice><type>quarter</type><tie type="stop"/>'
        '<notations><tied type="stop"/></notations></note>')
    result = observe(xml, tmp_path, constructs=('tie',))
    assert [row['source_ids'] for row in result['observations']] == [['a', 'b'], ['b', 'c']]
    assert result['coverage']['expected'] == 2 and not result['complete']


def test_reused_slur_number_cannot_pair_across_parts(tmp_path):
    pictures(tmp_path)
    xml = score(construct='slur')
    # Put the stop in another part. Two orphan declarations must not become
    # one claimed curve just because their number and pitches coincide.
    xml = xml.replace('<slur type="stop" number="7"/>', '')
    second = ('<part id="LH"><measure number="1"><attributes><divisions>1</divisions>'
        '<clef><sign>F</sign><line>4</line></clef></attributes><note id="foreign">'
        '<pitch><step>C</step><octave>3</octave></pitch><duration>4</duration>'
        '<type>whole</type><notations><slur type="stop" number="7"/></notations>'
        '</note></measure></part>')
    xml = xml.replace('</score-partwise>', second+'</score-partwise>')
    report = observe(xml, tmp_path, constructs=('slur',))
    assert sorted(row['source_ids'] for row in report['observations']) == [['a'], ['foreign']]
    assert all(row['status'] == 'unverified' for row in report['observations'])


def test_duplicate_source_ids_and_declared_wrong_side_cannot_authorize_tie(tmp_path):
    pictures(tmp_path)
    duplicate = score().replace('id="b"', 'id="a"')
    assert not observe(duplicate, tmp_path, constructs=('tie',))['complete']
    above = score().replace('<tied type="start"/>', '<tied type="start" placement="above"/>')
    assert not observe(above, tmp_path, constructs=('tie',))['complete']


def test_curve_ending_closer_to_another_head_has_no_unique_source_ownership(tmp_path):
    pictures(tmp_path, curve='none')
    for path in tmp_path.glob('*.png'):
        image = Image.open(path).convert('RGB')
        shift = 0 if '0.00000' in path.name else -240
        _stamp(image, 'head_black', 682+shift, 180)
        points = [(round(436+shift+234*t), round(157+10*t+96*t*(1-t)))
                  for t in np.linspace(0, 1, 235)]
        ImageDraw.Draw(image).line(points, fill=(231, 240, 232), width=2)
        image.save(path)
    row, = observe(score(), tmp_path, constructs=('tie',))['observations']
    assert row['status'] == 'unverified', row


def test_two_slur_numbers_cannot_double_own_one_pixel_curve(tmp_path):
    pictures(tmp_path)
    xml = score(construct='slur').replace('<slur type="start" number="7"/>',
        '<slur type="start" number="7"/><slur type="start" number="8"/>')
    xml = xml.replace('<slur type="stop" number="7"/>',
        '<slur type="stop" number="7"/><slur type="stop" number="8"/>')
    report = observe(xml, tmp_path, constructs=('slur',))
    assert len(report['observations']) == 2
    assert all(row['status'] == 'unverified' for row in report['observations'])


def test_full_performance_frames_are_evicted_without_losing_pair_evidence(tmp_path, monkeypatch):
    """A long audit retains scalar registrations, not every decoded RGB PNG."""
    from collections import Counter
    from copy import deepcopy
    import weakref
    import xml.etree.ElementTree as ET

    pictures(tmp_path)
    originals = {beat:(tmp_path/f'native-{beat:.5f}.png').read_bytes() for beat in (0, 2)}
    tree = ET.fromstring(score())
    part = tree.find('part')
    template = deepcopy(part[0])
    part.remove(part[0])
    for i in range(12):
        measure = deepcopy(template)
        measure.set('number', str(i+1))
        for note in measure.findall('note'):
            if note.get('id'):
                note.set('id', note.get('id')+str(i))
        part.append(measure)
        for beat, png in originals.items():
            (tmp_path/f'native-{i*4+beat:.5f}.png').write_bytes(png)
    # This final slur revisits the first pair after all later ties. Sharing
    # its real ink must still be diagnosed after that pair's PNGs are evicted.
    first, second = part[0].findall('note')[:2]
    ET.SubElement(first.find('notations'), 'slur', type='start')
    ET.SubElement(second.find('notations'), 'slur', type='stop')
    xml = ET.tostring(tree, encoding='unicode')
    baseline = observe(xml, tmp_path)
    assert baseline['coverage'] == dict(expected=13, verified=11, unverified=2, mismatch=0)

    converted, opened, peak = [], Counter(), [0]
    convert = Image.Image.convert

    def track_real_rgb(image, *args, **kwargs):
        result = convert(image, *args, **kwargs)
        name = str(getattr(image, 'filename', ''))
        if Path(name).name.startswith('native-') and result.mode == 'RGB':
            opened[Path(name).name] += 1
            converted.append(weakref.ref(result))
            peak[0] = max(peak[0], sum(ref() is not None for ref in converted))
        return result

    monkeypatch.setattr(Image.Image, 'convert', track_real_rgb)
    actual = observe(xml, tmp_path)
    assert actual == baseline
    assert len(opened) == 24, 'Every onset remains available to the audit'
    assert peak[0] <= 16, f'{peak[0]} decoded onset PNGs remained resident'
    assert opened['native-0.00000.png'] >= 2, 'Evicted early evidence must be reloadable'


@pytest.mark.parametrize('construct', ['tie', 'slur'])
def test_fractional_source_onsets_use_exact_five_decimal_frame_names(tmp_path, construct):
    import xml.etree.ElementTree as ET

    pictures(tmp_path)
    tree = ET.fromstring(score(construct=construct))
    measure = tree.find('part/measure')
    measure.find('attributes/divisions').text = '3'
    for note in measure.findall('note'):
        duration = note.find('duration')
        duration.text = str(int(duration.text)*3)
    measure.insert(1, ET.fromstring('<note><rest/><duration>1</duration><voice>1</voice>'
        '<type>eighth</type><time-modification><actual-notes>3</actual-notes>'
        '<normal-notes>2</normal-notes></time-modification></note>'))
    ending = measure.findall('note')[-1]
    ending.find('duration').text = '2'
    ending.append(ET.fromstring('<time-modification><actual-notes>3</actual-notes>'
                               '<normal-notes>2</normal-notes></time-modification>'))
    xml = ET.tostring(tree, encoding='unicode')
    for before, after in ((0, 1/3), (2, 7/3)):
        (tmp_path/f'native-{before:.5f}.png').rename(tmp_path/f'native-{after:.5f}.png')
    report = observe(xml, tmp_path, constructs=(construct,))
    assert report['complete'], report
    assert report['coverage']['expected'] == 1
    evidence = report['observations'][0]['evidence']
    assert {c['onset_frame'] for c in evidence['correspondence']} == {
        'native-0.33333.png', 'native-2.33333.png'}
    original = tmp_path/'native-0.33333.png'
    too_early = tmp_path/'native-0.333326.png'
    original.rename(too_early)  # Same F5 key, but 7.33 microbeats from 1/3.
    assert not observe(xml, tmp_path, constructs=(construct,))['complete']
    too_early.rename(original)
    # Delete every curve witness, retaining the authored times and heads.
    for path in tmp_path.glob('native-*.png'):
        image = Image.open(path).convert('RGB')
        shift = 0 if '0.33333' in path.name else -240
        ImageDraw.Draw(image).rectangle((436+shift, 157, 644+shift, 185), fill=(16, 41, 35))
        image.save(path)
    assert not observe(xml, tmp_path, constructs=(construct,))['complete']


def test_endpoint_frame_rounding_does_not_accept_more_than_five_microbeats(tmp_path):
    pictures(tmp_path)
    # This filename rounds to the same F5 key as 0, but it is farther than
    # the permitted half-unit from the actual source onset.
    (tmp_path/'native-0.00000.png').rename(tmp_path/'native-0.0000049.png')
    assert observe(score(), tmp_path, constructs=('tie',))['complete']
    (tmp_path/'native-0.0000049.png').rename(tmp_path/'native-0.0000051.png')
    assert not observe(score(), tmp_path, constructs=('tie',))['complete']
