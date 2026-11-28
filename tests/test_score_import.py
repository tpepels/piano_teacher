"""Imported MIDI remains the music the player opened, including repairs."""
from pathlib import Path
from hashlib import sha256
import shutil

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


def test_replacing_a_file_during_open_keeps_the_notes_bound_to_the_fingerprint(
        practice_session, tmp_path, monkeypatch):
    def source(name, pitch):
        return write_tracks(tmp_path / name, [
            ("Right Hand", [(0, "note_on", pitch, 80, 0), (480, "note_off", pitch, 0, 0)]),
        ])

    selected = source("selected.mid", 72)
    replacement = source("replacement.mid", 76)
    original = sha256(selected.read_bytes()).hexdigest()
    updated = sha256(replacement.read_bytes()).hexdigest()
    read_bytes = Path.read_bytes

    def replace_after_read(path):
        data = read_bytes(path)
        if path.name == selected.name and replacement.exists():
            replacement.replace(path)
        return data

    monkeypatch.setattr(Path, "read_bytes", replace_after_read)
    session = practice_session(source=selected)
    assert session.snapshot()["piece_fingerprint"] == original
    assert [note.pitch for note in session.engine.lesson.plan.piece.notes] == [72]
    session.engine.load(str(session.path))
    assert session.snapshot()["piece_fingerprint"] == updated
    assert [note.pitch for note in session.engine.lesson.plan.piece.notes] == [76]


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
    bundle = session.ask("score.bundle")
    source, layout = bundle["model"], bundle["layout"]
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
    bundle = session.ask("score.bundle")
    source, layout = bundle["model"], bundle["layout"]
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
    bundle = session.ask("score.bundle")
    source, layout = bundle["model"], bundle["layout"]
    assert source["duration_beats"] == 4
    assert source["practice_timeline"]["gap"]["meter"] == [4,4]
    active = set(source["active_note_ids"])
    assert active and active <= set(layout["attack_map"])
    session.command("listen")
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["count_in_meter"] == [4,4] and state["count_in_beats"] == 4




def test_a_duplicate_release_does_not_swallow_a_repeated_note(tmp_path):
    """Some exports release a note twice; the repeat that follows on the same
    tick is a real note (code review 2026-11-25)."""
    import mido
    from piano_teacher.music import load_midi
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    for delta, kind in ((0, "note_on"), (480, "note_off"), (0, "note_off"),
                        (0, "note_on"), (480, "note_off")):
        track.append(mido.Message(kind, note=69, velocity=80 if kind == "note_on" else 0, time=delta))
    midi.save(tmp_path/"repeat.mid")
    assert [(n.start, n.end) for n in load_midi(tmp_path/"repeat.mid").notes] == [(0.0, 1.0), (1.0, 2.0)]


def test_musicxml_with_grace_notes_opens_without_them():
    """Für Elise has grace notes; they have no duration of their own and are
    not practice targets, and must not stop the piece opening."""
    from pathlib import Path
    from piano_teacher.importing.pieces import import_piece
    piece = import_piece(Path(__file__).parent/"fixtures"/"pieces"/"fur-elise.mxl")
    assert piece.notes and all(n.end > n.start for n in piece.notes)
