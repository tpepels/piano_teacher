"""Bundled studies are complete playable MIDI files, not library placeholders."""
import io
import json

import mido
import pytest

from piano_teacher.library import ScoreLibrary
from piano_teacher.music import load_midi
from piano_teacher.warmups import PREFIX, WARMUPS, catalog, is_warmup, materialize, render_midi


def test_catalog_contains_all_six_with_meaningful_focus():
    entries = catalog()
    assert len(entries) == len(WARMUPS) == 6
    assert len({entry["id"] for entry in entries}) == 6
    assert {w.slug for w in WARMUPS} == {
        "chords", "finger-patterns", "classical-melody", "pop-accompaniment",
        "jazz-voicings", "jazz-phrasing"}
    for item in entries:
        assert item["id"].startswith(PREFIX)
        assert item["title"] and item["description"] and item["focus"]
        assert item["bars"] == 8 and 40 <= item["bpm"] <= 100


@pytest.mark.parametrize("warmup", WARMUPS, ids=lambda w: w.slug)
def test_builtin_midi_is_deterministic_and_importable(warmup, tmp_path):
    data = render_midi(warmup.slug)
    assert data == render_midi(warmup.slug)
    midi = mido.MidiFile(file=io.BytesIO(data))
    assert midi.type == 1 and midi.ticks_per_beat == 480
    assert len(midi.tracks) == 3
    assert [next(message.name for message in track if message.type == "track_name")
            for track in midi.tracks[1:]] == ["Right Hand", "Left Hand"]
    timing = midi.tracks[0]
    meter = next(message for message in timing if message.type == "time_signature")
    assert (meter.numerator, meter.denominator) == warmup.meter
    assert round(mido.tempo2bpm(next(msg.tempo for msg in timing
                                      if msg.type == "set_tempo"))) == warmup.bpm
    for track in midi.tracks[1:]:
        attacks = sum(msg.type == "note_on" and msg.velocity > 0 for msg in track)
        releases = sum(msg.type == "note_off" for msg in track)
        assert attacks >= 8 and attacks == releases
        assert all(msg.time >= 0 for msg in track)
    source = materialize(PREFIX + warmup.slug, tmp_path / "builtins")
    assert source.read_bytes() == data
    assert materialize(PREFIX + warmup.slug, tmp_path / "builtins") == source
    piece = load_midi(source)
    assert piece.bpm == warmup.bpm
    assert {note.hand for note in piece.notes} == {"right", "left"}
    assert len(piece.bar_boundaries) == warmup.bars + 1
    assert piece.time_signatures[0] == (0.0, *warmup.meter)
    assert all(0 <= note.start < note.end <= piece.bar_boundaries[-1]
               for note in piece.notes)


def test_styles_contain_real_syncopation_and_swing(tmp_path):
    swing = load_midi(materialize(PREFIX + "jazz-phrasing", tmp_path))
    assert any(abs(n.start % 1 - 2/3) < 0.00001 for n in swing.notes)
    pop = load_midi(materialize(PREFIX + "pop-accompaniment", tmp_path))
    assert any(n.hand == "right" and n.start % 1 == .5 for n in pop.notes)
    ladders = load_midi(materialize(PREFIX + "finger-patterns", tmp_path))
    assert sum(n.hand == "right" for n in ladders.notes) == 64


def test_warmups_survive_missing_folder_and_retain_recent_selection(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.json").write_text(json.dumps({"music_dir": str(tmp_path / "missing")}))
    lib = ScoreLibrary(config_dir=cfg)
    listing = lib.scan()
    assert listing["count"] == 0 and len(listing["warmups"]) == 6
    assert "error" in listing
    assert not (tmp_path / "missing").exists()
    selected = PREFIX + "chords"
    path = lib.resolve(selected)
    assert path.is_file() and path.parent == cfg / "warmups"
    lib.mark_opened(selected)
    assert lib.scan()["last_piece"] == selected
    new_music = tmp_path / "new"
    new_music.mkdir()
    lib.update(music_dir=str(new_music))
    assert lib.scan()["last_piece"] == selected
    for invalid in ("warmup:../chords", "warmup:unknown", "warmup:chords/../private"):
        assert not is_warmup(invalid)
        with pytest.raises(ValueError):
            lib.resolve(invalid)


def test_open_builtin_starts_at_full_perform_without_adaptive_stages(tmp_path):
    pytest.importorskip("music21")
    from piano_teacher.server import PracticeEngine
    engine = PracticeEngine(tmp_path / "state", enable_midi=False)
    try:
        engine.load_library(PREFIX + "chords")
        assert engine.is_builtin_warmup
        assert engine.mode == "perform"
        assert engine.plan.exercise.kind == "perform"
        assert engine.plan.bpm == engine.plan.target_bpm == 68
        assert engine.plan.active_phrase.notes == engine.plan.piece.notes
        assert engine.library_listing()["last_piece"] == PREFIX + "chords"
        engine.control("start")
        assert engine.preview_only and engine.mode == "perform"
        engine.control("stop")
        engine.control("start")
        assert engine.mode == "perform"
        engine.control("stop")
    finally:
        engine.db.close()


@pytest.mark.parametrize("warmup", WARMUPS, ids=lambda w: w.slug)
def test_real_engraving_covers_required_warmup_notes(tmp_path, warmup):
    pytest.importorskip("music21")
    pytest.importorskip("verovio")
    from piano_teacher.server import PracticeEngine
    from piano_teacher.lesson_validation import require_lesson_alignment
    engine = PracticeEngine(tmp_path / warmup.slug, enable_midi=False)
    try:
        engine.load_library(PREFIX + warmup.slug)
        engraved = engine.engraving()
        require_lesson_alignment(engine.plan.active_phrase, engraved.layout, "both")
        assert engraved.pages
        assert len(engraved.layout["notes"]) >= len(engine.plan.active_phrase.notes)
        assert engine.engraved_png(0).startswith(b"\x89PNG")
    finally:
        engine.db.close()
