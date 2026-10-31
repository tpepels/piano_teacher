"""Fast Phase 0 checks; real Verovio rendering runs in the Arch smoke job."""
from pathlib import Path
import sys
import time
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_phase0 import make_fixture


def test_generated_two_hand_midi_fixture(tmp_path):
    file = tmp_path / "fixture.mid"
    make_fixture(file)
    piece = load_midi(file)
    assert piece.bpm == 120
    assert len(piece.notes) == 16
    assert {n.hand for n in piece.notes} == {"right", "left"}
    assert len(piece.phrases) == 1
    assert piece.phrases[0].first_bar == 1
    assert piece.phrases[0].last_bar == 2


def test_no_midi_mode_cannot_award_mastery(tmp_path):
    file = tmp_path / "fixture.mid"
    make_fixture(file)
    engine = PracticeEngine(tmp_path / "db", enable_midi=False)
    engine.plan = LearningPlan(load_midi(file))
    try:
        engine.start()
        assert engine.state()["preview_only"]
        engine.run_at = time.monotonic() - .25
        assert engine.state()["phase"] == "playing"
        engine.run_at = time.monotonic() - 50
        result = engine.state()
        assert not result["running"]
        assert result["mastered"] == 0
        assert engine.plan.failures == 0
    finally:
        engine.db.close()


def test_native_launcher_is_executable_and_contains_no_server():
    content = (ROOT / "run.sh").read_text()
    assert '127.0.0.1' not in content
    assert "PianoNative" not in content  # verified by native preflight
    assert (ROOT / "run.sh").stat().st_mode & 0o111
