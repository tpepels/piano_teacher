"""Retained shard-0 framebuffers: context, components and source-onset proof."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from piano_teacher.notation import extra_symbol_pixels as pixels
from piano_teacher.notation.proof import read_written_score

FIXTURES = Path(__file__).parent/'fixtures/extra_shard_pixels'


def test_real_heads_straddling_a_scan_stripe_keep_the_complete_best_contour():
    photo = pixels._photo(FIXTURES/'danny-stripe.png')
    heads = [r for r in pixels._scan(photo, [[580, 0, 708, 520]]) if r['family'] == 'head']
    for y in (164, 303):
        assert any(r['bbox'] == [574, y, 604, y+25] and r['score'] > .95 for r in heads), heads
    assert not any(r['bbox'][0] == 580 and r['score'] < .85 for r in heads), heads


def test_two_real_augmentation_dots_are_not_one_connected_rectangular_rest():
    photo = pixels._photo(FIXTURES/'liszt-dots.png')
    body = dict(name='rest_whole', gap=21.875, bbox=[871, 347, 899, 360])
    dots = dict(name='rest_whole', gap=21.875, bbox=[900, 347, 928, 360])
    assert pixels._isolated_rectangle(photo, body)
    assert not pixels._isolated_rectangle(photo, dots)


def bind_onset(photo, written):
    objects = pixels._scan(photo, [[0, 0, photo['shape'][1], photo['shape'][0]]])
    for track, obj in enumerate(objects):
        obj['track'] = track
    owners, errors = {}, []
    events = [e for e in written.symbols if e['beat'] == 0]
    pixels._bind(written, events, photo, objects, owners, errors)
    return owners, errors, events


def test_real_source_clock_uses_strict_pale_contours_with_measured_ledger_context():
    written = read_written_score((FIXTURES/'clair-onset.musicxml').read_text())
    owners, errors, events = bind_onset(pixels._photo(FIXTURES/'clair-onset.png'), written)
    expected = {e['source']['id'] for e in events if e['kind'] == 'note'}
    assert len(expected) == 2
    assert expected <= set(owners.values()), (owners, errors)


def test_erasing_real_onset_heads_cannot_be_repaired_by_source_metadata(tmp_path):
    original = FIXTURES/'clair-onset.png'
    with Image.open(original) as raw:
        image = raw.convert('RGB')
    # Both actual low-register half heads, while leaving other source ink.
    pen = ImageDraw.Draw(image)
    pen.rectangle((625, 432, 663, 498), fill=image.getpixel((1200, 0)))
    path = tmp_path/'erased.png'
    image.save(path)
    written = read_written_score((FIXTURES/'clair-onset.musicxml').read_text())
    owners, errors, events = bind_onset(pixels._photo(path), written)
    expected = {e['source']['id'] for e in events if e['kind'] == 'note'}
    assert not expected.intersection(owners.values())
    assert expected <= set(errors)


def test_foreign_head_is_still_detected_beside_a_context_padded_stripe(tmp_path):
    import cairosvg
    from io import BytesIO
    with Image.open(FIXTURES/'danny-stripe.png') as raw:
        image = raw.convert('RGB')
    glyph = pixels._feature_glyphs()['head_black']
    bounds = glyph['bounds']
    png = cairosvg.svg2png(bytestring=glyph['svg'].encode(),
        output_width=round(bounds[2]*21.875/250),
        output_height=round(bounds[3]*21.875/250))
    with Image.open(BytesIO(png)) as head:
        image.paste(head, (580, 60), head)
    path = tmp_path/'extra.png'
    image.save(path)
    rows = pixels._scan(pixels._photo(path), [[580, 0, 708, 520]])
    assert any(r['name'] == 'head_black' and r['bbox'][:2] == [580, 60]
               and r['score'] >= .95 for r in rows), rows


def test_wrong_written_head_family_cannot_authorize_the_real_hollow_heads():
    xml = (FIXTURES/'clair-onset.musicxml').read_text().replace('<type>half</type>', '<type>quarter</type>')
    written = read_written_score(xml)
    owners, errors, events = bind_onset(pixels._photo(FIXTURES/'clair-onset.png'), written)
    expected = {e['source']['id'] for e in events if e['kind'] == 'note'}
    assert not expected.intersection(owners.values())
    assert expected <= set(errors)


def hanon_frames():
    return [Image.open(FIXTURES/f'hanon-motion-{i}.png').convert('RGB') for i in range(3)]


def test_actual_hanon_step_outside_the_column_shortlist_is_verified_in_two_dimensions():
    from piano_teacher.notation.phase3_pixels import verify_translation_sequence
    report = verify_translation_sequence(*hanon_frames())
    assert report['passed'], report
    assert report['pixel_steps'] == [15, 15]
    assert min(report['contour_agreement']) > .93


def test_actual_hanon_freeze_reverse_and_jump_remain_rejected():
    from piano_teacher.notation.phase3_pixels import verify_translation_sequence
    frames = hanon_frames()
    jumped = Image.new('RGB', frames[-1].size, frames[-1].getpixel((1200, 0)))
    jumped.paste(frames[-1], (-30, 0))
    for sequence in ((frames[0],)*3, tuple(reversed(frames)), (*frames[:2], jumped)):
        assert not verify_translation_sequence(*sequence)['passed']


def test_structural_motion_uses_full_hanon_contours_outside_the_column_shortlist():
    from piano_teacher.notation.feature_pixels import _frame_shift
    frames = hanon_frames()
    for first, second in zip(frames, frames[1:]):
        measured = _frame_shift(first, second)
        assert measured is not None
        assert measured['shift'] == 15
        assert measured['contour_agreement'] > .90
        backward = _frame_shift(second, first)
        assert backward is not None and backward['shift'] == -15


def test_structural_motion_rejects_equal_competing_full_contours_and_missing_ink():
    from piano_teacher.notation.feature_pixels import _frame_shift
    background = (16, 41, 35)
    periodic = Image.new('RGB', (800, 200), background)
    pen = ImageDraw.Draw(periodic)
    for x in (100, 300, 500, 700):
        pen.rectangle((x, 40, x+10, 90), fill=(245, 245, 245))
    assert _frame_shift(periodic, periodic) is None
    blank = Image.new('RGB', periodic.size, background)
    assert _frame_shift(periodic, blank) is None
    assert _frame_shift(periodic, blank.crop((0, 0, 600, 200))) is None


def test_all_horizontal_dice_scores_equal_direct_pixel_intersections():
    from piano_teacher.notation import phase3_pixels
    assert callable(getattr(phase3_pixels, '_horizontal_dice', None))
    rng = np.random.default_rng(731)
    a, b = (rng.random((31, 97)) > .8 for _ in range(2))
    for dice, shift in phase3_pixels._horizontal_dice(a, b, 30):
        aa, bb = (a[:, shift:], b[:, :-shift]) if shift > 0 else (
            (a[:, :shift], b[:, -shift:]) if shift < 0 else (a, b))
        expected = 2*np.count_nonzero(aa & bb)/(np.count_nonzero(aa)+np.count_nonzero(bb))
        assert abs(dice-expected) < 1e-12


def test_real_flag_loop_is_not_independently_identified_as_an_extra_head():
    photo = pixels._photo(FIXTURES/'clair-flag.png')
    rows = pixels._scan(photo, [[760, 350, 820, 415]])
    alias = next(r for r in rows if r['name'] == 'head_black'
                 and r['bbox'] == [783, 372, 799, 386])
    # The alias really passes the unmodified family score. Its boundary,
    # however, joins the flag through the middle, unlike a head/stem junction.
    assert alias['score'] >= .79
    evidence = pixels._head_boundary_evidence(photo, alias)
    assert evidence['status'] == 'ambiguous', evidence
    assert evidence['unsupported_boundary_pixels'] > 0


def test_authentic_foreign_head_and_thin_stem_remain_independent_candidates(tmp_path):
    with Image.open(FIXTURES/'clair-flag.png') as raw:
        image = raw.convert('RGB')
    gap = pixels._photo(FIXTURES/'clair-flag.png')['staves']['left'].gap
    template = pixels._template('head_black', gap)
    h, w = template.shape
    # Genuine external contour, deliberately unrelated to any source anchor.
    ink = Image.fromarray(np.uint8(template)*255)
    image.paste((245, 245, 245), (900, 80, 900+w, 80+h), ink)
    for stem in (False, True):
        if stem:
            ImageDraw.Draw(image).line((900+w-1, 80+h//2, 900+w-1, 45),
                                      fill=(245, 245, 245), width=1)
        path = tmp_path/f'foreign-{stem}.png'
        image.save(path)
        photo = pixels._photo(path)
        rows = pixels._scan(photo, [[880, 40, 940, 110]])
        head = next(r for r in rows if r['name'] == 'head_black'
                    and r['bbox'][:2] == [900, 80])
        assert head['score'] > .95
        assert pixels._head_boundary_evidence(photo, head)['status'] == 'verified'
