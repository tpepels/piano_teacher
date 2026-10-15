"""Phase 6 diagnostic against the actual importer, engraver and PNG pipeline."""
from __future__ import annotations

import importlib.util
import json
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
