"""Keep backend progression and Godot presentation at explicit boundaries.

These source-only tests are deliberately fast. The headless test runs only
when Godot is available and cannot certify physical MIDI latency.
"""
from pathlib import Path
import ast
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_practice_engine_delegates_start_and_progression_under_lock():
    server = (ROOT / "piano_teacher/server.py").read_text()
    source = ast.parse(server)
    engine = next(node for node in source.body
                  if isinstance(node, ast.ClassDef) and node.name == "PracticeEngine")
    methods = {node.name: node for node in engine.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for method in ("start", "_update"):
        segment = ast.get_source_segment(server, methods[method])
        assert "self.attempt_progression." in segment
        assert len(segment.splitlines()) < 22
    progression = (ROOT / "piano_teacher/application/attempt_progression.py").read_text()
    assert "def grid_for(" in progression
    assert "def begin(" in progression
    assert "def advance(" in progression
    assert "run_before_assessment(engine, now)" in progression
    assert "engine._apply_rolling_recovery(" in progression
    assert "engine._complete_attempt(" in progression


def test_main_callbacks_keep_reply_handling_and_presentation_separate():
    main = (ROOT / "godot/main.gd").read_text()
    process = main.split("func _process(", 1)[1].split("\nfunc ", 1)[0]
    state = main.split("func _on_state(", 1)[1].split("\nfunc ", 1)[0]
    assert "PracticeFrameCoordinator.advance(self, _delta)" in process
    assert "stage.renderer.present(" not in process
    assert "PracticeStatePresenter.present(self, parsed, sample_started_ms)" in state
    assert "score_session.update_context(" not in state
    frame = (ROOT / "godot/practice_frame_coordinator.gd").read_text()
    presenter = (ROOT / "godot/practice_state_presenter.gd").read_text()
    assert frame.count("app._transport_beat_now()") == 1
    assert "renderer.present(" in frame
    assert "demo_player.keep_synchronized(" in frame
    assert "app.visual_transport_clock.accept(" in presenter
    assert "app.score_session.update_context(" in presenter


@pytest.mark.skipif(not (shutil.which("godot") or shutil.which("godot4")),
                    reason="Godot is not installed")
def test_single_clock_sample_reaches_visual_consumers():
    binary = shutil.which("godot") or shutil.which("godot4")
    run = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/practice_frame_coordinator.gd")],
        capture_output=True, text=True, timeout=20)
    output = run.stdout + run.stderr
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "PRACTICE_FRAME_COORDINATOR_FAILURES:0" in output, output
