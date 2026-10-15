"""Tempo-capped count-in is short even when beginning at very slow BPM."""
import pytest
from piano_teacher.lesson_timing import lead_in_beats


@pytest.mark.parametrize("bar,bpm,expected", [
    (4, 100, 4),
    (3, 100, 3),
    (4, 40, 2.5),
    (3, 40, 2.5),
    (4, 20, 1),
    (3, 12, 0.5),
    (3, 120, 3),
])
def test_lead_in_is_at_most_one_measure_and_about_four_seconds(bar, bpm, expected):
    lead = lead_in_beats(bar, bpm)
    assert lead == expected
    assert lead <= bar
    assert lead * 60 / bpm <= 4.01


def test_invalid_count_in_inputs_fail():
    for args in [(0,40), (4,0), (-2,120)]:
        with pytest.raises(ValueError):
            lead_in_beats(*args)


def test_godot_scrolling_is_unconditional_during_transport():
    from pathlib import Path
    gd=(Path(__file__).resolve().parents[1]/"godot"/"main.gd").read_text()
    assert "target_x = viewport.x * 0.42 - note_x * displayed_width" in gd
    assert "if displayed_width > viewport.x * 0.91:" not in gd
    assert "var initial_cursor: Dictionary = _position_at_beat(play_from)" in gd
    assert "PHASE0_LEAD_BEAT:" in gd
    assert 'game_phase_cue = GamePhaseCue.new()' in gd
    assert 'game_count_in.present(beat,' in gd
