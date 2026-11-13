"""Photographic connector witnesses after a fixed playhead crosses source ink.

Only an existing actual captured PNG timestamp can be tried. The original
independent source-pixel comparison and refusal of offscreen/occluded captures
remain mandatory. In Chopin 13-16 a beam ends at beat 8.875 while screenshots
at 9.0/9.15/9.3 are actually retained; onset-only selection was missing them.
"""
from piano_teacher.notation.captured_frames import CapturedFrames


def frames_with(clocks):
    gallery = CapturedFrames.__new__(CapturedFrames)
    gallery.clocks = tuple(clocks)
    return gallery


def test_real_chopin_clock_inventory_makes_fully_past_playhead_witnesses():
    frames = frames_with([7.5,7.65,7.75,7.8,7.95,8.,8.1,8.25,
                          8.4,8.5,8.55,8.7,8.85,8.875,
                          9.,9.15,9.3,9.45,9.5,9.6,9.75])
    source = [7.5,7.75,8.,8.25,8.5,8.875]
    assert frames.post_group_clocks(source) == [9.,9.15,9.3]
    assert all(clock > max(source) for clock in frames.post_group_clocks(source))


def test_real_capture_only_and_no_future_frame_are_not_a_pass():
    frames = frames_with([0.,.25,.5,.75,1.])
    assert frames.post_group_clocks([1.]) == []
    assert frames.post_group_clocks([]) == []
    assert frames.post_group_clocks([.5],limit=0) == []


def test_bounded_witnesses_never_look_a_measure_into_another_passage():
    frames = frames_with([0.,.0625,.125,.25,.5,.5001,.501,.75,1.,1.5])
    assert frames.post_group_clocks([0.],limit=10) == [
        .0625,.125,.25,.5]
    assert frames.post_group_clocks([0.],limit=2) == [.0625,.125]
    assert frames.post_group_clocks([.5],limit=10) == [.5001,.501,.75,1.]


def test_existing_early_onset_neighbor_search_is_unchanged():
    frames = frames_with([0.,.0625,.125,.5,.75,.875,1.,1.125])
    # This is a separate evidence channel, not replacement of the existing
    # nearby-clocks query. Both must use saved clocks, never an invented time.
    assert frames.nearby_clocks([.5],limit=3) == [.75,.125,.875]
    assert frames.post_group_clocks([.5],limit=3) == [.75,.875,1.]


def test_late_post_group_witness_lookup_uses_bounded_indexed_access():
    class IndexedClocks(tuple):
        reads = 0
        def __iter__(self):
            raise AssertionError('Post-group witnesses must not scan every performance clock')
        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)

    frames = CapturedFrames.__new__(CapturedFrames)
    frames.clocks = IndexedClocks(index * .15 for index in range(100_000))
    assert frames.post_group_clocks([14998.5]) == [
        14998.65, 14998.8, 14998.949999999999]
    assert frames.clocks.reads < 32


def test_post_group_selection_preserves_exact_half_beat_and_epsilon_edges():
    frames = frames_with([.00001, .0000100001, .25, .50001, .5000101])
    assert frames.post_group_clocks([0.], limit=10) == [
        .0000100001, .25, .50001]
