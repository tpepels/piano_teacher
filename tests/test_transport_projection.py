"""Independent transport projection: no live clock or PracticeEngine needed."""
from dataclasses import replace

import pytest

from piano_teacher.exercise_contracts import TempoMap, TempoSegment
from piano_teacher.transport_projection import (
    VisualMotionSnapshot, project_visual_motion,
)


@pytest.fixture
def snapshot():
    return VisualMotionSnapshot(
        phrase_length=8.0, visual_offset=12.0, play_from_beat=0.0,
        bpm=80.0, run_at=100.0, running=False,
        preparation_pending=False, preparation_at=0.0, preparation_measure=None,
        rewind_from=None, rewind_to=None, rewind_at=0.0,
        rewind_seconds=1.0, pending_auto_result=False,
        preview_loop_pending=False, gap_beats=4.0, paused=False,
    )


def test_idle_and_running_keep_single_beat_coordinate_system(snapshot):
    assert project_visual_motion(snapshot, 101) == (12, 0, 20)
    playing = replace(snapshot, running=True, play_from_beat=2)
    position, speed, target = project_visual_motion(playing, 101.5)
    assert position == pytest.approx(16)
    assert speed == pytest.approx(80/60)
    assert target == 20


@pytest.mark.parametrize("flag", ["pending_auto_result", "preview_loop_pending"])
def test_completed_pass_advances_through_gap_without_a_new_camera_origin(snapshot, flag):
    gap = replace(snapshot, **{flag: True})
    position, speed, target = project_visual_motion(gap, 106.75)
    assert position == pytest.approx(21)
    assert speed == pytest.approx(80/60)
    assert target == 24
    position, speed, target = project_visual_motion(gap, 110)
    assert position == pytest.approx(25.333333333333332)
    assert speed == pytest.approx(80/60)
    assert target == 24
    # A slow engine transition can no longer freeze the visible bar at 24.
    after, _, _ = project_visual_motion(gap, 110.2)
    assert after - position == pytest.approx(.2 * 80/60)


def test_rewind_is_backward_and_preparation_resumes_forward(snapshot):
    prep = replace(snapshot, preparation_pending=True, preparation_at=106,
                   preparation_measure={"start_beat":8.0, "end_beat":12.0},
                   rewind_from=20, rewind_to=8, rewind_at=104,
                   rewind_seconds=2.0)
    assert project_visual_motion(prep, 105) == (14, -6, 8)
    assert project_visual_motion(prep, 106) == (8, 80/60, 12)
    pos, speed, target = project_visual_motion(prep, 107.5)
    assert pos == pytest.approx(10)
    assert speed == pytest.approx(80/60)
    assert target == 12
    assert project_visual_motion(prep, 111) == (12, 0, 12)


def test_paused_projection_freezes_speed_at_supplied_paused_instant(snapshot):
    paused = replace(snapshot, running=True, paused=True)
    position, speed, _ = project_visual_motion(paused, 101)
    assert position == pytest.approx(13.333333333333334)
    assert speed == 0
    assert project_visual_motion(paused, 101) == project_visual_motion(paused, 101)


def test_rewind_endpoint_holds_without_accidental_forward_motion(snapshot):
    rewind = replace(snapshot, rewind_from=22, rewind_to=12,
                     rewind_at=100, rewind_seconds=2)
    assert project_visual_motion(rewind, 99) == (22, -5, 12)
    assert project_visual_motion(rewind, 101) == (17, -5, 12)
    assert project_visual_motion(rewind, 102) == (12, 0, 12)


def test_active_preparation_and_rewind_require_valid_targets(snapshot):
    with pytest.raises(ValueError, match="measure"):
        project_visual_motion(replace(snapshot, preparation_pending=True,
                                     preparation_at=0), 100)
    with pytest.raises(ValueError, match="target"):
        project_visual_motion(replace(snapshot, rewind_from=2), 100)


def test_shaped_forward_projection_is_continuous_through_rest_and_repeat(snapshot):
    tempo = TempoMap("test", (
        TempoSegment(0, 4, 48),
        TempoSegment(4, 8, 60),
    ))
    moving = replace(snapshot, phrase_length=8.0, visual_offset=12.0,
                     bpm=80.0, run_at=100.0, running=True)
    # Authored passage: four beats at 48 BPM, then four at 60 BPM.
    # Appended rest: four beats at the practice BPM of 80.
    first = project_visual_motion(moving, 105.0, tempo_map=tempo)
    assert first == pytest.approx((16.0, 1.0, 20.0))
    end = project_visual_motion(moving, 109.0, tempo_map=tempo)
    assert end == pytest.approx((20.0, 80/60, 20.0))
    resting = replace(moving, running=False, pending_auto_result=True)
    assert project_visual_motion(resting, 109.0, tempo_map=tempo) == pytest.approx(
        (20.0, 80/60, 24.0))
    assert project_visual_motion(resting, 110.5, tempo_map=tempo) == pytest.approx(
        (22.0, 80/60, 24.0))
    # The backend may update late; rendering remains time-indexed.
    assert project_visual_motion(resting, 112.25, tempo_map=tempo)[0] == pytest.approx(24.3333333333)
    repeated = replace(moving, visual_offset=24.0, run_at=112.0)
    assert project_visual_motion(repeated, 112.25, tempo_map=tempo)[0] == pytest.approx(
        24.0+.25*48/60)


def test_shaped_seek_and_pause_keep_same_source_epoch(snapshot):
    tempo = TempoMap("test", (
        TempoSegment(0, 4, 48),
        TempoSegment(4, 8, 60),
    ))
    partial = replace(snapshot, phrase_length=8.0, visual_offset=16.0,
                      play_from_beat=4.0, bpm=80.0, run_at=100.0, running=True)
    at = project_visual_motion(partial, 102.0, tempo_map=tempo)
    assert at[0] == pytest.approx(22.0)  # source beat 6
    assert at[1] == pytest.approx(1.0)
    paused = replace(partial, paused=True)
    frozen = project_visual_motion(paused, 102.0, tempo_map=tempo)
    assert frozen[0] == at[0] and frozen[1] == 0.0
    assert project_visual_motion(paused, 102.0, tempo_map=tempo) == frozen
    with pytest.raises(ValueError, match="duration"):
        project_visual_motion(replace(partial, phrase_length=7.0), 102.0,
                              tempo_map=tempo)
