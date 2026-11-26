"""Generate an authentic score bundle for Godot player-behaviour scenarios."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from session_inputs import write_midi
from piano_teacher.server import PracticeEngine

with TemporaryDirectory() as temp:
    directory = Path(temp)
    source = write_midi(directory / "readiness.mid", bars=2, chords=True)
    engine = PracticeEngine(directory / "learner", enable_midi=False)
    try:
        engine.load(str(source))
        bundle = engine.score_bundle()
        assert bundle["status"] == "ready", bundle.get("error")
        Path(sys.argv[1]).write_text(json.dumps(bundle), encoding="utf-8")
    finally:
        engine.close()
