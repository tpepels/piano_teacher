"""Imported MIDI remains the music the player opened, including repairs."""
from pathlib import Path
import shutil
import time

import mido
import pytest

from piano_teacher.importing.pieces import import_piece
from piano_teacher.music import load_midi

FIXTURES = Path(__file__).parent / "fixtures" / "musical_fidelity"


def write_tracks(path, tracks, *, meter=(4, 4)):
    """Literal absolute ticks; equal-tick event order is intentional."""
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for name, events in tracks:
        track = mido.MidiTrack([
            mido.MetaMessage("track_name", name=name),
            mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1]),
            mido.MetaMessage("set_tempo", tempo=600000),
        ])
        previous = 0
        for tick, kind, pitch, velocity, channel in events:
            track.append(mido.Message(kind, note=pitch, velocity=velocity,
                                      channel=channel, time=tick - previous))
            previous = tick
        midi.tracks.append(track)
    midi.save(path)
    return path


def test_import_preserves_crossed_hands_dynamics_meter_and_sustained_end(tmp_path):
    path = write_tracks(tmp_path / "crossed.mid", [
        ("Left Hand", [(0, "note_on", 65, 32, 0), (2400, "note_off", 65, 0, 0)]),
        ("Right Hand", [(160, "note_on", 55, 113, 1), (480, "note_on", 55, 0, 1)]),
    ], meter=(6, 8))
    piece = import_piece(path)
    assert piece.bpm == 100
    assert piece.time_signatures == ((0, 6, 8),)
    assert piece.bar_boundaries[:3] == (0, 3, 6)
    assert [(n.pitch, n.hand, n.start, n.end, n.velocity) for n in piece.notes] == [
        (65, "left", 0, 5, 32), (55, "right", 1 / 3, 1, 113),
    ]
    assert len({n.source_id for n in piece.notes}) == 2
    assert [n.source_id for n in load_midi(path).notes] == [n.source_id for n in piece.notes]
    assert not piece.import_warnings


def test_raw_unison_overlaps_keep_every_attack_and_fifo_release(tmp_path):
    path = write_tracks(tmp_path / "overlap.mid", [
        ("Right Hand", [(0, "note_on", 64, 91, 0),
                        (0, "note_on", 64, 52, 0),
                        (120, "note_on", 64, 73, 0),
                        (240, "note_off", 64, 0, 0),
                        (480, "note_on", 64, 0, 0),
                        (600, "note_off", 64, 0, 0)]),
        ("Left Hand", [(0, "note_on", 64, 43, 0),
                       (720, "note_off", 64, 0, 0)]),
    ])
    piece = load_midi(path)
    assert sorted((n.start, n.end, n.velocity) for n in piece.notes) == [
        (0, .5, 91), (0, 1, 52), (0, 1.5, 43), (.25, 1.25, 73),
    ]
    assert len({n.source_id for n in piece.notes}) == 4
    assert any("FIFO" in warning for warning in piece.import_warnings)


def test_repair_keeps_valid_notes_and_source_identity_without_inventing_releases(tmp_path):
    clean = [(0, "note_on", 60, 80, 0), (480, "note_off", 60, 0, 0)]
    path = write_tracks(tmp_path / "repair.mid", [("Right Hand", clean)])
    original = load_midi(path).notes[0]
    write_tracks(path, [("Right Hand", clean + [
        (480, "note_on", 62, 80, 0), (480, "note_off", 62, 0, 0),
        (480, "note_off", 60, 0, 1),
    ])])
    repaired = import_piece(path)
    assert [(n.source_id, n.pitch, n.start, n.end) for n in repaired.notes] == [
        (original.source_id, 60, 0, 1),
    ]
    assert any("zero-duration" in w for w in repaired.import_warnings)
    assert any("unmatched" in w for w in repaired.import_warnings)
    write_tracks(path, [("Right Hand", clean + [(600, "note_on", 64, 80, 0)])])
    with pytest.raises(ValueError, match="unterminated MIDI note"):
        load_midi(path)


def test_bad_meter_metadata_does_not_shift_notes(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage("time_signature", numerator=4, denominator=4),
        mido.Message("note_on", note=60, velocity=80),
        mido.Message("note_off", note=60, time=480),
        mido.MetaMessage("time_signature", numerator=131, denominator=4, time=480),
        mido.Message("note_on", note=64, velocity=80),
        mido.Message("note_off", note=64, time=480),
    ]))
    path = tmp_path / "bad-meter.mid"
    midi.save(path)
    piece = load_midi(path)
    assert piece.time_signatures == ((0, 4, 4),)
    assert [(n.start, n.end) for n in piece.notes] == [(0, 1), (2, 3)]
    assert any("131/4" in warning for warning in piece.import_warnings)


def test_midi_alone_retains_triplets_and_authored_meter_changes():
    triplets = import_piece(FIXTURES / "midi_triplets.mid")
    assert [n.start for n in triplets.notes[:3]] == pytest.approx([0, 1 / 3, 2 / 3])
    assert [n.end - n.start for n in triplets.notes[:3]] == pytest.approx([1 / 3] * 3)
    mixed = import_piece(FIXTURES / "midi_mixed_meter.mid")
    assert len(mixed.time_signatures) > 1
    assert mixed.time_signatures == ((0, 3, 4), (3, 4, 4))
    assert mixed.bar_boundaries == (0, 3, 7, 11)


def test_percussion_only_file_cannot_be_opened_as_piano_music(tmp_path):
    path = write_tracks(tmp_path / "drums.mid", [("Percussion", [
        (0, "note_on", 36, 80, 9), (480, "note_off", 36, 0, 9),
    ])])
    with pytest.raises(ValueError, match="No pitched"):
        import_piece(path)


def test_native_score_preserves_chord_attacks_and_full_tied_ending(practice_session):
    session = practice_session(bars=2, chords=True, held_tail=2)
    session.select(1, 2, hand="both")
    source = session.ask("score.semantic")
    layout = session.ask("score.native_layout")
    heads = {note["id"]: note for note in layout["notes"]}
    chord = [note for note in source["notes"] if note["hand"] == "right" and note["onset_beats"] == 0]
    assert {note["midi_pitch"] for note in chord} == {72,76,79}
    chord_heads = [heads[layout["attack_map"][note["id"]]] for note in chord]
    assert {head["pitch"] for head in chord_heads} == {72,76,79}
    assert all(head["is_attack"] and head["hand"] == "right" and head["beat"] == 0
               for head in chord_heads)
    ending = next(note for note in source["notes"] if note["onset_beats"] == 7)
    assert ending["duration_beats"] == 3
    attack = heads[layout["attack_map"][ending["id"]]]
    assert attack["is_attack"] and attack["pitch"] == 80 and attack["beat"] == 7
    continuations = [heads[head] for head in layout["continuation_map"][ending["id"]]]
    assert continuations and all(not head["is_attack"] for head in continuations)
    assert all(head["source_id"] == ending["id"] and head["pitch"] == ending["midi_pitch"]
               and 7 < head["beat"] < 10 for head in continuations)
    assert source["practice_timeline"]["sounding_duration_beats"] == 10


def test_midi_triplets_reach_native_notation_with_their_beam_and_number(practice_session):
    session = practice_session(bars=1)
    target = session.music/"triplets.mid"
    shutil.copyfile(FIXTURES/"midi_triplets.mid", target)
    session.ask("library.open", id=target.name)
    session.select(hand="both", final=True)
    source = session.ask("score.semantic")
    layout = session.ask("score.native_layout")
    triplet = source["notes"][:3]
    assert [note["onset_beats"] for note in triplet] == pytest.approx([0,1/3,2/3])
    heads = {layout["attack_map"][note["id"]] for note in triplet}
    assert any(set(fragment["note_ids"]) == heads
               for fragment in layout["native_tuplet_fragments"].values())
    assert layout["native_beams_complete"] and layout["native_beam_fragments"]
    assert any(mark["type"] == "start" for event in source["notation_events"]
               for mark in event.get("tuplet_marks", []))


def test_authored_meter_change_survives_source_selection_and_native_engraving(practice_session):
    session = practice_session(bars=1)
    target = session.music/"mixed.mid"
    shutil.copyfile(FIXTURES/"midi_mixed_meter.mid", target)
    session.ask("library.open", id=target.name)
    session.select(2,2)
    source = session.ask("score.semantic")
    layout = session.ask("score.native_layout")
    assert source["duration_beats"] == 4
    assert source["practice_timeline"]["gap"]["meter"] == [4,4]
    active = set(source["active_note_ids"])
    assert active and active <= set(layout["attack_map"])
    session.command("listen")
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["count_in_meter"] == [4,4] and state["count_in_beats"] == 4


def test_preloaded_score_stays_bound_to_its_source_after_opening_another_piece(practice_session):
    from piano_teacher.inprocess import INVALID
    from session_inputs import write_midi
    import json

    session = practice_session(bars=2)
    session.finish_listen()
    session.finish_free()
    before = session.ready_score()

    def next_score():
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            prepared = session.ask("score.next_stage")
            if prepared["status"] != "preparing":
                assert prepared["status"] == "ready", prepared
                return prepared
            time.sleep(.005)
        raise AssertionError("Real next-stage notation did not prepare")

    first = next_score()
    assert first["hand"] == "left" and first["step_number"] == 2
    assert first["layout"]["attack_map"]
    assert all(note["hand"] == "left" for note in first["model"]["notes"])
    assert session.snapshot()["hand"] == before["hand"]
    assert session.snapshot()["transport_id"] == before["transport_id"]
    assert session.ask("score.stage_ready", stage_key=first["stage_key"],
                       revision=first["revision"])["accepted"]
    second_path = write_midi(session.music/"new.mid", bars=2, bpm=100)
    session.ask("library.open", id=second_path.name)
    session.finish_listen()
    session.finish_free()
    session.ready_score()
    status, _ = session.commands.request("score.stage_ready", json.dumps({
        "stage_key": first["stage_key"], "revision": first["revision"]}))
    assert status == INVALID
    assert not session.ask("score.stage_failed", fingerprint=first["fingerprint"],
                           step_number=first["step_number"], revision=first["revision"],
                           error="Late failure from the previous piece")["accepted"]
    second = next_score()
    assert second["fingerprint"] != first["fingerprint"]
    assert second["fingerprint"] == session.ask("learning.status")["current_fingerprint"]
