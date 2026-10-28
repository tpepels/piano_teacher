"""Bound long-score resource use without dropping source witnesses."""
from pathlib import Path
import shutil

import numpy as np

from piano_teacher.notation.captured_frames import CapturedFrames
from piano_teacher.notation.connector_pixels import verify_beam_pixels
from piano_teacher.notation.proof import read_written_score

FIXTURE = Path(__file__).parent/'fixtures/connector_pixels/beams'


def test_frame_cache_evicts_least_recently_used_real_png_and_can_reload(tmp_path):
    for beat in range(40):
        shutil.copyfile(FIXTURE/'native-0.00000.png', tmp_path/f'native-{beat:.5f}.png')
    written = read_written_score((FIXTURE/'score.musicxml').read_text())
    frames = CapturedFrames(tmp_path, written)
    first_pixels = frames.frame(0)['pixels'].copy()
    for beat in range(1, 16):
        frames.frame(beat)
    recent = frames.frame(0)
    for beat in range(16, 40):
        frames.frame(beat)
        assert len(frames.frames) <= 16
        if beat == 16:
            assert 0 in frames.frames and 1 not in frames.frames
    assert 0 not in frames.frames and 1 not in frames.frames
    assert np.array_equal(frames.frame(0)['pixels'], first_pixels)
    assert len(frames.frames) <= 16
    assert recent['name'] == 'native-0.00000.png'


def test_source_anchor_cache_retains_no_image_support_arrays():
    written = read_written_score((FIXTURE/'score.musicxml').read_text())
    frames = CapturedFrames(FIXTURE, written)
    for event in written.symbols:
        if event['kind'] == 'note' and event['staff'] == 'right':
            head = frames.head(event)
            assert {'x', 'y', 'bbox', 'score', 'gap'} <= head.keys()
            assert 'support' not in head
    def arrays(value):
        if isinstance(value, np.ndarray):
            return True
        if isinstance(value, dict):
            return any(arrays(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(arrays(v) for v in value)
        return False
    assert not arrays(frames.registrations)


def test_each_api_call_scans_capture_clocks_once_for_all_source_groups(monkeypatch):
    original = Path.glob
    scans = []
    def counted(path, pattern, **kwargs):
        if pattern == 'native-*.png':
            scans.append(path)
        return original(path, pattern, **kwargs)
    monkeypatch.setattr(Path, 'glob', counted)
    report = verify_beam_pixels((FIXTURE/'score.musicxml').read_text(), FIXTURE, hand='right')
    assert report['coverage']['expected'] == report['coverage']['verified'] == 2
    assert scans == [FIXTURE]


def test_nearest_capture_search_does_not_traverse_full_performance_clock_list():
    class IndexedClocks(tuple):
        reads = 0
        def __iter__(self):
            raise AssertionError('Nearest witnesses must not scan every performance clock')
        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)
    written = read_written_score((FIXTURE/'score.musicxml').read_text())
    frames = CapturedFrames(FIXTURE, written)
    frames.clocks = IndexedClocks(range(18000))
    assert frames.nearby_clocks([9000., 9001.]) == [8999, 9002, 8998, 9003]
    assert frames.clocks.reads < 64
