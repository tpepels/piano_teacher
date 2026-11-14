"""Fast ownership gate for fixtures reached only by the manual full suite.

These fixtures regress when the UI command owner is extracted but a
headless-only script continues to call the former Main.command_state.
The full Godot tests still own actual behavior; this test rejects stale
interfaces before a costly full-suite run.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "tests" / "godot"


@pytest.mark.parametrize("name", [
    "learning_statistics_native.gd",
    "pending_navigation.gd",
    "practice_interactions.gd",
    "art_direction.gd",
    "library_resume.gd",
])
def test_full_suite_godot_fixtures_use_extracted_owner(name):
    source = (GODOT / name).read_text()
    assert ".command_state" not in source
    assert "app.command_coordinator.state" in source


def test_recording_adapter_is_bound_to_command_owner():
    source = (GODOT / "pending_navigation.gd").read_text()
    assert "command_coordinator.action_request = action_request" in source


def test_library_resume_uses_signal_based_command_results():
    source = (GODOT / "library_resume.gd").read_text()
    assert "CommandSuccessEffects.new(command_success_presenter)" in source
    assert "command_coordinator.configure(" in source
    assert "command_coordinator.succeeded.connect(command_success_effects.apply)" in source


def test_notation_probes_do_not_select_retired_desktop_strategies():
    for name in ("test_phase1_camera.py", "test_native_head_ink.py"):
        source = (ROOT / "tests" / name).read_text()
        assert "WARMUP_STRATEGY" in source
        assert 'library.update(exercise_strategy="source-progression")' not in source
    midi_source = (ROOT / "tests/test_full_native_open_with_lumikey.py").read_text()
    assert 'set_preferences(exercise_strategy="coda-midi")' not in midi_source
    assert 'set_preferences(exercise_strategy="coda-fukuda-midi")' in midi_source
