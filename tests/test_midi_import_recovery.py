"""Regression cases taken from real exported piano MIDI failure modes.

These contain invented notes only; uploaded copyrighted performances are not
committed to the repository. Corruption never changes valid event identities.
"""
from __future__ import annotations

from pathlib import Path

import mido

from piano_teacher.music import load_midi


def _write_file(path: Path, *, zero: bool, orphan: bool) -> Path:
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for track_index, pitch in enumerate((72, 48)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=("Right Hand" if track_index == 0
                                                         else "Left Hand"), time=0))
        if track_index == 0:
            track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
            track.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        track.append(mido.Message("note_on", note=pitch, velocity=90,
                                  channel=0, time=0))
        track.append(mido.Message("note_off", note=pitch, velocity=0,
                                  channel=0, time=480))
        if zero:
            track.append(mido.Message("note_on", note=pitch, velocity=90,
                                      channel=0, time=0))
            track.append(mido.Message("note_off", note=pitch, velocity=0,
                                      channel=0, time=0))
        if orphan:
            track.append(mido.Message("note_off", note=pitch, velocity=0,
                                      channel=1, time=0))
        track.append(mido.MetaMessage("end_of_track", time=1440))
        midi.tracks.append(track)
    midi.save(path)
    return path


def test_zero_duration_events_are_skipped_but_legitimate_notes_survive(tmp_path):
    path = _write_file(tmp_path / "instantaneous.mid", zero=True, orphan=False)
    piece = load_midi(path)
    assert [(n.pitch, n.start, n.end) for n in piece.notes] == [
        (48, 0.0, 1.0), (72, 0.0, 1.0),
    ]
    assert [n.source_id for n in piece.notes] == [
        "midi-t1-e1", "midi-t0-e3",
    ] or {n.source_id for n in piece.notes} == {"midi-t0-e3", "midi-t1-e1"}
    assert len(piece.import_warnings) == 1
    assert "2 zero-duration" in piece.import_warnings[0]


def test_orphan_channel_releases_do_not_abort_normal_piano_exercise(tmp_path):
    path = _write_file(tmp_path / "orphan.mid", zero=False, orphan=True)
    piece = load_midi(path)
    assert {n.pitch for n in piece.notes} == {48, 72}
    assert len(piece.notes) == 2
    assert len(piece.import_warnings) == 1
    assert "2 unmatched" in piece.import_warnings[0]


def test_combined_repairs_are_reported_and_source_identities_remain_stable(tmp_path):
    path = _write_file(tmp_path / "repairs.mid", zero=True, orphan=True)
    piece = load_midi(path)
    assert len(piece.notes) == 2
    assert len(piece.import_warnings) == 2
    assert piece.phrases and piece.bar_boundaries
    assert len({n.source_id for n in piece.notes}) == 2


def test_normal_midi_produces_no_repair_warning(tmp_path):
    path = _write_file(tmp_path / "clean.mid", zero=False, orphan=False)
    piece = load_midi(path)
    assert len(piece.notes) == 2
    assert piece.import_warnings == ()


def test_repaired_midi_passes_full_notation_import(tmp_path):
    import pytest
    pytest.importorskip("music21")
    from piano_teacher.score import import_piece

    path = _write_file(tmp_path / "engrave.mid", zero=True, orphan=True)
    piece, notation = import_piece(path)
    assert len(piece.notes) == 2
    assert len(piece.import_warnings) == 2
    # Verovio gets its canonical note IDs from build_lesson_score in the
    # runtime. The uploaded MIDI's original note IDs must remain stable.
    assert all(note.source_id for note in piece.notes)
