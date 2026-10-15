"""The integration smoke must reach the real Godot practice and score paths."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCENE = (ROOT / "godot" / "main.gd").read_text(encoding="utf-8")
SMOKE = (ROOT / "scripts" / "smoke_godot.py").read_text(encoding="utf-8")


def test_smoke_enters_practice_and_waits_for_png_and_playing():
    assert 'OS.get_cmdline_user_args().has("--phase0-smoke")' in SCENE
    assert 'if phase0_smoke_mode:\n        _navigate("practice")' in SCENE
    assert 'print("PHASE0_SCORE_READY:"' in SCENE
    assert 'score_view.texture = ImageTexture.create_from_image(cropped)' in SCENE
    assert 'lambda log: "PHASE0_SCORE_READY:" in log' in SMOKE
    assert 'lambda log: "PHASE0_PHASE:count_in" in log' in SMOKE
    assert 'lambda log: "PHASE0_PHASE:playing" in log' in SMOKE
    assert 'if state["mastered"] != 0 or state["phase"] != "ready":' in SMOKE


def test_smoke_uses_isolated_storage_and_accepts_a_real_song():
    assert 'env["XDG_DATA_HOME"] = str(temp / "data")' in SMOKE
    assert 'env["XDG_CONFIG_HOME"] = str(temp / "config")' in SMOKE
    assert '"--no-midi"' in SMOKE
    assert 'parser.add_argument("--file", type=Path,' in SMOKE
    assert 'fixture.write_bytes(file.read_bytes())' in SMOKE


def test_smoke_requires_moving_visible_cursor_and_scheduled_count_in_clicks():
    assert "await_condition(moving_cursor_observed" in SMOKE
    assert "PHASE0_CURSOR_BEAT:" in SCENE
    assert 'log.count("PHASE0_CLICK:count_in") >= 2' in SMOKE
    assert "PHASE0_CLICK:" in SCENE


def test_score_motion_during_lead_is_an_acceptance_gate():
    assert "await_condition(moving_lead_in_observed" in SMOKE
    assert "PHASE0_LEAD_BEAT:" in SCENE
    assert "target_x = viewport.x * 0.42 - note_x * displayed_width" in SCENE
