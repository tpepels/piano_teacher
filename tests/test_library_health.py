"""On-demand library import diagnostics, caching and queue isolation."""
from __future__ import annotations

import json
import time

import mido

from piano_teacher.server import PracticeEngine
from piano_teacher.inprocess import EngineCommands


def _midi(path, *, zero_note=False):
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    track.append(mido.Message("note_on", channel=0, note=60, velocity=90, time=0))
    track.append(mido.Message("note_off", channel=0, note=60, velocity=0, time=480))
    if zero_note:
        track.append(mido.Message("note_on", channel=0, note=63, velocity=90, time=0))
        track.append(mido.Message("note_off", channel=0, note=63, velocity=0, time=0))
    track.append(mido.MetaMessage("end_of_track", time=1440))
    mid.tracks.append(track)
    mid.save(path)


def _finished(checker):
    until = time.monotonic() + 12
    while time.monotonic() < until:
        status = checker.snapshot()
        if status["started"] and not status["running"]:
            return status
        time.sleep(.025)
    raise AssertionError(f"Library check did not finish: {checker.snapshot()}")


def test_real_import_health_and_repair_warning_without_modifying_files(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    _midi(music / "clean.mid")
    _midi(music / "repair.mid", zero_note=True)
    (music / "broken.mid").write_bytes(b"not a MIDI")
    before = {p.name: p.read_bytes() for p in music.iterdir()}
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.set_preferences(music_dir=str(music))
        assert not engine.library_health_status()["started"]
        engine.start_library_health()
        report = _finished(engine.library_health)
        assert (report["checked"], report["total"], report["ok"],
                report["warning"], report["error"]) == (3, 3, 1, 1, 1)
        assert report["items"]["clean.mid"]["notes"] == 1
        assert report["items"]["clean.mid"]["status"] == "ok"
        assert report["items"]["repair.mid"]["status"] == "warning"
        assert "zero-duration" in report["items"]["repair.mid"]["message"]
        assert report["items"]["broken.mid"]["status"] == "error"
        assert {p.name: p.read_bytes() for p in music.iterdir()} == before
    finally:
        engine.db.close()


def test_recheck_uses_unchanged_cache_and_invalidates_modified_file(tmp_path, monkeypatch):
    import piano_teacher.library_health as module
    music = tmp_path / "music"
    music.mkdir()
    file = music / "song.mid"
    _midi(file)
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.set_preferences(music_dir=str(music))
    original = module.import_piece
    count = [0]

    def counted(*args, **kwargs):
        count[0] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "import_piece", counted)
    try:
        engine.start_library_health()
        assert _finished(engine.library_health)["ok"] == 1
        engine.start_library_health()
        assert _finished(engine.library_health)["ok"] == 1
        assert count[0] == 1
        _midi(file, zero_note=True)
        engine.start_library_health()
        assert _finished(engine.library_health)["warning"] == 1
        assert count[0] == 2
    finally:
        engine.db.close()


def test_folder_switch_clears_previous_health_and_ignores_symlinks(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _midi(a / "first.mid")
    _midi(b / "second.mid")
    (b / "link.mid").symlink_to(a / "first.mid")
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.set_preferences(music_dir=str(a))
        engine.start_library_health()
        assert "first.mid" in _finished(engine.library_health)["items"]
        engine.set_preferences(music_dir=str(b))
        assert not engine.library_health_status()["started"]
        engine.start_library_health()
        check = _finished(engine.library_health)
        assert list(check["items"]) == ["second.mid"]
        assert check["total"] == 1
    finally:
        engine.db.close()


def test_queue_health_start_is_nonblocking_and_does_not_load_a_piece(tmp_path):
    music = tmp_path / "music"
    music.mkdir()
    _midi(music / "study.mid")
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    commands = EngineCommands(engine=engine)
    engine.set_preferences(music_dir=str(music))
    try:
        status, body = commands.request("GET", "/library/health")
        assert status == 200 and json.loads(body)["started"] is False
        status, body = commands.request("POST", "/library/health", "{}")
        assert status == 200 and json.loads(body)["started"] is True
        result = _finished(engine.library_health)
        assert result["ok"] == 1
        assert engine.plan is None
        status, body = commands.request("GET", "/library/health")
        assert status == 200
        assert json.loads(body)["items"]["study.mid"]["notes"] == 1
    finally:
        engine.db.close()
