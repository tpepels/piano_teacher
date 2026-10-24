"""The integration smoke must reach the real Godot practice and score paths."""
from pathlib import Path
from test_phase1_camera import native_camera_run
ROOT = Path(__file__).resolve().parents[1]
SCENE = (ROOT / "godot" / "main.gd").read_text(encoding="utf-8")
SMOKE = (ROOT / "scripts" / "smoke_godot.py").read_text(encoding="utf-8")


def test_smoke_enters_practice_and_prepares_native_score(native_camera_run):
    report, output = native_camera_run
    assert report["screen"] == "practice" and report["native_ready"]
    assert "PHASE0_SCORE_READY_NATIVE: REVISION:" in output
    assert "NATIVE_MODEL_READY:" in output
    assert report["lead_samples"] >= 2 and report["playing_samples"] >= 3
    assert 'lambda log: "PHASE0_PHASE:count_in" in log' in SMOKE
    assert 'lambda log: "PHASE0_PHASE:playing" in log' in SMOKE
    assert 'state["mastered"] != 0 or state["phase"] != "preview_gap"' in SMOKE
    assert 'stopped["phase"] != "ready" or stopped["mastered"] != 0' in SMOKE


def test_smoke_uses_isolated_storage_and_accepts_a_real_song():
    assert 'env["XDG_DATA_HOME"] = str(temp / "data")' in SMOKE
    assert 'env["XDG_CONFIG_HOME"] = str(temp / "config")' in SMOKE
    assert '"--no-midi"' in SMOKE
    assert 'parser.add_argument("--file", type=Path,' in SMOKE
    assert 'fixture.write_bytes(file.read_bytes())' in SMOKE


def test_smoke_requires_moving_visible_cursor_and_scheduled_count_in_clicks(native_camera_run):
    from scripts.smoke_godot import moving_cursor_observed

    _, output = native_camera_run
    transport = output.split("NATIVE_CAMERA_TRANSPORT_BEGIN", 1)[1].split(
        "NATIVE_CAMERA_TRANSPORT_END", 1)[0]
    assert moving_cursor_observed(transport), transport
    assert output.count("PHASE0_CLICK:count_in") >= 2
    assert "PHASE0_VISIBLE_NOTES:" in transport


def test_score_motion_during_lead_is_an_acceptance_gate(native_camera_run):
    from scripts.smoke_godot import moving_lead_in_observed

    _, output = native_camera_run
    transport = output.split("NATIVE_CAMERA_TRANSPORT_BEGIN", 1)[1].split(
        "NATIVE_CAMERA_TRANSPORT_END", 1)[0]
    assert moving_lead_in_observed(transport, count_in_beats=.5), transport
