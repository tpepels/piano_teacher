"""Native is the public layout contract; reference engraving is explicit."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from piano_teacher.application.score_preparation import assemble_layout
from piano_teacher.server import Handler, PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native_engine(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.load(str(ROOT / "tests/fixtures/native_pixel_pitch_probe.musicxml"))
    try:
        yield engine
    finally:
        engine.db.close()


def test_default_geometry_has_authentic_native_assets_and_matching_model(native_engine):
    layout = native_engine.geometry()
    model = native_engine.semantic_score()
    assert layout["revision"] == model["revision"]
    assert layout.get("native_note_templates"), "Default geometry omitted native note assets"
    assert layout.get("native_tie_templates"), "Default geometry omitted native tie assets"
    assert layout["native_beams_complete"] and layout["native_slurs_complete"]
    assert {n["id"] for n in model["notation_events"] if n["kind"] == "note"} == {
        n["id"] for n in layout["notes"]}


def test_reference_geometry_remains_explicit_and_preserves_original_engraving(native_engine):
    source = native_engine.engraving()
    reference = native_engine.geometry(native_notes=False)
    assert reference["notes"] == source.layout["notes"]
    assert reference["anchors"] == source.layout["anchors"]
    assert "native_note_templates" not in reference
    assert native_engine.engraving().pages == source.pages


def test_default_assembly_requires_selected_model_and_xml(native_engine):
    source = native_engine.engraving()
    with pytest.raises(ValueError, match="model and MusicXML"):
        assemble_layout(source)
    with pytest.raises(ValueError, match="model and MusicXML"):
        assemble_layout(source, native_model=native_engine.semantic_score())
    assert assemble_layout(source, native_notes=False)["notes"] == source.layout["notes"]


def test_native_preparation_failure_never_returns_reference_layout(native_engine, monkeypatch):
    from piano_teacher.notation.assets import notes

    def unavailable(_cache):
        raise RuntimeError("Authenticated source notes unavailable")

    monkeypatch.setattr(notes, "note_templates", unavailable)
    with pytest.raises(RuntimeError, match="source notes unavailable"):
        native_engine.geometry()
    assert native_engine.geometry(native_notes=False)["anchors"]


def test_http_layout_defaults_native_and_reference_requires_explicit_false(native_engine):
    class LocalHandler(Handler):
        engine = native_engine

    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for query in ("", "?native=1"):
            with urlopen(base + "/score/layout" + query, timeout=15) as response:
                layout = json.load(response)
            assert layout.get("native_note_templates"), "Public layout silently selected reference-only assets"
        with urlopen(base + "/score/layout?native=0", timeout=15) as response:
            reference = json.load(response)
        assert "native_note_templates" not in reference and reference["notes"]
        with pytest.raises(HTTPError) as rejected:
            urlopen(base + "/score/layout?native=legacy", timeout=15)
        assert rejected.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
