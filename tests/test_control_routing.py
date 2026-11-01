"""Control classification cannot read engine state or dispatch effects."""
import pytest

from piano_teacher.application.control_dispatch import ControlDispatcher


@pytest.mark.parametrize(("action", "expected"), [
    ("calibration_start", "calibration"), ("calibration_reset", "calibration"),
    ("reset_path", "reset"),
    ("score_ready", "acknowledgement"), ("demo_ready", "acknowledgement"),
    ("listen", "listening"), ("perform", "listening"),
    ("practice_weak", "listening"), ("review_retry", "listening"),
    ("seek", "listening"),
    ("learn_next", "learning"), ("skip_stage", "learning"),
    ("place_original", "learning"), ("revisit_trouble", "learning"),
    ("learn", "learning"), ("learn_retry", "learning"),
    ("open_at", "learning"), ("hints", "learning"),
    ("practice", "transport"), ("stop", "transport"),
    ("start", "transport"), ("restart", "transport"),
    ("pause", "transport"), ("resume", "transport"),
    ("select_step", "stage"), ("tempo_up", "stage"),
    ("tempo_down", "stage"), ("hand", "stage"),
    ("unknown", "stage"),
])
def test_locked_control_route_is_pure(action, expected):
    assert ControlDispatcher.route(action) == expected


def test_routing_requires_no_engine_instance():
    assert not hasattr(ControlDispatcher, "dispatch")
    assert ControlDispatcher.route("score_ready") == "acknowledgement"
