"""Exercise actual Godot controls, keyboard commands, navigation and layout.

These catch accidental stop-on-pause, lost practice position on short detours,
incorrect Settings return destinations, and clipped connection guidance.
"""
from pathlib import Path
import shutil
import subprocess

import pytest

from test_recovery_motion import make_midi_fixture

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


@pytest.fixture(scope="module")
def native_fixture(tmp_path_factory):
    folder = tmp_path_factory.mktemp("native-interactions")
    make_midi_fixture(folder, "chords", "both")
    return folder


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
@pytest.mark.parametrize("scenario", [
    "three_button_stage", "short_challenge_loop", "primary_transport", "secondary_stop", "focused_shortcuts", "practice_detours",
    "settings_back_origin", "abandon_practice", "compact_feedback", "caption_bounds", "notation_phase_cues", "instructional_transition", "modes", "pause_choices", "focus_trap", "learner_progression", "handsfree_midi",
])
def test_actual_practice_interactions(scenario, tmp_path, native_fixture):
    # Isolate any Godot user settings from the real desktop session.
    import os
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/practice_interactions.gd"), "--", scenario, str(native_fixture)],
        capture_output=True, text=True, timeout=30, env=env,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PRACTICE_INTERACTION_FAILURES:0" in output, output
