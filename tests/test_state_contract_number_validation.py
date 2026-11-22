"""A5: malformed transport and visual time cannot reach native presentation."""
from math import inf, nan

import pytest

from piano_teacher.state_contract import (
    CONTROL_ACTIONS, VERSION, problems,
)


def _state():
    return {
        "schema_version": VERSION,
        "loaded": False,
        "controls": {name: {"action": "", "enabled": False}
                     for name in CONTROL_ACTIONS},
    }


@pytest.mark.parametrize("key", [
    "bpm", "clock_beat", "visual_scroll_beat",
    "visual_target_beat", "clock_sampled_at_ms",
])
@pytest.mark.parametrize("value", [nan, inf, -inf])
def test_nonfinite_top_level_time_and_rate_are_rejected(key, value):
    state = _state()
    state[key] = value
    assert any("must be finite" in error for error in problems(state))


def test_finite_numeric_ports_remain_valid():
    state = _state()
    state.update(bpm=20, clock_beat=-4.0, visual_scroll_beat=0.0)
    assert problems(state) == []


@pytest.mark.parametrize("value", [nan, inf, -inf, None, "beat"])
def test_invalid_target_source_beat_is_rejected(value):
    state = _state()
    state.update({
        "loaded": True,
        "mode": "practice",
        "phase": "ready",
        "running": False,
        "paused": False,
        "revision": 1,
        "transport_id": 1,
        "piece_fingerprint": "original",
        "presentation_directive": {"kind": "target", "source_beat": value},
        "playback_timeline": {},
    })
    assert any("finite source_beat" in error for error in problems(state))
