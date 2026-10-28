"""Exact local photographic reuse must remain bounded and observe PNG changes."""
from pathlib import Path
import shutil
import os

from PIL import Image, ImageDraw, UnidentifiedImageError

import numpy as np
import pytest

from piano_teacher.notation import extra_symbol_pixels as pixels

FIXTURES = Path(__file__).parent/'fixtures/extra_shard_pixels'


def test_actual_photo_reuse_avoids_a_second_decode_and_returns_fresh_masks(monkeypatch, tmp_path):
    assert callable(getattr(pixels, '_PhotoCache', None)), 'Bounded intra-call photo reuse is missing'
    path = tmp_path/'native-0.00000.png'
    shutil.copyfile(FIXTURES/'clair-onset.png', path)
    original = pixels._photo
    calls = []
    def counted(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(pixels, '_photo', counted)
    cache = pixels._PhotoCache()
    photo = cache.capture(path)
    expected = original(path)
    photo['ink'][:] = False
    photo['layers'][0][:] = False
    photo['staves'].clear()
    photo['occlusion_columns'][:] = -1
    restored = cache.restore(path)
    assert set(restored) == set(expected)
    assert len(calls) == 1
    for key in ('ink', 'head_pixels', 'occlusion', 'occlusion_columns'):
        np.testing.assert_array_equal(restored[key], expected[key])
        assert restored[key].dtype == expected[key].dtype
        assert not np.shares_memory(restored[key], photo[key])
    for actual, wanted in zip(restored['layers'], expected['layers']):
        np.testing.assert_array_equal(actual, wanted)
        assert actual.dtype == wanted.dtype
    for key in ('staves', 'camera', 'occluded', 'shape'):
        assert restored[key] == expected[key]
    assert cache.bytes_used == 0
    assert not cache.entries


def copy_onset(tmp_path, name='native-0.00000.png'):
    path = tmp_path/name
    shutil.copyfile(FIXTURES/'clair-onset.png', path)
    return path


def erase_heads(path):
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    ImageDraw.Draw(image).rectangle((625, 432, 663, 498), fill=image.getpixel((1200, 0)))
    image.save(path)


def test_entry_and_byte_limits_evict_without_changing_photographs(monkeypatch, tmp_path):
    path = copy_onset(tmp_path)
    probe = pixels._PhotoCache()
    probe.capture(path)
    one_entry = probe.bytes_used
    assert one_entry > 0
    for byte_limit, entry_limit, expected_entries in ((one_entry*10, 2, 2), (one_entry*2-1, 10, 1)):
        monkeypatch.setattr(pixels, 'PHOTO_CACHE_BYTES', byte_limit)
        monkeypatch.setattr(pixels, 'PHOTO_CACHE_ENTRIES', entry_limit)
        cache = pixels._PhotoCache()
        paths = [copy_onset(tmp_path, f'native-{i}.00000.png') for i in range(3)]
        for frame in paths:
            cache.capture(frame)
            assert cache.bytes_used <= byte_limit
            assert len(cache.entries) <= entry_limit
        assert len(cache.entries) == expected_entries
        # The oldest entry was evicted, but its real photograph still decodes.
        np.testing.assert_array_equal(cache.restore(paths[0])['ink'], pixels._photo(paths[0])['ink'])
        for entry in cache.entries.values():
            assert all(not isinstance(value, np.ndarray) for value in entry)


def test_oversized_png_and_oversized_entry_use_ordinary_photography(monkeypatch, tmp_path):
    path = copy_onset(tmp_path)
    expected = pixels._photo(path)
    for limit, value in (('PHOTO_CACHE_PNG_BYTES', 16), ('PHOTO_CACHE_BYTES', 16), ('PHOTO_CACHE_ENTRIES', 0)):
        with monkeypatch.context() as patch:
            patch.setattr(pixels, limit, value)
            cache = pixels._PhotoCache()
            np.testing.assert_array_equal(cache.capture(path)['ink'], expected['ink'])
            assert not cache.entries
            np.testing.assert_array_equal(cache.restore(path)['ink'], expected['ink'])


def test_changed_bytes_with_identical_size_and_mtime_invalidate_cached_masks(tmp_path):
    path = copy_onset(tmp_path)
    path.write_bytes(path.read_bytes()+bytes(100_000))
    stat = path.stat()
    cache = pixels._PhotoCache()
    before = cache.capture(path)
    erase_heads(path)
    changed = path.read_bytes()
    assert len(changed) < stat.st_size
    path.write_bytes(changed+bytes(stat.st_size-len(changed)))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert path.stat().st_size == stat.st_size
    assert path.stat().st_mtime_ns == stat.st_mtime_ns
    after = cache.restore(path)
    expected = pixels._photo(path)
    np.testing.assert_array_equal(after['ink'], expected['ink'])
    assert not np.array_equal(before['ink'], after['ink'])


def test_failed_or_changed_corrupt_png_cannot_return_a_cached_pass(tmp_path):
    path = copy_onset(tmp_path)
    cache = pixels._PhotoCache()
    cache.capture(path)
    path.write_bytes(b'corrupt PNG')
    with pytest.raises(UnidentifiedImageError):
        cache.restore(path)
    with pytest.raises(UnidentifiedImageError):
        cache.capture(path)
    assert not cache.entries
    copy_onset(tmp_path)
    assert cache.restore(path)['ink'].any()


def test_cache_is_bound_to_the_exact_frame_path_and_not_just_content(tmp_path):
    original = copy_onset(tmp_path)
    wrong_clock = copy_onset(tmp_path, 'native-9.00000.png')
    cache = pixels._PhotoCache()
    cache.capture(original)
    wrong_clock.write_bytes(b'wrong-clock corrupt PNG')
    with pytest.raises(UnidentifiedImageError):
        cache.restore(wrong_clock)
    assert cache.restore(original)['ink'].any()


def report(folder):
    return pixels.verify_extra_symbol_pixels((FIXTURES/'clair-onset.musicxml').read_text(), folder)


@pytest.mark.parametrize('mutation', ['clean', 'erased', 'wrong-clock', 'corrupt'])
def test_complete_actual_report_equals_disabled_cache(monkeypatch, tmp_path, mutation):
    path = copy_onset(tmp_path)
    if mutation == 'erased':
        erase_heads(path)
    elif mutation == 'wrong-clock':
        path.rename(tmp_path/'native-9.00000.png')
    elif mutation == 'corrupt':
        path.write_bytes(b'corrupt PNG')
    cached = report(tmp_path)
    monkeypatch.setattr(pixels, 'PHOTO_CACHE_BYTES', 0)
    control = report(tmp_path)
    assert cached == control
    if mutation == 'clean':
        assert cached['coverage']['bound_heads'] == 2
    elif mutation == 'erased':
        assert cached['coverage']['bound_heads'] == 0
        assert cached['coverage']['binding_errors']
    elif mutation == 'wrong-clock':
        assert cached['coverage']['bound_heads'] == 0
        assert 0. in cached['coverage']['missing_source_clocks']
    else:
        assert cached['coverage']['measured_frames'] == 0


def test_verifier_uses_local_reuse_and_observes_between_pass_png_changes(monkeypatch, tmp_path):
    path = copy_onset(tmp_path)
    original_bytes = path.read_bytes()
    original_photo = pixels._photo
    decodes = []
    def counted(value):
        decodes.append(value)
        return original_photo(value)
    monkeypatch.setattr(pixels, '_photo', counted)
    clean = report(tmp_path)
    assert len(decodes) == 1
    # A second invocation must photograph again; no cross-call cache exists.
    assert clean == report(tmp_path)
    assert len(decodes) == 2
    restore = pixels._PhotoCache.restore
    def changed(cache, value):
        erase_heads(Path(value))
        return restore(cache, value)
    monkeypatch.setattr(pixels._PhotoCache, 'restore', changed)
    cached = report(tmp_path)
    path.write_bytes(original_bytes)
    monkeypatch.setattr(pixels, 'PHOTO_CACHE_BYTES', 0)
    control = report(tmp_path)
    assert cached == control
    assert cached != clean


def test_non_byte_aligned_masks_and_empty_columns_round_trip_exactly():
    from piano_teacher.notation.pixel_proof import RasterStaff
    rng = np.random.default_rng(401)
    masks = [rng.random((7, 13)) > .5 for _ in range(5)]
    original = dict(ink=masks[0], layers=masks[1:3], head_pixels=masks[3],
        occlusion=masks[4], shape=(7, 13), camera=None,
        occlusion_columns=np.array([], dtype=np.intp), occluded=47,
        staves={'right': RasterStaff('right', (.5, 2.5, 4.5, 6.5, 8.5), 2.)})
    restored = pixels._PhotoCache._unpack(pixels._PhotoCache._pack(original))
    for actual, expected in zip((restored['ink'], *restored['layers'], restored['head_pixels'], restored['occlusion']), masks):
        np.testing.assert_array_equal(actual, expected)
        assert actual.dtype == np.bool_
        assert not np.shares_memory(actual, expected)
    assert restored['staves'] == original['staves']
    assert restored['staves']['right'] is not original['staves']['right']
    assert restored['camera'] is None
    assert restored['occlusion_columns'].dtype == original['occlusion_columns'].dtype
    assert restored['occlusion_columns'].shape == (0,)


def test_actual_photo_cache_resource_bounds_in_an_isolated_process():
    import subprocess
    import sys
    code = """
import resource
from pathlib import Path
from tempfile import TemporaryDirectory
from piano_teacher.notation import extra_symbol_pixels as p
resource.setrlimit(resource.RLIMIT_AS,(1024**3*3,1024**3*3))
p.PHOTO_CACHE_BYTES=32_000
p.PHOTO_CACHE_ENTRIES=3
cache=p._PhotoCache()
path=Path('tests/fixtures/extra_shard_pixels/clair-onset.png').resolve()
# Unique keys exercise eviction without retaining a case of decoded arrays.
with TemporaryDirectory() as folder:
    for i in range(20):
        frame=Path(folder)/f'native-{i}.png'
        frame.symlink_to(path)
        data=cache.capture(frame)
        assert cache.bytes_used<=p.PHOTO_CACHE_BYTES
        assert len(cache.entries)<=p.PHOTO_CACHE_ENTRIES
assert data['ink'].any()
print('bounded')
"""
    result = subprocess.run([sys.executable, '-c', code],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout+result.stderr
    assert 'bounded' in result.stdout
