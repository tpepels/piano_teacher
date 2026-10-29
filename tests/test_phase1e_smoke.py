"""Headless E2E coverage requires actual stage transition, not scene startup."""
from pathlib import Path
import pytest
from test_phase1_camera import native_camera_run

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/"scripts"/"smoke_adaptive_godot.py").read_text()
GODOT=(ROOT/"godot"/"main.gd").read_text()
WORKFLOW=(ROOT/".github"/"workflows"/"native-notation.yml").read_text()


def test_adaptive_smoke_exercises_real_godot_and_three_clean_repeats():
    assert 'subprocess.Popen(' in SCRIPT
    assert '"--phase0-smoke"' in SCRIPT
    assert 'for attempt in range(1,4)' in SCRIPT
    assert 'if attempt == 1:' in SCRIPT
    assert 'engine.start()' in SCRIPT
    assert 'engine.state()["lesson_level"] == "outline"' in SCRIPT
    assert 'engine.score_revision > first_revision' in SCRIPT
    assert 'lesson_rendered(log, first_revision)' in SCRIPT
    assert 'lesson_rendered(log, next_revision)' in SCRIPT
    assert 'engine.lesson_overview()' in SCRIPT
    assert 'engine.midi.port = object()' in SCRIPT
    # The historical phase0 push workflow was replaced by a bounded smoke
    # gate; adaptive graphical journeys remain explicit local checks.
    assert 'scripts/ci-smoke.sh' in WORKFLOW
    assert 'scripts/smoke_adaptive_godot.py' not in WORKFLOW


def test_godot_reports_actual_loaded_native_lesson(native_camera_run):
    from scripts.smoke_adaptive_godot import lesson_rendered

    report, output = native_camera_run
    assert report["native_ready"]
    # Feed actual production markers to the acceptance consumer, rather
    # than testing a hand-written marker the app no longer emits.
    import re
    revision = int(re.search(r"NATIVE_MODEL_READY:\s*(\d+)", output)[1])
    assert lesson_rendered(output, revision), output
    assert not lesson_rendered(output, revision + 1)


def test_adaptive_smoke_requires_matching_native_model_and_assets():
    from scripts.smoke_adaptive_godot import lesson_rendered

    assert not lesson_rendered("PHASE0_LESSON_READY: REVISION:2", 2)
    assert not lesson_rendered("PHASE0_SCORE_READY_NATIVE: REVISION:2", 2)
    assert lesson_rendered(
        "PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
        "NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0", 2)
    assert not lesson_rendered(
        "PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
        "NATIVE_MODEL_READY: 1 NOTES: 8 DENSITY: 96.0", 2)


@pytest.mark.parametrize("log, revision, expected", [
    ("PHASE0_LESSON_READY: REVISION:2", 2, False),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
     "PHASE_B_MODEL_READY: 2 NOTES: 8", 2, False),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:20\n"
     "NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0", 2, False),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
     "NATIVE_MODEL_READY: 20 NOTES: 8 DENSITY: 96.0", 2, False),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:2extra\n"
     "NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0", 2, False),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
     "NATIVE_MODEL_READY: 2extra NOTES: 8 DENSITY: 96.0", 2, False),
    ("NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0", 2, False),
    ("NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0\r\n"
     "PHASE0_SCORE_READY_NATIVE: REVISION:2\r\n", 2, True),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:20\n"
     "NATIVE_MODEL_READY: 20 NOTES: 8 DENSITY: 96.0", 20, True),
    ("PHASE0_SCORE_READY_NATIVE: REVISION:2\n"
     "NATIVE_MODEL_READY: 2 NOTES: 8 DENSITY: 96.0\n"
     "PHASE0_SCORE_READY_NATIVE: REVISION:3", 3, False),
])
def test_lesson_rendered_accepts_only_exact_native_revision(log, revision, expected):
    from scripts.smoke_adaptive_godot import lesson_rendered

    assert lesson_rendered(log, revision) is expected
