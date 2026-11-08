"""A native layout and its semantic fragments must describe the same revision."""
from pathlib import Path
import threading
import os
import shutil
import subprocess

import pytest

from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


def test_new_model_waits_for_current_revision_native_assets():
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 unavailable")
    proc = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_revision_readiness.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NATIVE_REVISION_READINESS_PASS" in proc.stdout


def test_native_preparation_stays_on_its_captured_revision_while_the_lesson_changes(tmp_path, monkeypatch):
    from piano_teacher.notation.assets import glyphs

    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.load(str(ROOT / "midi/Ala_–_Joep_Beving.midi"))
    revision = engine.score_revision
    entered = threading.Event()
    changed = threading.Event()
    real_symbols = glyphs.preparation_symbols

    def switch_hand():
        assert entered.wait(10)
        with engine.lock:
            engine.plan.set_hand("left")
            engine.score_revision += 1
        changed.set()

    def symbols_during_transition():
        # Preparation runs outside the engine lock (PracticeEngine.
        # _selected_artifacts), so a newer lesson may be selected meanwhile
        # and must not block on, nor leak into, the revision being prepared.
        entered.set()
        assert changed.wait(10), "A lesson change was blocked behind native asset preparation"
        return real_symbols()

    monkeypatch.setattr(glyphs, "preparation_symbols", symbols_during_transition)
    worker = threading.Thread(target=switch_hand)
    worker.start()
    try:
        layout = engine.geometry()
        assert "native_chord_templates" in layout
        assert layout["revision"] == revision
        assert engine.score_revision == revision + 1
    finally:
        entered.set()
        worker.join(timeout=10)
        engine.db.close()
    assert changed.is_set() and not worker.is_alive()
