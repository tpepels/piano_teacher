"""Detached native rest dots keep their own changed-ink contour and count."""
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image
import pytest

from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels


FIXTURES = Path(__file__).parent/'fixtures/rest_dot_native'


def capture(tmp_path, name):
    shutil.copytree(FIXTURES/name, tmp_path, dirs_exist_ok=True)
    source = json.loads((tmp_path/'source.json').read_text())
    xml = (tmp_path/'score.musicxml').read_text()
    return source, xml


def observation(xml, folder, source):
    report = verify_all_rest_pixels(xml, folder, hand=source['staff'])
    return next(r for r in report['measured'] if r['source_id'] == source['source_id'])


@pytest.mark.parametrize('name', ['mozart-double', 'peace-double', 'peace-triple', 'peace-64th'])
def test_actual_detached_native_rest_dot_circles_are_individually_verified(tmp_path, name):
    source, xml = capture(tmp_path, name)
    row = observation(xml, tmp_path, source)
    assert row['status'] == 'verified', row
    dots = row['dot_evidence']
    assert dots['observed_count'] == dots['expected_count'] == source['expected_count']
    assert all(d['shape_match'] >= .8 for d in dots['dots'])
    assert all(d['visible_removed_match'] >= .8 for d in dots['dots'])
    boxes = [d['box'] for d in dots['dots']]
    assert all(left[2] < right[0] for left, right in zip(boxes, boxes[1:]))


def test_rest_flag_circle_cannot_replace_an_erased_64th_rest_augmentation_dot(tmp_path):
    source, xml = capture(tmp_path, 'peace-64th')
    diag = json.loads((tmp_path/'native-overlay-report.json').read_text())
    frame = diag['rest_difference_frames'][0]
    with Image.open(tmp_path/diag['rest_difference_controls'][0]['file']) as raw:
        suppressed = np.asarray(raw.convert('RGB'))
    for name in (f'native-{source["beat"]:.5f}.png',frame['repeat_file'],frame['restored_file']):
        with Image.open(tmp_path/name) as raw:
            image = np.asarray(raw.convert('RGB')).copy()
        # Leave every flag/body pixel intact, including a disconnected bulb
        # whose independent augmentation-dot Dice is .836 (> .8).
        image[171:176,654:660] = suppressed[171:176,654:660]
        Image.fromarray(image).save(tmp_path/name)
    row = observation(xml, tmp_path, source)
    assert row['status'] != 'verified', row
    assert row.get('dot_evidence', {}).get('status') != 'verified', row


@pytest.mark.parametrize('name,box', [
    ('peace-64th', (654,171,660,176)),
    ('mozart-double', (662,176,674,188)),
])
def test_control_only_dark_dot_cannot_replace_removed_visible_dot(tmp_path, name, box):
    source, xml = capture(tmp_path, name)
    diag = json.loads((tmp_path/'native-overlay-report.json').read_text())
    frame = diag['rest_difference_frames'][0]
    control = tmp_path/diag['rest_difference_controls'][0]['file']
    names = [f'native-{source["beat"]:.5f}.png', frame['repeat_file'], frame['restored_file']]
    with Image.open(tmp_path/names[0]) as raw:
        original = np.asarray(raw.convert('RGB'))
    with Image.open(control) as raw:
        suppressed = np.asarray(raw.convert('RGB')).copy()
    delta = np.max(abs(original.astype(int)-suppressed.astype(int)), axis=2) >= 10
    dot = np.zeros(delta.shape, dtype=bool)
    x0,y0,x1,y1 = box
    dot[y0:y1,x0:x1] = delta[y0:y1,x0:x1]
    assert dot.any()
    # Remove the real dot while keeping repeat/restore perfectly invariant.
    # A corrupt control then ADDS dark ink with the same silhouette. The
    # unchanged rest body still supplies plenty of genuine removed pale ink.
    for filename in names:
        with Image.open(tmp_path/filename) as raw:
            image = np.asarray(raw.convert('RGB')).copy()
        image[dot] = suppressed[dot]
        Image.fromarray(image).save(tmp_path/filename)
    suppressed[dot] = 0
    Image.fromarray(suppressed).save(control)
    row = observation(xml, tmp_path, source)
    assert row['visible_original_ink_removed'] >= 12, row
    assert row['status'] != 'verified', row
    assert row['dot_evidence']['status'] == 'unverified', row
    assert row['dot_evidence']['visible_removed_match'] == 0, row
    assert 'removed visible pale contour' in row['reason'], row
    assert row['placement_evidence']['status'] != 'verified', row


def test_control_only_dark_rest_body_cannot_borrow_genuine_removed_dots(tmp_path):
    source, xml = capture(tmp_path, 'mozart-double')
    diag = json.loads((tmp_path/'native-overlay-report.json').read_text())
    frame = diag['rest_difference_frames'][0]
    control = tmp_path/diag['rest_difference_controls'][0]['file']
    names = [f'native-{source["beat"]:.5f}.png', frame['repeat_file'], frame['restored_file']]
    with Image.open(tmp_path/names[0]) as raw:
        original = np.asarray(raw.convert('RGB'))
    with Image.open(control) as raw:
        suppressed = np.asarray(raw.convert('RGB')).copy()
    delta = np.max(abs(original.astype(int)-suppressed.astype(int)), axis=2) >= 10
    body = np.zeros(delta.shape, dtype=bool)
    body[155:221,632:658] = delta[155:221,632:658]
    assert body.sum() == 528
    for filename in names:
        with Image.open(tmp_path/filename) as raw:
            image = np.asarray(raw.convert('RGB')).copy()
        image[body] = suppressed[body]
        Image.fromarray(image).save(tmp_path/filename)
    suppressed[body] = 0
    Image.fromarray(suppressed).save(control)
    row = observation(xml, tmp_path, source)
    assert row['status'] != 'verified', row
    assert row['placement_evidence']['status'] != 'verified', row


@pytest.mark.parametrize('expected,drawn', [('16th','32nd'),('32nd','64th'),('64th','128th')])
def test_extra_short_rest_flag_cannot_be_relabelled_as_a_written_dot(tmp_path, expected, drawn):
    from test_phase3_rest_differences import _captures
    xml = _captures(tmp_path, kind=drawn)
    xml = xml.replace(f'<type>{drawn}</type>', f'<type>{expected}</type><dot/>')
    row = verify_all_rest_pixels(xml, tmp_path)['measured'][0]
    assert row['status'] != 'verified', row


def test_body_and_dot_partition_accounts_for_every_original_changed_pixel_once(tmp_path):
    from piano_teacher.notation.phase3_pixels import _rest_delta_parts, _rest_body_dot_partition
    from piano_teacher.notation.pixel_proof import detect_staff_lines
    from piano_teacher.notation.reference_font import reference_glyphs

    source, _ = capture(tmp_path, 'peace-64th')
    diag = json.loads((tmp_path/'native-overlay-report.json').read_text())
    with Image.open(tmp_path/f'native-{source["beat"]:.5f}.png') as raw:
        original = raw.convert('RGB')
    with Image.open(tmp_path/diag['rest_difference_controls'][0]['file']) as raw:
        suppressed = np.asarray(raw.convert('RGB'), dtype=int)
    delta = np.max(abs(np.asarray(original, dtype=int)-suppressed), axis=2) >= 10
    gap = detect_staff_lines(original)[source['staff']].gap
    parts = _rest_delta_parts(delta, gap)
    body, dots = _rest_body_dot_partition(parts[0], parts[1:],
        reference_glyphs()['rest_64th'], gap, 1)
    owned = set()
    for part in [body, *dots]:
        ys, xs = np.nonzero(part['mask'])
        support = set(zip(ys+part['box'][1], xs+part['box'][0]))
        assert owned.isdisjoint(support)
        owned.update(support)
    assert owned == set(zip(*np.nonzero(delta)))


@pytest.mark.parametrize('mutation', ['erase', 'wrong-shape', 'joined', 'extra', 'unchanged-neighbor'])
def test_actual_rest_dot_erasure_wrong_shape_or_joined_ink_cannot_receive_credit(tmp_path, mutation):
    source, xml = capture(tmp_path, 'mozart-double')
    # Measured directly from the retained source/control PNG difference:
    # first dot [662,176,673,187], second [676,176,686,187]. The clear
    # columns 674/675 must stay clear to establish two physical contours.
    diag = json.loads((tmp_path/'native-overlay-report.json').read_text())
    frame = diag['rest_difference_frames'][0]
    control = diag['rest_difference_controls'][0]['file']
    with Image.open(tmp_path/control) as raw:
        suppressed = np.asarray(raw.convert('RGB')).copy()
    names = [f'native-{source["beat"]:.5f}.png', frame['repeat_file'], frame['restored_file']]
    if mutation == 'unchanged-neighbor':
        with Image.open(tmp_path/names[0]) as raw:
            original = np.asarray(raw.convert('RGB'))
        suppressed[176:188,662:674] = original[176:188,662:674]
        Image.fromarray(suppressed).save(tmp_path/control)
    else:
        for name in names:
            with Image.open(tmp_path/name) as raw:
                image = np.asarray(raw.convert('RGB')).copy()
            if mutation in ('erase', 'wrong-shape'):
                image[176:188,662:674] = suppressed[176:188,662:674]
            if mutation == 'wrong-shape':
                image[174:190,667:669] = (235,242,234)
            if mutation == 'joined':
                image[181,673:677] = (235,242,234)
            if mutation == 'extra':
                from piano_teacher.notation.phase3_pixels import _rest_dot_template_mask
                mask = _rest_dot_template_mask(21.875)
                ys, xs = np.nonzero(mask)
                mask = mask[ys.min():ys.max()+1,xs.min():xs.max()+1]
                region = image[176:176+mask.shape[0],690:690+mask.shape[1]]
                region[mask] = (235,242,234)
            Image.fromarray(image).save(tmp_path/name)
    row = observation(xml, tmp_path, source)
    assert row['status'] != 'verified', row
    assert row.get('dot_evidence', {}).get('status') != 'verified', row


def test_excessive_source_rest_dots_stay_explicitly_unsupported(tmp_path):
    from xml.etree import ElementTree as ET
    source, xml = capture(tmp_path, 'peace-triple')
    tree = ET.fromstring(xml)
    # The actual triple-dotted rest is the only triple-dot source element.
    note, = [n for n in tree.findall('.//note') if len(n.findall('dot')) == 3]
    ET.SubElement(note, 'dot')
    row = observation(ET.tostring(tree, encoding='unicode'), tmp_path, source)
    assert row['status'] == row['dot_evidence']['status'] == 'unsupported'
