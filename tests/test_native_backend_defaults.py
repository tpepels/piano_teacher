"""Native is the sole public score layout through typed in-process operations."""
import json
from pathlib import Path

import pytest

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.inprocess import EngineCommands, OK, INVALID
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native_engine(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.load(str(ROOT / "tests/fixtures/musical_fidelity/midi_four_four.mid"))
    try:
        yield engine
    finally:
        engine.db.close()


def test_default_geometry_has_authentic_native_assets_and_matching_model(native_engine):
    layout = native_engine.geometry()
    model = native_engine.semantic_score()
    assert layout["revision"] == model["revision"]
    assert layout["native_note_templates"] and layout["native_tie_templates"]
    assert layout["native_beams_complete"] and layout["native_slurs_complete"]
    assert {n["id"] for n in model["notation_events"] if n["kind"] == "note"} == {
        n["id"] for n in layout["notes"]}


def test_assembly_requires_selected_model_and_xml(native_engine):
    with pytest.raises(ValueError, match="selected notation and semantic model"):
        assemble_layout(native_engine.engraving(), native_model=None, notation_xml="")


def test_typed_layout_publishes_native_assets_and_matching_revision(native_engine):
    commands = EngineCommands(engine=native_engine)
    status, body = commands.request("score.native_layout", "")
    assert status == OK
    layout = json.loads(body)
    status, body = commands.request("score.semantic", "")
    assert status == OK
    model = json.loads(body)
    assert layout["native_note_templates"] and layout["native_glyphs"]
    assert layout["revision"] == model["revision"] == native_engine.score_revision


def test_native_preparation_failure_is_explicit_and_does_not_cache_partial_layout(
        native_engine, monkeypatch):
    from piano_teacher.notation.assets import notes

    def unavailable(_cache):
        raise RuntimeError("Authenticated source notes unavailable")

    monkeypatch.setattr(notes, "note_templates", unavailable)
    status, body = EngineCommands(engine=native_engine).request("score.native_layout", "")
    assert status == INVALID and "source notes unavailable" in json.loads(body)["error"]
    monkeypatch.undo()
    recovered = native_engine.geometry()
    assert recovered["native_note_templates"] and recovered["native_glyphs"]
