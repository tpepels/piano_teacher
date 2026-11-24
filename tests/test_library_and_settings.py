"""Choosing music and saving settings must preserve a usable lesson."""
import json
import time

import mido
import pytest

from session_inputs import PracticeSession

from piano_teacher import sample_piano
from piano_teacher.inprocess import EngineCommands, FAILED, INVALID, OK
from piano_teacher.library import ScoreLibrary, default_music_dir
from piano_teacher.server import PracticeEngine


def request(commands, operation, **payload):
    status, body = commands.request(operation, json.dumps(payload) if payload else "")
    return status, json.loads(body)


@pytest.fixture
def library(tmp_path):
    music = tmp_path / "My music"
    (music / "Etudes").mkdir(parents=True)
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", note=60, velocity=80),
        mido.Message("note_off", note=60, time=480),
    ]))
    midi.save(music / "Prelude.mid")
    midi.save(music / "Etudes" / "Study.midi")
    (music / "notes.txt").write_text("ignore")
    (music / ".drafts").mkdir()
    midi.save(music / ".drafts" / "hidden.mid")
    lib = ScoreLibrary(tmp_path / "config")
    lib.update(music_dir=str(music))
    return lib, music


def test_library_recurses_and_cannot_open_outside_the_selected_folder(library, tmp_path):
    lib, music = library
    outside = tmp_path / "private.mid"
    outside.write_bytes(b"private")
    (music / "linked.mid").symlink_to(outside)
    assert {p["id"] for p in lib.scan()["pieces"]} == {"Prelude.mid", "Etudes/Study.midi"}
    assert lib.resolve("Etudes/Study.midi") == music / "Etudes" / "Study.midi"
    for selected in ("../private.mid", str(outside), "linked.mid", "notes.txt"):
        with pytest.raises(ValueError):
            lib.resolve(selected)


def test_actual_library_open_and_bad_commands_leave_next_open_usable(library, tmp_path, monkeypatch):
    _, music = library
    monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
    monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", tmp_path / "absent.sf2")
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    commands = EngineCommands(engine=engine)
    try:
        assert request(commands, "settings.update", music_dir=str(music))[0] == OK
        assert request(commands, "library.open", id="../private.mid")[0] == INVALID
        (music / "Broken.mid").write_bytes(b"broken MIDI")
        assert request(commands, "library.open", id="Broken.mid")[0] in (INVALID, FAILED)
        assert request(commands, "library.open", id="Prelude.mid")[0] == OK
        state = engine.state()
        assert state["loaded"] and state["title"] == "Prelude"
        assert engine.library_listing()["last_piece"] == "Prelude.mid"
        assert commands.request("library.open", "{bad")[0] == INVALID
        assert request(commands, "library.catalog")[0] == OK
    finally:
        engine.close()


def test_folder_change_resets_recent_and_persists_selected_preferences(library, tmp_path):
    lib, _ = library
    lib.mark_opened("Prelude.mid")
    lib.update(fullscreen=False, metronome=False, midi_device="USB Piano",
               grade_note_holds=True)
    reopened = ScoreLibrary(lib.settings_path.parent)
    assert reopened.scan()["last_piece"] == "Prelude.mid"
    assert reopened.public_settings()["midi_device"] == "USB Piano"
    assert reopened.public_settings()["fullscreen"] is False
    assert reopened.public_settings()["grade_note_holds"] is True
    empty = tmp_path / "empty"
    empty.mkdir()
    reopened.update(music_dir=str(empty))
    again = ScoreLibrary(lib.settings_path.parent)
    assert again.scan()["last_piece"] == "" and again.scan()["count"] == 0
    assert again.public_settings()["metronome"] is False
    assert again.public_settings()["grade_note_holds"] is True


def test_malformed_saved_values_and_retired_course_migrate_without_losing_preferences(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({
        "music_dir": " ", "midi_offset_ms": True, "metronome": False,
        "exercise_strategy": "source-progression", "timing_strategy": "dotted-long-short",
        "tempo_strategy": "two-phase-tempo", "last_piece": "old.pdf",
    }))
    lib = ScoreLibrary(tmp_path)
    settings = lib.public_settings()
    assert settings["music_dir"] == str(default_music_dir().resolve())
    assert settings["midi_offset_ms"] == 0 and settings["metronome"] is False
    assert "exercise_strategy" not in settings
    assert settings["grade_note_holds"] is False
    assert lib.scan()["last_piece"] == ""
    saved = json.loads(lib.settings_path.read_text())
    assert not {"exercise_strategy", "timing_strategy", "tempo_strategy"} & saved.keys()


def test_missing_library_folder_is_actionable_and_can_be_replaced(tmp_path):
    (tmp_path / "settings.json").write_text(json.dumps({"music_dir": str(tmp_path / "gone")}))
    lib = ScoreLibrary(tmp_path)
    assert lib.scan()["count"] == 0 and lib.scan()["error"]
    replacement = tmp_path / "new"
    replacement.mkdir()
    lib.update(music_dir=str(replacement))
    assert not lib.scan().get("error")


def test_rejected_and_failed_saves_preserve_live_and_saved_settings(library, monkeypatch):
    lib, _ = library
    before = lib.public_settings()
    disk = lib.settings_path.read_bytes()
    for updates in ({"midi_offset_ms": 251}, {"fullscreen": "yes"},
                    {"exercise_strategy": "retired"}):
        with pytest.raises(ValueError):
            lib.update(**updates)
    assert lib.public_settings() == before
    assert lib.settings_path.read_bytes() == disk

    def disk_full(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(lib, "save", disk_full)
    with pytest.raises(OSError, match="disk full"):
        lib.update(metronome=False)
    assert lib.public_settings() == before
    assert lib.settings_path.read_bytes() == disk


def test_invalid_command_or_failed_preference_save_preserves_running_lesson(library, tmp_path, monkeypatch):
    _, music = library
    monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
    monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", tmp_path / "absent.sf2")
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    try:
        engine.set_preferences(music_dir=str(music))
        engine.load_library("Prelude.mid")
        PracticeSession.attach(engine, engine.now).start_listen()
        before = engine.state()
        preferences = engine.preferences()
        disk = (tmp_path / "app" / "config" / "settings.json").read_bytes()
        commands = EngineCommands(engine=engine)
        assert request(commands, "practice.command", action="tempo", bpm=0)[0] == INVALID
        assert request(commands, "settings.update", exercise_strategy="retired")[0] == INVALID

        def disk_full(**kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(engine.library, "save", disk_full)
        with pytest.raises(OSError, match="disk full"):
            engine.set_preferences(metronome=not preferences["metronome"])
        assert engine.preferences() == preferences
        assert (tmp_path / "app" / "config" / "settings.json").read_bytes() == disk
        after = engine.state()
        assert after["running"]
        assert after["transport_id"] == before["transport_id"]
        assert after["title"] == before["title"] and after["bpm"] == before["bpm"]
    finally:
        engine.close()


def test_library_health_finds_bad_music_then_recovers_without_changing_the_lesson(practice_session):
    session = practice_session(bars=1)
    damaged = session.music/"broken.mid"
    damaged.write_bytes(b"not a MIDI file")
    original = session.path.read_bytes()
    selected = session.snapshot()

    def health():
        session.ask("library.health.start")
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            result = session.ask("library.health_status")
            if not result["running"]:
                return result
            time.sleep(.005)
        raise AssertionError("Library health did not finish")

    checked = health()
    assert checked["checked"] == checked["total"] == 2
    assert checked["ok"] == 1 and checked["error"] == 1
    assert checked["items"][damaged.name]["status"] == "error"
    assert checked["items"][damaged.name]["message"]
    assert session.snapshot()["revision"] == selected["revision"]
    assert session.path.read_bytes() == original
    damaged.write_bytes(original)
    repaired = health()
    assert repaired["ok"] == 2 and repaired["error"] == 0
    empty = session.music/"empty"
    empty.mkdir()
    session.ask("settings.update", music_dir=str(empty))
    assert session.ask("library.health_status")["checked"] == 0
    assert health()["total"] == 0
