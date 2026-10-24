"""Retired renderer resources cannot remain alternate executable pipelines."""
from pathlib import Path
import json
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]

RETIRED = (
    "godot/notation/legacy/strip.gd",
    "godot/notation/legacy/exact_spacing.gd",
    "godot/notation/legacy/motion_curve.gd",
    "godot/notation/legacy/quality.gd",
    "godot/notation/shared/beat_camera.gd",
    "godot/diagnostic_score.gd",
    "tests/godot/score_strip.gd",
    "tests/godot/score_exact_spacing.gd",
    "tests/godot/score_motion_curve.gd",
    "tests/godot/user_midi_visual_regression.gd",
)


def test_retired_godot_runtime_and_resource_companions_are_removed():
    remaining = [name for name in RETIRED if (ROOT / name).exists()]
    remaining += [name + ".uid" for name in RETIRED if (ROOT / (name + ".uid")).exists()]
    assert not remaining, remaining


def test_scroll_velocity_audit_measures_actual_native_source_heads(tmp_path):
    from scripts import audit_scroll_velocity as audit

    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    audit.make_render_fixture(tmp_path, bars=2)
    assert (tmp_path / "native.json").exists(), "Velocity audit still prepares a raster-only renderer"
    assert audit.run_fixture(binary, tmp_path, "native source heads", 1.01)
    samples = json.loads((tmp_path / "samples.json").read_text())
    payload = json.loads((tmp_path / "native.json").read_text())
    bounds = audit.measure_speed_bounds(payload, samples)
    assert bounds["samples"] == len(samples) >= 6
    assert bounds["min_ratio"] == pytest.approx(1.0, abs=.001)
    assert bounds["max_ratio"] == pytest.approx(1.0, abs=.001)
    for corruption in ("missing", "duplicate", "source-beat", "speed", "non-finite"):
        bad = [dict(sample) for sample in samples]
        if corruption == "missing":
            bad.pop()
        elif corruption == "duplicate":
            bad.append(dict(bad[0]))
        elif corruption == "source-beat":
            bad[0]["beat"] += 1
        elif corruption == "speed":
            bad[0]["after"] = bad[0]["before"]
        else:
            bad[0]["before"] = float("nan")
        with pytest.raises(ValueError):
            audit.measure_speed_bounds(payload, bad)
