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


def test_native_preparation_keeps_revision_locked_until_assets_are_bound(tmp_path, monkeypatch):
    from piano_teacher import notation_symbols

    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.load(str(ROOT / "midi/Ala_–_Joep_Beving.midi"))
    revision = engine.score_revision
    entered = threading.Event()
    changed = threading.Event()
    real_symbols = notation_symbols.preparation_symbols

    def switch_hand():
        assert entered.wait(10)
        with engine.lock:
            engine.plan.set_hand("left")
            engine.score_revision += 1
        changed.set()

    def symbols_during_transition():
        entered.set()
        assert not changed.wait(.1), "A newer lesson replaced the source before fragments were bound"
        return real_symbols()

    monkeypatch.setattr(notation_symbols, "preparation_symbols", symbols_during_transition)
    worker = threading.Thread(target=switch_hand)
    worker.start()
    try:
        layout = engine.geometry(native_notes=True)
        assert "native_chord_templates" in layout
        assert layout["revision"] == revision
    finally:
        entered.set()
        worker.join(timeout=10)
        engine.db.close()
    assert changed.is_set() and not worker.is_alive()
