"""Malformed saved preference values cannot break startup or MIDI timing."""
from __future__ import annotations

import json

import pytest

from piano_teacher.library import ScoreLibrary, default_music_dir


@pytest.mark.parametrize("saved_folder", ["", "   ", "regular-file"])
def test_invalid_saved_music_folder_uses_first_run_default(tmp_path, saved_folder):
    if saved_folder == "regular-file":
        file = tmp_path / "not-a-folder"
        file.write_text("ordinary file")
        saved_folder = str(file)
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"music_dir": saved_folder}))

    library = ScoreLibrary(tmp_path)

    assert library.public_settings()["music_dir"] == str(
        default_music_dir().resolve())
    assert isinstance(library.scan()["pieces"], list)


@pytest.mark.parametrize("offset", [-1, 251, True])
def test_invalid_saved_midi_offset_uses_uncalibrated_default(tmp_path, offset):
    (tmp_path / "settings.json").write_text(
        json.dumps({"midi_offset_ms": offset}))

    library = ScoreLibrary(tmp_path)

    assert type(library.public_settings()["midi_offset_ms"]) is int
    assert library.public_settings()["midi_offset_ms"] == 0
    with pytest.raises(ValueError, match="0–250"):
        library.update(midi_offset_ms=offset)


@pytest.mark.parametrize("offset", [0, 250])
def test_valid_saved_midi_offset_boundaries_remain_selected(tmp_path, offset):
    (tmp_path / "settings.json").write_text(
        json.dumps({"midi_offset_ms": offset}))

    assert ScoreLibrary(tmp_path).public_settings()["midi_offset_ms"] == offset
