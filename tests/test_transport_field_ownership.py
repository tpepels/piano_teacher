"""The engine does not alias mutable transport state on its public API."""
from pathlib import Path

from piano_teacher.server import PracticeEngine
from piano_teacher.visual_transport import VisualTransport

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "run_at", "play_from_beat", "pending_rewind", "paused", "paused_at",
    "next_at", "visual_offset_beats", "_preview_loop_pending",
    "_visual_rewind_from", "_visual_rewind_to", "_visual_rewind_at",
    "_visual_rewind_seconds", "_retry_previous_pass",
    "practice_preparation", "_preparation_pending", "_preparation_at",
    "visual_gap_beats",
)


def test_one_mutable_transport_owner_without_engine_aliases():
    source = (ROOT / "piano_teacher/server.py").read_text()
    transport = (ROOT / "piano_teacher/visual_transport.py").read_text()
    assert "TransportField" not in source + transport
    assert "class TransportField" not in transport
    for name in NAMES:
        assert name not in vars(PracticeEngine), name
        assert name in vars(VisualTransport)["__dataclass_fields__"], name
        assert ("self." + name) not in source, name
    assert "self.visual_transport.run_at" in source
