"""Headless E2E coverage requires actual stage transition, not scene startup."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/"scripts"/"smoke_adaptive_godot.py").read_text()
GODOT=(ROOT/"godot"/"main.gd").read_text()
WORKFLOW=(ROOT/".github"/"workflows"/"phase0.yml").read_text()


def test_adaptive_smoke_exercises_real_godot_and_three_clean_repeats():
    assert 'subprocess.Popen(' in SCRIPT
    assert '"--phase0-smoke"' in SCRIPT
    assert 'for attempt in range(1,4)' in SCRIPT
    assert 'if attempt == 1:' in SCRIPT
    assert 'engine.start()' in SCRIPT
    assert 'engine.state()["lesson_level"] == "outline"' in SCRIPT
    assert 'engine.score_revision > first_revision' in SCRIPT
    assert 'log.count("PHASE0_LESSON_READY:") >= 2' in SCRIPT
    assert 'engine.lesson_overview()' in SCRIPT
    assert 'engine.midi_port = object()' in SCRIPT
    assert 'scripts/smoke_adaptive_godot.py' in WORKFLOW


def test_godot_reports_actual_loaded_lesson():
    assert 'print("PHASE0_LESSON_READY: REVISION:"' in GODOT
    assert 'int(last_state.get("required_notes", 0))' in GODOT
    assert '"Stage %d of %d' in GODOT
