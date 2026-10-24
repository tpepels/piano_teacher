"""Phase 6 diagnostic against the actual importer, engraver and PNG pipeline."""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "musical_fidelity"
SPEC = importlib.util.spec_from_file_location(
    "verify_library_pipeline", ROOT / "scripts" / "verify_library_pipeline.py")
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


@pytest.mark.parametrize("filename", [
    "midi_mixed_meter.mid",
    "xml_pickup.musicxml",
])
def test_true_start_middle_end_navigation_and_raster(filename, tmp_path):
    # Runs the production engine, actual source-note mapping and Verovio
    # rasterizer. Fake PNGs and synthetic layout objects cannot pass.
    result = diagnostic.check_one(FIXTURES / filename, tmp_path / "evidence", godot=None)
    assert result["status"] == "pass"
    assert result["source_notes"] > 0
    assert len(result["samples"]) >= 2
    for item in result["samples"]:
        manifest = json.loads((tmp_path / "evidence" / item["manifest"]).read_text())
        assert manifest["measure"] == item["selected"]
        assert manifest["layout"]["notes"]
        assert item["pages"] >= 1
        for filename in manifest["pages"]:
            assert (tmp_path / "evidence" / filename).read_bytes().startswith(
                bytes.fromhex("89504e470d0a1a0a"))


def test_broken_library_entry_does_not_prevent_next_file(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    (music / "a-broken.mid").write_bytes(b"not a MIDI file")
    (music / "b-valid.mid").write_bytes((FIXTURES / "midi_four_four.mid").read_bytes())
    report = diagnostic.run_library(music, tmp_path / "results", timeout=120)
    assert report["completed"] == 2
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["results"][0]["status"] == "fail"
    assert report["results"][1]["status"] == "pass"
    stored = json.loads((tmp_path / "results" / "report.json").read_text())
    assert stored["results"][0]["stage_error"]
    assert stored["results"][1]["samples"]


def test_sample_bars_selects_real_attacks_instead_of_timeline_fractions():
    from piano_teacher.music import Note, Piece
    # A sparse file: long stretches of rests should not become a
    # pointless diagnostic of empty measures.
    class Sparse:
        bar_boundaries = [float(4*i) for i in range(101)]
        notes = [
            Note(0, 1, 60, 0, 0, "right"),
            Note(200, 202, 64, 0, 0, "right"),
            Note(388, 390, 67, 0, 0, "right"),
        ]
    assert diagnostic.sample_bars(Sparse()) == [1, 51, 98]


def test_source_raster_diagnostic_does_not_require_native_preparation(tmp_path, monkeypatch):
    from piano_teacher.server import PracticeEngine

    geometry = PracticeEngine.geometry

    def reference_geometry(self, *, native_notes=True):
        assert native_notes is False, "Source raster checks must not depend on native assets"
        return geometry(self, native_notes=False)

    def unexpected_native_model(self):
        pytest.fail("Source-only diagnostics must not prepare a native model")

    monkeypatch.setattr(PracticeEngine, "geometry", reference_geometry)
    monkeypatch.setattr(PracticeEngine, "semantic_score", unexpected_native_model)
    result = diagnostic.check_one(FIXTURES / "xml_pickup.musicxml", tmp_path, godot=None)
    assert result["status"] == "pass"
    assert result["samples"]


@pytest.mark.parametrize("filename", ["midi_mixed_meter.mid", "xml_pickup.musicxml"])
def test_godot_diagnostic_prepares_and_displays_each_native_sample(filename, tmp_path):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    result = diagnostic.check_one(FIXTURES / filename, tmp_path, godot=binary)
    report = json.loads((tmp_path / "native-library-report.json").read_text())
    assert len(report["samples"]) == len(result["samples"])
    for sample, observed in zip(result["samples"], report["samples"]):
        manifest = json.loads((tmp_path / sample["manifest"]).read_text())
        payload = json.loads((tmp_path / manifest["native_fixture"] / "native.json").read_text())
        assert payload["layout"]["native_glyphs"]
        assert payload["layout"]["native_note_templates"]
        assert payload["layout"]["revision"] == payload["model"]["revision"]
        source_ids = {note["id"] for note in payload["model"]["notes"]}
        assert observed["measure"] == sample["selected"]
        assert observed["ready"] is True
        assert set(observed["source_ids"]) == source_ids
        assert observed["displayed_source_ids"]
        assert set(observed["displayed_source_ids"]) <= source_ids
        assert set(observed["feedback_source_ids"]) == source_ids

    # Genuine assets are required by the production handlers, even if all
    # source PNGs still exist and the semantic model remains valid.
    manifest = json.loads((tmp_path / result["samples"][0]["manifest"]).read_text())
    native = tmp_path / manifest["native_fixture"] / "native.json"
    payload = json.loads(native.read_text())
    payload["layout"]["native_glyphs"] = {}
    native.write_text(json.dumps(payload))
    run = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/native_library_diagnostic.gd"), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=50)
    assert run.returncode != 0, run.stdout + run.stderr
    assert "PHASE6_GODOT_PASS" not in run.stdout
