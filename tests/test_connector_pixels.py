"""Independent connector proofs on retained actual Godot framebuffers."""
from pathlib import Path
import json
import shutil

from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.connector_pixels import verify_beam_pixels, verify_tuplet_pixels

FIXTURES = Path(__file__).parent / 'fixtures/connector_pixels'


def check(case, folder=None, xml=None):
    folder = folder or FIXTURES / case
    xml = xml or (FIXTURES / case / 'score.musicxml').read_text()
    return (verify_beam_pixels if case == 'beams' else verify_tuplet_pixels)(
        xml, folder, hand='right')


def copied(case, tmp_path):
    dest = tmp_path / case
    shutil.copytree(FIXTURES / case, dest)
    return dest


def erase(folder, name, bbox):
    path = folder / name
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    x0, y0, x1, y1 = map(round, bbox)
    ImageDraw.Draw(image).rectangle((x0, y0, x1-1, y1-1), fill=image.getpixel((1535, 0)))
    image.save(path)


@pytest.mark.parametrize(('case', 'expected'), [('beams', 2), ('tuplets', 1)])
def test_real_source_bound_connectors(case, expected):
    report = check(case)
    assert report['coverage']['expected'] == expected
    assert report['coverage']['verified'] == expected, report
    assert report['complete']
    assert 'passed' not in report
    for row in report['measured']:
        assert row['source_ids'] and row['event_ids']
        assert row['evidence']['staff_lines']
        assert row['evidence']['anchors']
    json.dumps(report)


@pytest.mark.parametrize('case', ['beams', 'tuplets'])
def test_erased_connector_cannot_be_certified_by_native_metadata(case, tmp_path):
    folder = copied(case, tmp_path)
    before = check(case, folder)['measured'][0]
    assert before['status'] == 'verified'
    # Erase the same world feature in every retained frame. Other groups
    # remain intact, so global image registration cannot authorize this ink.
    for witness in before['evidence']['witnesses']:
        erase(folder, witness['frame'], witness['bbox'])
    (folder/'fixture.json').write_text('{"native_fragments":"verified"}')
    (folder/'native-overlay-report.json').write_text('not valid diagnostic JSON')
    after = check(case, folder)
    row = next(r for r in after['measured'] if r['source_ids'] == before['source_ids'])
    assert row['status'] != 'verified', row
    assert not after['complete']


def test_source_identity_must_agree_with_original_reference_svg():
    xml = (FIXTURES/'tuplets/score.musicxml').read_text()
    xml = xml.replace('<actual-notes>5</actual-notes>', '<actual-notes>7</actual-notes>')
    assert check('tuplets', xml=xml)['coverage']['verified'] == 0
    xml = (FIXTURES/'beams/score.musicxml').read_text()
    xml = xml.replace('<type>eighth</type>', '<type>16th</type>')
    assert check('beams', xml=xml)['coverage']['verified'] == 0


def test_missing_onset_and_reference_frames_stay_in_denominator(tmp_path):
    folder = copied('beams', tmp_path)
    for path in folder.glob('native-*.png'):
        path.unlink()
    report = check('beams', folder)
    assert report['coverage']['expected'] == 2
    assert report['coverage']['unverified'] == 2
    assert not report['complete']
    for path in folder.glob('verovio-*.svg'):
        path.unlink()
    report = check('beams', folder)
    assert report['coverage']['expected'] >= 2
    assert not report['complete']


@pytest.mark.parametrize('case', ['beams', 'tuplets'])
def test_detached_actual_endpoint_cannot_pass_a_good_global_contour(case, tmp_path):
    folder = copied(case, tmp_path)
    before = check(case, folder)['measured'][0]
    witness = before['evidence']['witnesses'][0]
    if case == 'beams':
        stem = witness['stems'][0]
        x = stem['x']
        y = stem['top'] + 20
        box = [x-3, y, x+4, y+8]
    else:
        x0, y0, x1, y1 = witness['bracket_bbox']
        box = [x1-6, y0+4, x1+2, y1+2]
    erase(folder, witness['frame'], box)
    assert check(case, folder)['measured'][0]['status'] != 'verified'


def test_erasure_between_old_three_probe_positions_is_detected(tmp_path):
    folder = copied('beams', tmp_path)
    row = check('beams', folder)['measured'][0]
    witness = row['evidence']['witnesses'][0]
    sample = witness['samples'][5]
    x = sample['x']
    y0, y1 = witness['bbox'][1], witness['bbox'][3]
    erase(folder, witness['frame'], [x, y0, x+4, y1])
    assert check('beams', folder)['measured'][0]['status'] != 'verified'


def test_singleton_note_and_anonymous_rest_are_actual_source_bound():
    for case in ('singleton-note', 'singleton-rest'):
        folder = FIXTURES/case
        report = verify_tuplet_pixels((folder/'score.musicxml').read_text(), folder, hand='right')
        visible = [r for r in report['measured'] if r['graphical']]
        assert len(visible) == 1
        row = visible[0]
        assert len(row['source_ids']) == len(row['evidence']['anchors']) == 1
        assert row['evidence']['expected_numeral'] == '20:19'
        assert row['evidence']['numeral_match'] >= .79
        # These genuine Verovio singleton brackets touch the number ink.
        # Opaque shared pixels cannot prove both silhouettes independently.
        assert row['status'] == 'ambiguous'
        if case == 'singleton-rest':
            assert row['evidence']['overlapping_pixels'] > 2
        else:
            assert any(d['match'] < .79 for d in row['evidence']['digits'])
        hidden = [r for r in report['measured'] if not r['graphical']]
        assert hidden and all(r['status'] != 'verified' for r in hidden)


@pytest.mark.parametrize('case', ['beam16', 'beam-chords', 'beam-down'])
def test_actual_multiple_beam_levels_chords_and_downward_stems(case):
    folder = FIXTURES/case
    report = verify_beam_pixels((folder/'score.musicxml').read_text(), folder, hand='right')
    assert report['coverage']['expected'] == 2
    assert report['coverage']['verified'] == 2, report


def test_wrong_actual_numeral_does_not_pass_a_source_ratio_label(tmp_path):
    import cairosvg
    from io import BytesIO
    from xml.etree import ElementTree as ET
    import verovio

    folder = copied('tuplets', tmp_path)
    row = check('tuplets', folder)['measured'][0]
    witness = row['evidence']['witnesses'][0]
    erase(folder, witness['frame'], witness['number_bbox'])
    resources = Path(verovio.__file__).parent/'data'
    font = ET.parse(resources/'Leipzig.xml').getroot()
    glyph = font.find("g[@c='E883']")  # Authentic 3 in place of written 5.
    x, y, w, h = [float(glyph.get(k)) for k in ('x', 'y', 'w', 'h')]
    root = ET.Element('svg', xmlns='http://www.w3.org/2000/svg',
                      viewBox=f'{x} {-y-h} {w} {h}', fill='#edf6ee')
    root.append(ET.parse(resources/'Leipzig/E883.xml').getroot())
    png = cairosvg.svg2png(bytestring=ET.tostring(root),
        output_width=round(w*witness['staff_gap']/250),
        output_height=round(h*witness['staff_gap']/250))
    path = folder/witness['frame']
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    with Image.open(BytesIO(png)) as glyph:
        image.paste(glyph, tuple(witness['number_bbox'][:2]), glyph)
    image.save(path)
    assert check('tuplets', folder)['measured'][0]['status'] != 'verified'


def test_each_digit_has_independent_identity_evidence():
    row = check('tuplets')['measured'][0]
    assert [d['code'] for d in row['evidence']['digits']] == ['E885']
    assert all(d['match'] >= .79 and d['margin'] >= .03 for d in row['evidence']['digits'])


def test_secondary_beam_source_hook_cannot_reuse_a_full_reference_beam():
    folder = FIXTURES/'beam16'
    xml = (folder/'score.musicxml').read_text().replace(
        '<beam number="2">begin</beam>', '<beam number="2">forward hook</beam>')
    report = verify_beam_pixels(xml, folder, hand='right')
    assert report['coverage']['verified'] == 0


def test_anonymous_polyphonic_rest_binding_remains_unverified():
    from xml.etree import ElementTree as ET
    folder = FIXTURES/'singleton-rest'
    root = ET.fromstring((folder/'score.musicxml').read_text())
    # The source voice inventory changed; do not bind an opaque SVG rest
    # by proximity or borrow a native generated ID.
    root.find('part/measure/note/voice').text = '2'
    report = verify_tuplet_pixels(ET.tostring(root, encoding='unicode'), folder, hand='right')
    visible = [r for r in report['measured'] if r['graphical']]
    assert visible and all(r['status'] != 'verified' for r in visible)


def test_reference_id_renaming_and_invalid_hand_fail_closed():
    folder = FIXTURES/'beams'
    xml = (folder/'score.musicxml').read_text().replace('pt5bf5e5491713546d75540ba27f62e53as0', 'unbound')
    report = verify_beam_pixels(xml, folder, hand='right')
    assert not report['complete']
    with pytest.raises(ValueError):
        verify_beam_pixels(xml, folder, hand='feet')


def test_actual_missing_secondary_beam_cannot_pass_as_written_sixteenths(tmp_path):
    import numpy as np
    from piano_teacher.notation.symbol_pixel_proof import bright

    folder = copied('beam16', tmp_path)
    xml = (folder/'score.musicxml').read_text()
    before = verify_beam_pixels(xml, folder, hand='right')['measured'][0]
    witness = before['evidence']['witnesses'][0]
    path = folder/witness['frame']
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    pixels = bright(image)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = witness['bbox']
    removed = 0
    for x in range(left, right):
        if any(abs(x-s['x']) < 2 for s in witness['stems']):
            continue
        ys = np.flatnonzero(pixels[top:bottom, x])
        runs = [a for a in np.split(ys, np.flatnonzero(np.diff(ys)>1)+1) if len(a)]
        if len(runs) == 2:
            band = runs[-1]  # Keep the primary beam and every attached stem.
            draw.line((x, top+int(band[0]), x, top+int(band[-1])), fill=image.getpixel((1535, 0)))
            removed += len(band)
    assert removed > 100
    image.save(path)
    after = verify_beam_pixels(xml, folder, hand='right')
    assert after['measured'][0]['status'] == 'mismatch'


def test_explicit_source_group_identity_survives_reference_measure_count_changes():
    """The reference renderer may paginate or omit empty measure containers.

    Explicit XML event IDs must still resolve; anonymous events are not
    guessed by proximity if the structural count no longer agrees.
    """
    from piano_teacher.notation.connector_pixels import _pages
    from piano_teacher.notation.proof import read_written_score
    from types import SimpleNamespace
    folder = FIXTURES / 'tuplets'
    xml = (folder / 'score.musicxml').read_text()
    svg = (folder / 'verovio-0.svg').read_text()
    written = read_written_score(xml)
    original = _pages(written, [svg])[1]
    assert any(e['id'] for e in original.values())
    malformed_index = SimpleNamespace(symbols=written.symbols + (dict(
        written.symbols[0], index=12345, id=None),))
    resolved = _pages(malformed_index, [svg])[1]
    expected = {e['id'] for e in written.symbols if e['id']}
    assert expected <= {e['id'] for e in resolved.values() if e['id']}


def test_grouped_source_ids_do_not_depend_on_anonymous_rest_ordinal():
    from piano_teacher.notation.connector_pixels import _inventory
    from piano_teacher.notation.proof import read_written_score
    folder = FIXTURES / 'tuplets'
    written = read_written_score((folder / 'score.musicxml').read_text())
    svg = (folder / 'verovio-0.svg').read_text()
    groups = _inventory(written, [svg], 'tuplet', 'right')
    graphical = [g for g in groups if g.get('graphical', True)]
    assert graphical and all(g['events'] and not g.get('error') for g in graphical)
    assert len({e['source']['id'] for g in graphical for e in g['events']}) >= 5



def test_no_usable_reference_frame_cannot_be_certified(monkeypatch):
    from piano_teacher.notation import connector_pixels as matcher
    from types import SimpleNamespace
    from pathlib import Path
    source = (FIXTURES / "beams" / "score.musicxml").read_text()
    written = matcher.read_written_score(source)
    svg = (FIXTURES / "beams" / "verovio-0.svg").read_text()
    groups = matcher._inventory(written, [svg], "beam", "right")
    assert groups and groups[0]["events"]
    # Reuse the real source/reference, but simulate no usable screenshot
    # witnesses; source metadata must never be enough to prove a connector.
    class Frames:
        def __init__(self, *_): pass
        def nearby_clocks(self, *_): return []
        def anchors(self, events, target):
            # This is the public image-witness interface used by _beam.
            # An unavailable capture must fail closed, not raise AttributeError
            # because the test double forgot a method.
            raise OSError("No independently usable framebuffer")
        def frame(self, clock): raise OSError("No independently usable framebuffer")
    monkeypatch.setattr(matcher, "_Frames", Frames)
    report = matcher._verify(source, Path("/unused"), "right", [svg], "beam")
    assert report["coverage"]["expected"] > 0
    assert report["coverage"]["verified"] == 0
    assert not report["complete"]
    assert all(row["status"] == "unverified" for row in report["measured"])
    assert all(
        row["evidence"]["unavailable_witnesses"]
        and "No independently usable framebuffer" in row["evidence"]["unavailable_witnesses"][0]["reason"]
        for row in report["measured"]
    )
