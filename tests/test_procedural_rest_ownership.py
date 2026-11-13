"""Strict independent ownership for the two real printed practice-gap rests.

The source note/rest inventory must never authorize extra ink. A procedural
full-meter gap can own *two* independently photographed, source-after-end
glyphs only when its exact clock, staff, longitudinal motion and identities
survive repeated real-frame registration. The synthetic snapshots here use
physical positions measured in the Hanon 37–40 Godot capture.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import copy

import pytest

from piano_teacher.notation.procedural_rest_ownership import (
    _source_gap_duration, _photographic_density, _pair_at,
    confirmed_gap_tracks, verified_procedural_pair,
)


@dataclass(frozen=True)
class Staff:
    lines: tuple[float, ...]
    gap: float = 22.

    @property
    def bottom(self):
        return self.lines[-1]


def _source():
    return SimpleNamespace(
        bars=(0., 2., 4., 6., 8.),
        meter=((0, (2, 4)), (0, (2, 4))),
    )


def _frame(index, *, duplicate=False):
    clock = 4.75+index*.0625
    cx = 1507-index*15
    objects = [
        {"family":"rest","name":"rest_whole","score":1.0,
         "bbox":[cx-14, 164, cx+14, 177],"track":4856},
        {"family":"rest","name":"rest_whole","score":1.0,
         "bbox":[cx-14, 336, cx+14, 349],"track":4857},
    ]
    if duplicate:
        objects.append({**objects[0],"track":6000})
    return dict(clock=clock,travel=-15*index,shift=None if not index else -15,
                motion=None if not index else {"position_error":.5},
                camera=507.0,
                staves={
                    "right":Staff((143., 165., 187., 209., 231.)),
                    "left":Staff((315., 337., 359., 381., 403.)),
                },objects=objects)


def test_real_hanon_photo_positions_identify_exact_two_meter_rests():
    frames = [_frame(i) for i in range(6)]
    assert _source_gap_duration(_source()) == 2.
    assert _photographic_density(frames) == 240.
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == {4856,4857}
    assert proof["source_end"] == 8. and proof["gap_beats"] == 2.
    assert all(len(verified_procedural_pair(frame,proof)) == 2
               for frame in frames)


@pytest.mark.parametrize("change", [
    "missing_left","extra_right","low_score","off_staff","wrong_time",
    "wrong_source_meter","no_motion","other_track"
])
def test_corrupted_procedural_ink_cannot_acquire_ownership(change):
    frames = [_frame(i) for i in range(6)]
    written = _source()
    if change == "missing_left":
        for frame in frames:
            frame["objects"].pop()
    elif change == "extra_right":
        for frame in frames:
            frame["objects"].append({**frame["objects"][0],"track":42})
    elif change == "low_score":
        for frame in frames:
            frame["objects"][0]["score"] = .82
    elif change == "off_staff":
        for frame in frames:
            frame["objects"][0]["bbox"][1] -= 30
            frame["objects"][0]["bbox"][3] -= 30
    elif change == "wrong_time":
        for frame in frames:
            frame["clock"] += 2.
    elif change == "wrong_source_meter":
        written = SimpleNamespace(bars=(0.,1.,2.,3.,4.),
                                  meter=((0,(2,4)),))
    elif change == "no_motion":
        for frame in frames[1:]:
            frame["shift"] = None
    elif change == "other_track":
        for frame in frames:
            frame["objects"][1]["track"] = frame["clock"]
    assert not confirmed_gap_tracks(written,frames),change


def test_current_frame_mutation_revokes_only_its_pair_without_trust_from_others():
    frames = [_frame(i) for i in range(6)]
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof
    changed = copy.deepcopy(frames[3])
    changed["objects"][1]["bbox"] = [200,300,228,313]
    assert not verified_procedural_pair(changed,proof)
    assert len(verified_procedural_pair(frames[2],proof)) == 2


def test_incomplete_or_conflicting_meter_never_makes_extra_rest_expected():
    assert _source_gap_duration(SimpleNamespace(
        bars=(0.,1.5,3.5),meter=((0,(2,4)),))) is None
    assert _source_gap_duration(SimpleNamespace(
        bars=(0.,2.,4.),meter=((0,(2,4)),(0,(3,4))))) is None


def test_registered_contour_track_fragments_share_only_the_same_source_gap():
    # Actual GL contours sometimes fall below the strict shape threshold
    # during subpixel translation and regain a new track on rescan. Each
    # fragment is stable in at least three independent photographs.
    frames = [_frame(i) for i in range(12)]
    for index, frame in enumerate(frames):
        for obj in frame["objects"]:
            obj["track"] += (index//4)*2
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == set(range(4856,4862))
    assert all(len(verified_procedural_pair(frame,proof)) == 2 for frame in frames)


def test_lone_fragment_at_other_time_never_inherits_a_confirmed_gap():
    frames = [_frame(i) for i in range(12)]
    for frame in frames[4:8]:
        for obj in frame["objects"]:
            obj["track"] += 2
            obj["bbox"][0] -= 90
            obj["bbox"][2] -= 90
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == {4856,4857}
    assert all(not verified_procedural_pair(frame,proof) for frame in frames[4:8])


def test_brief_fragment_must_follow_the_confirmed_photographic_trajectory():
    frames = [_frame(i) for i in range(12)]
    for frame in frames[4:6]:
        for obj in frame["objects"]:
            obj["track"] += 2
            # Still inside the original broad source/meter search box.
            obj["bbox"][0] += 10
            obj["bbox"][2] += 10
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == {4856,4857}
    assert all(not verified_procedural_pair(frame,proof) for frame in frames[4:6])


@pytest.mark.parametrize("source_beat", [7.5, 8.25])
def test_pair_inside_occupied_source_cannot_borrow_nearby_gap_midpoint(source_beat):
    frames = [_frame(i) for i in range(6)]
    for index, frame in enumerate(frames):
        frame["travel"] = -index*1.25
        frame["shift"] = -1.25 if index else None
        # At low density the midpoint search radius reaches source music.
        # Source end is 8; both placements overlap the occupied source.
        cx = 507+(source_beat-frame["clock"])*20
        for obj in frame["objects"]:
            obj["bbox"][0], obj["bbox"][2] = cx-14,cx+14
    assert _photographic_density(frames) == 20
    assert not confirmed_gap_tracks(_source(),frames)


def test_low_score_in_current_frame_revokes_a_previously_confirmed_fragment():
    frames = [_frame(i) for i in range(6)]
    proof = confirmed_gap_tracks(_source(),frames)
    changed = copy.deepcopy(frames[3])
    changed["objects"][0]["score"] = .89999
    assert not verified_procedural_pair(changed,proof)


def test_brief_two_track_fragment_requires_stable_photographs_on_both_sides():
    frames = [_frame(i) for i in range(12)]
    for frame in frames[4:6]:
        for obj in frame["objects"]:
            obj["track"] += 2
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == {4856,4857,4858,4859}
    assert all(len(verified_procedural_pair(frame,proof)) == 2 for frame in frames)
    # A short new fragment only at an end has no photographic bridge.
    proof = confirmed_gap_tracks(_source(),frames[:6])
    assert proof["tracks"] == {4856,4857}
    assert not verified_procedural_pair(frames[4],proof)


def test_a_brief_single_track_identity_change_cannot_be_bridged():
    frames = [_frame(i) for i in range(12)]
    for frame in frames[4:6]:
        frame["objects"][0]["track"] += 2
    proof = confirmed_gap_tracks(_source(),frames)
    assert proof["tracks"] == {4856,4857}
    assert not verified_procedural_pair(frames[4],proof)
