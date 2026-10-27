"""Valid-only FFTs retain every Dice score and photographic owner."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation import extra_symbol_pixels as pixels
from piano_teacher.notation.proof import read_written_score


FIXTURES = Path(__file__).parent/'fixtures/extra_shard_pixels'


def full_padding_scores(layer, template, transforms=None, integral=None, kernel_key=None):
    """Pre-optimization full linear convolution, independent of the FFT cache."""
    h, w = template.shape
    H, W = layer.shape
    if h > H or w > W:
        return np.empty((0, 0))
    shape = (1 << (H+h-2).bit_length(), 1 << (W+w-2).bit_length())
    a = np.fft.rfft2(layer.astype(np.float32), s=shape)
    b = np.fft.rfft2(template[::-1, ::-1].astype(np.float32), s=shape)
    intersection = np.fft.irfft2(a*b, s=shape)[h-1:H, w-1:W]
    if integral is None:
        integral = np.pad(layer.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    count = integral[h:, w:]-integral[:-h, w:]-integral[h:, :-w]+integral[:-h, :-w]
    return 2*np.rint(np.maximum(intersection, 0))/(count+int(template.sum())+1e-9)


@pytest.mark.parametrize('shape,kernel', [
    ((31, 63), (17, 9)), ((32, 64), (9, 17)), ((33, 65), (17, 9)),
    ((16, 32), (16, 32)), ((1, 16), (1, 7)), ((16, 1), (7, 1)),
    ((1, 1), (1, 1)), ((8, 8), (9, 1)),
])
def test_every_translation_is_direct_pixel_dice(shape, kernel):
    rng = np.random.default_rng(732)
    layer = rng.random(shape) > .65
    template = rng.random(kernel) > .4
    h, w = kernel
    H, W = shape
    actual = pixels._scores(layer, template)
    if h > H or w > W:
        assert actual.shape == (0, 0)
        return
    expected = np.empty((H-h+1, W-w+1))
    for y in range(H-h+1):
        for x in range(W-w+1):
            patch = layer[y:y+h, x:x+w]
            expected[y, x] = (2*np.count_nonzero(patch & template)/
                              (int(patch.sum())+int(template.sum())+1e-9))
    np.testing.assert_array_equal(actual, expected)


def test_valid_search_bounds_fft_work_to_the_image_extent():
    # At a power-of-two boundary, full-convolution padding quadruples work.
    # This resource contract catches that regression without wall-clock limits.
    layer = np.zeros((32, 64), bool)
    template = np.ones((9, 17), bool)
    layer[-9:, -17:] = template
    transforms = {}
    scores = pixels._scores(layer, template, transforms=transforms)
    assert scores[-1, -1] > .999999
    assert set(transforms) == {(32, 64)}


@pytest.mark.parametrize('y,x', [(0, 0), (0, 47), (23, 0), (23, 47)])
def test_edge_glyph_corruption_is_visible_without_circular_aliasing(y, x):
    template = np.random.default_rng(733).random((9, 17)) > .4
    layer = np.zeros((32, 64), bool)
    layer[y:y+9, x:x+17] = template
    clean = pixels._scores(layer, template)
    assert clean[y, x] > .999999
    # A real missing foreground pixel must lower the score at each corner.
    yy, xx = np.argwhere(template)[0]
    layer[y+yy, x+xx] = False
    damaged = pixels._scores(layer, template)
    assert damaged[y, x] < .999
    np.testing.assert_array_equal(damaged, full_padding_scores(layer, template))


def test_authentic_kernels_and_shared_integrals_keep_all_scores():
    layer = np.random.default_rng(734).random((128, 256)) > .8
    transforms = {}
    integral = np.pad(layer.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    for name in ('head_black', 'head_half', 'rest_whole', 'augmentation_dot'):
        template = pixels._template(name, 21.875)
        actual = pixels._scores(layer, template, transforms, integral, (name, 21.875))
        np.testing.assert_array_equal(actual, full_padding_scores(layer, template))


@pytest.mark.parametrize('fixture,areas', [
    ('danny-stripe.png', [[580, 0, 708, 520]]),
    ('clair-flag.png', [[760, 350, 820, 415]]),
    ('liszt-dots.png', [[850, 320, 950, 380]]),
])
def test_retained_scan_candidates_equal_full_convolution(monkeypatch, fixture, areas):
    photo = pixels._photo(FIXTURES/fixture)
    actual = pixels._scan(photo, areas)
    assert actual
    monkeypatch.setattr(pixels, '_scores', full_padding_scores)
    assert actual == pixels._scan(photo, areas)


def onset_binding(photo, written):
    objects = pixels._scan(photo, [[0, 0, photo['shape'][1], photo['shape'][0]]])
    for track, obj in enumerate(objects):
        obj['track'] = track
    owners, errors = {}, []
    pixels._bind(written, [e for e in written.symbols if e['beat'] == 0],
                 photo, objects, owners, errors)
    return objects, owners, errors


def test_real_ownership_and_erased_head_rejection_equal_full_convolution(monkeypatch, tmp_path):
    written = read_written_score((FIXTURES/'clair-onset.musicxml').read_text())
    original = FIXTURES/'clair-onset.png'
    with Image.open(original) as raw:
        image = raw.convert('RGB')
    ImageDraw.Draw(image).rectangle((625, 432, 663, 498), fill=image.getpixel((1200, 0)))
    erased = tmp_path/'erased.png'
    image.save(erased)
    optimized = pixels._scores
    for path in (original, erased):
        photo = pixels._photo(path)
        monkeypatch.setattr(pixels, '_scores', optimized)
        actual = onset_binding(photo, written)
        monkeypatch.setattr(pixels, '_scores', full_padding_scores)
        assert actual == onset_binding(photo, written)
        expected = {e['source']['id'] for e in written.symbols
                    if e['beat'] == 0 and e['kind'] == 'note'}
        if path == original:
            assert expected <= set(actual[1].values())
        else:
            assert expected.isdisjoint(actual[1].values())
            assert expected <= set(actual[2])
