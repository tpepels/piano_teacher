"""The visible -5 BPM control coexists with step, hand and transport controls."""
import json
import shutil

import pytest

from scripts.review_art_direction import main


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")), reason="Godot required")
def test_real_practice_controls_preserve_manual_tempo(tmp_path, monkeypatch):
    monkeypatch.setenv("PIANO_TEACHER_NATIVE_NOTATION", "1")
    # Real backend and production main.tscn; headless is sufficient for input
    # routing. --render runs the same journey with raw screenshot evidence.
    assert main(["--exercise-controls", "--sizes", "800x600", "--output", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "passed"
    assert report["runs"][0]["exercise_controls"] is True
    assert len(report["runs"][0]["workflow_checks"]) == 15
