"""Literal raw MIDI overlap regressions; expectations never use the importer.

The first two timelines preserve the attack/release ordering found in the local
Moonlight export. MIDI identifies a release by channel/pitch, not attack ID, so
FIFO is an explicit interpretation rather than proof of an authored duration.
"""
from collections import Counter
from pathlib import Path

import mido
import pytest

from piano_teacher.music import load_midi
from piano_teacher.notation.semantic_contract import (
    _raw_midi_events,
    source_inventory,
    verify_midi_performance,
)


def _write_timeline(path, tracks):
    """Write literal absolute ticks in supplied order, including equal ticks."""
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for events in tracks:
        track = mido.MidiTrack()
        previous = 0
        for tick, kind, pitch, velocity, channel in events:
            track.append(mido.Message(kind, note=pitch, velocity=velocity,
                                      channel=channel, time=tick - previous))
            previous = tick
        midi.tracks.append(track)
    midi.save(path)
    return path


def _facts(piece):
    return [(n.source_id, n.start, n.end, n.pitch, n.track, n.channel, n.velocity)
            for n in piece.notes]


@pytest.mark.parametrize("release_kind", ["note_on", "note_off"])
def test_staggered_raw_overlap_keeps_both_attacks_and_both_releases(tmp_path, release_kind):
    # Source t0 e223/e227 attack E4; e228/e229 release it. FIFO durations
    # are 455 and 151 ticks, not truncation at the second attack (320 ticks).
    path = _write_timeline(tmp_path / "staggered.mid", [[
        (15360, "note_on", 64, 80, 0),
        (15680, "note_on", 64, 80, 0),
        (15815, release_kind, 64, 0, 0),
        (15831, release_kind, 64, 0, 0),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 32.0, 15815 / 480, 64, 0, 0, 80),
        ("midi-t0-e1", 98 / 3, 15831 / 480, 64, 0, 0, 80),
    ]
    assert {n.voice for n in piece.notes} == {"midi-t0-c0"}
    assert len(piece.import_warnings) == 1
    warning = piece.import_warnings[0]
    for detail in ("Ambiguous", "FIFO", "oldest attack first", "track 0",
                   "channel 0", "pitch 64", "15680", "midi-t0-e1",
                   "not uniquely"):
        assert detail in warning


def test_simultaneous_raw_unisons_are_separate_attacks_not_deduplicated(tmp_path):
    # Source t0 e392/e393 attack B3 simultaneously; releases are e394/e398.
    path = _write_timeline(tmp_path / "unisons.mid", [[
        (26880, "note_on", 59, 80, 0),
        (26880, "note_on", 59, 80, 0),
        (27031, "note_on", 59, 0, 0),
        (27335, "note_on", 59, 0, 0),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 56.0, 27031 / 480, 59, 0, 0, 80),
        ("midi-t0-e1", 56.0, 27335 / 480, 59, 0, 0, 80),
    ]
    assert len(piece.import_warnings) == 1


def test_three_overlaps_preserve_fifo_durations_and_attack_dynamics(tmp_path):
    path = _write_timeline(tmp_path / "polyphony.mid", [[
        (0, "note_on", 72, 91, 3),
        (120, "note_on", 72, 52, 3),
        (240, "note_on", 72, 73, 3),
        (360, "note_off", 72, 40, 3),
        (480, "note_on", 72, 0, 3),
        (600, "note_off", 72, 0, 3),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 0.0, .75, 72, 0, 3, 91),
        ("midi-t0-e1", .25, 1.0, 72, 0, 3, 52),
        ("midi-t0-e2", .5, 1.25, 72, 0, 3, 73),
    ]
    assert len(piece.import_warnings) == 2
    assert all("Ambiguous" in w and "FIFO" in w for w in piece.import_warnings)


def test_equal_tick_retrigger_before_release_keeps_two_positive_durations(tmp_path):
    path = _write_timeline(tmp_path / "boundary.mid", [[
        (0, "note_on", 60, 91, 0),
        (480, "note_on", 60, 52, 0),
        (480, "note_off", 60, 0, 0),
        (960, "note_off", 60, 0, 0),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 0.0, 1.0, 60, 0, 0, 91),
        ("midi-t0-e1", 1.0, 2.0, 60, 0, 0, 52),
    ]
    assert len(piece.import_warnings) == 1
    assert "FIFO" in piece.import_warnings[0]


def test_release_before_equal_tick_retrigger_is_unambiguous(tmp_path):
    path = _write_timeline(tmp_path / "sequential.mid", [[
        (0, "note_on", 60, 91, 0),
        (480, "note_off", 60, 0, 0),
        (480, "note_on", 60, 52, 0),
        (960, "note_off", 60, 0, 0),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 0.0, 1.0, 60, 0, 0, 91),
        ("midi-t0-e2", 1.0, 2.0, 60, 0, 0, 52),
    ]
    assert piece.import_warnings == ()


def test_overlap_queues_are_isolated_by_track_channel_and_pitch(tmp_path):
    path = _write_timeline(tmp_path / "isolated.mid", [[
        (0, "note_on", 64, 91, 0),
        (120, "note_on", 64, 52, 0),
        (240, "note_on", 64, 73, 1),
        (240, "note_on", 65, 81, 0),
        (360, "note_off", 64, 0, 1),
        (360, "note_off", 65, 0, 0),
        (480, "note_off", 64, 0, 0),
        (600, "note_off", 64, 0, 0),
    ], [
        (0, "note_on", 64, 43, 0),
        (720, "note_off", 64, 0, 0),
    ]])
    piece = load_midi(path)
    assert _facts(piece) == [
        ("midi-t0-e0", 0.0, 1.0, 64, 0, 0, 91),
        ("midi-t1-e0", 0.0, 1.5, 64, 1, 0, 43),
        ("midi-t0-e1", .25, 1.25, 64, 0, 0, 52),
        ("midi-t0-e2", .5, .75, 64, 0, 1, 73),
        ("midi-t0-e3", .5, .75, 65, 0, 0, 81),
    ]
    assert len(piece.import_warnings) == 1


def test_missing_release_after_overlap_still_fails_instead_of_fabricating_end(tmp_path):
    path = _write_timeline(tmp_path / "unterminated.mid", [[
        (0, "note_on", 64, 80, 0),
        (120, "note_on", 64, 81, 0),
        (480, "note_off", 64, 0, 0),
    ]])
    with pytest.raises(ValueError, match="unterminated MIDI note"):
        load_midi(path)


def test_successful_import_does_not_make_independent_pairing_unambiguous(tmp_path):
    path = _write_timeline(tmp_path / "audit.mid", [[
        (15360, "note_on", 64, 80, 0),
        (15680, "note_on", 64, 80, 0),
        (15815, "note_on", 64, 0, 0),
        (15831, "note_on", 64, 0, 0),
    ]])
    assert len(load_midi(path).notes) == 2
    # Native facts are hand calculated, not copied from the imported Piece.
    native = dict(active_hand="both", active_note_ids=["midi-t0-e0", "midi-t0-e1"], notes=[
        dict(id="midi-t0-e0", onset_beats=32.0, duration_beats=455 / 480,
             midi_pitch=64, velocity=80, track=0, channel=0,
             voice="midi-t0-c0", hand="right"),
        dict(id="midi-t0-e1", onset_beats=98 / 3, duration_beats=151 / 480,
             midi_pitch=64, velocity=80, track=0, channel=0,
             voice="midi-t0-c0", hand="right"),
    ])
    report = verify_midi_performance(path, native)
    assert report["passed"], report["discrepancies"]
    assert not report["complete"]
    for construct, expected_ids in (
        ("midi_performance", {"midi-t0-e0", "midi-t0-e1"}),
        ("midi_release", {"midi-t0-e2", "midi-t0-e3"}),
    ):
        rows = [e for e in report["elements"] if e["construct"] == construct]
        assert len(rows) == 2
        assert {e["source"]["id"] for e in rows} == expected_ids
        assert all(e["status"] == "verified" for e in rows)
    releases = [e for e in report["elements"] if e["construct"] == "midi_release"]
    assert {e["source"]["id"]: (e["evidence"]["attack_id"], e["evidence"]["release_tick"])
            for e in releases} == {
        "midi-t0-e2": ("midi-t0-e0", 15815),
        "midi-t0-e3": ("midi-t0-e1", 15831),
    }
    pairing = [e for e in report["elements"] if e["construct"] == "midi_note_pairing"]
    assert len(pairing) == 2
    assert {e["source"]["id"] for e in pairing} == {"midi-t0-e0", "midi-t0-e1"}
    assert all(e["status"] == "ambiguous" for e in pairing)
    transcription = [e for e in report["elements"]
                     if e["construct"] == "midi_written_transcription"]
    assert len(transcription) == 1 and transcription[0]["status"] == "unsupported"
    observed = Counter(e["id"] for e in report["elements"])
    for required in source_inventory(path):
        assert observed[required["id"]] == 1


def test_local_moonlight_preserves_every_raw_attack_and_release():
    path = Path(__file__).resolve().parents[1] / "midi/Moonlight_Sonata_I.midi"
    if not path.exists():
        pytest.skip("Local Moonlight export is unavailable; literal raw patterns run above")
    # The independent stdlib SMF reader inventories bytes without pairing notes.
    raw = list(_raw_midi_events(path.read_bytes()))
    piece = load_midi(path)
    attacks = Counter((e["track"], e["channel"], e["pitch"], e["tick"],
                       f'midi-t{e["track"]}-e{e["event_index"]}')
                      for e in raw if e["attack"] and e["channel"] != 9)
    releases = Counter((e["track"], e["channel"], e["pitch"], e["tick"])
                       for e in raw if not e["attack"] and e["channel"] != 9)
    assert len(piece.notes) == 1164
    assert attacks == Counter((n.track, n.channel, n.pitch, round(n.start * 480), n.source_id)
                              for n in piece.notes)
    assert releases == Counter((n.track, n.channel, n.pitch, round(n.end * 480))
                               for n in piece.notes)
    assert len(piece.import_warnings) == 24
    assert all("Ambiguous" in w and "FIFO" in w for w in piece.import_warnings)
    by_id = {n.source_id: n for n in piece.notes}
    assert (by_id["midi-t0-e223"].start, by_id["midi-t0-e223"].end) == (32.0, 15815 / 480)
    assert (by_id["midi-t0-e227"].start, by_id["midi-t0-e227"].end) == (98 / 3, 15831 / 480)
