"""Unit tests for the real Godot cursor trace evaluator."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "smoke_godot_cursor", Path(__file__).resolve().parents[1] / "scripts" / "smoke_godot.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _trace(samples):
    return "\n".join("PHASE0_CURSOR_BEAT:%s SCREEN_X:%s VISIBLE:%s" % sample for sample in samples)


def test_visible_moving_beam_passes():
    assert module.moving_cursor_observed(_trace([(0.02, 120, "true"), (.3, 180, "true"), (.6, 260, "true")]))


def test_playing_phase_alone_does_not_pass():
    assert not module.moving_cursor_observed("PHASE0_PHASE:playing\nPHASE0_SCORE_READY:1200 x 800")


def test_static_hidden_and_backward_beams_fail():
    assert not module.moving_cursor_observed(_trace([(.1, 200, "true"), (.4, 200, "true"), (.8, 200, "true")]))
    assert not module.moving_cursor_observed(_trace([(.1, 200, "false"), (.4, 300, "false"), (.8, 400, "false")]))
    assert not module.moving_cursor_observed(_trace([(.1, 200, "true"), (.8, 300, "true"), (.6, 400, "true")]))


def test_stationary_beam_with_scrolling_score_counts_as_motion():
    transcript = _trace([(0.05, 310, "true"), (.32, 310, "true"), (.71, 310, "true")])
    transcript += "\nCONTENT_X:-100\nCONTENT_X:-170\nCONTENT_X:-240"
    assert module.moving_cursor_observed(transcript)



def _lead(samples):
    return "\n".join("PHASE0_LEAD_BEAT:%s CONTENT_X:%s CURSOR_X:%s VISIBLE:%s" % sample for sample in samples)


def test_count_in_scrolls_under_fixed_beam():
    assert module.moving_lead_in_observed(_lead([
        (-2.25, 650, 430, "true"), (-1.25, 430, 430, "true"), (-.25, 210, 430, "true")]))


def test_hidden_countdown_and_stationary_score_do_not_pass():
    assert not module.moving_lead_in_observed("PHASE0_PHASE:count_in\nGET READY")
    assert not module.moving_lead_in_observed(_lead([
        (-2, 320, 430, "true"), (-1, 320, 430, "true"), (-.25, 320, 430, "true")]))
    assert not module.moving_lead_in_observed(_lead([
        (-2, 650, 430, "false"), (-1, 430, 430, "false"), (-.25, 210, 430, "false")]))


def test_wandering_count_in_beam_fails():
    assert not module.moving_lead_in_observed(_lead([
        (-2, 650, 220, "true"), (-1, 430, 340, "true"), (-.25, 210, 430, "true")]))
