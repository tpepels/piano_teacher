"""MIDI-domain Coda category completeness and safe author transformations."""
from dataclasses import replace

import mido
import pytest

from piano_teacher.application.coda_midi_curriculum import (
    _first_meter, midi_coda_catalog, midi_coda_stages,
)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Phrase, load_midi
from piano_teacher.research.coda_auto_chord_levels import original_chord_levels
from piano_teacher.research.coda_midi_grid import midi_coda_quantization


def _midi(tmp_path, notes, *, numerator=4, denominator=4):
    """Write independent right/left tracks and explicit source attacks."""
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for hand in ("right", "left"):
        selected = [(start, end, pitch) for h, start, end, pitch in notes if h == hand]
        if not selected:
            continue
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name",
                                      name=hand.title() + " Hand", time=0))
        if hand == "right":
            track.append(mido.MetaMessage(
                "time_signature", numerator=numerator,
                denominator=denominator, time=0))
        events = []
        for start, end, pitch in selected:
            events.extend(((round(start * 480), True, pitch),
                           (round(end * 480), False, pitch)))
        current = 0
        for tick, on, pitch in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(mido.Message(
                "note_on" if on else "note_off", note=pitch,
                velocity=80 if on else 0, time=tick - current))
            current = tick
        midi.tracks.append(track)
    path = tmp_path / "coda-catalog.mid"
    midi.save(path)
    return load_midi(path)


def _original(piece):
    return ExerciseVariant("original", Phrase(
        1, 1, len(piece.bar_boundaries) - 1,
        piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes),
        tuple(range(len(piece.notes))))


def test_midi_dotted_rhythm_can_group_valid_notes_across_barline(tmp_path):
    # The author groups equal-duration runs across bars. The earlier MIDI
    # adapter incorrectly rejected this pair as if a MusicXML beam existed.
    piece = _midi(tmp_path, [
        ("right", 3, 4, 60), ("right", 4, 5, 62)])
    original = _original(piece)
    catalog = midi_coda_catalog(piece, original)
    dotted = next(item for item in catalog
                  if item.request == "dotted-long-short")
    assert dotted.status == "generated"
    by_pitch = {n.pitch: n for n in dotted.stage.variant.notes}
    assert by_pitch[60].start == pytest.approx(3)
    assert by_pitch[60].end == pytest.approx(4.5)
    assert by_pitch[62].start == pytest.approx(4.5)
    assert by_pitch[62].end == pytest.approx(5)
    stages = midi_coda_stages(piece, (original,), kind="learn")
    assert any(s.variant.level == "coda-dotted-long-short" for s in stages)


def test_full_multihand_catalog_inventories_every_part_voice_and_request(tmp_path):
    piece = _midi(tmp_path, [
        ("right", 0, .5, 60), ("right", .5, 1, 62),
        ("right", 1, 1.5, 64), ("right", 1.5, 2, 65),
        ("left", 0, 1, 48), ("left", 1, 2, 50)])
    original = _original(piece)
    catalog = midi_coda_catalog(piece, original)
    assert sum(x.category == "Score Level" for x in catalog) == 1
    assert sum(x.category == "Part Level" for x in catalog) == 2
    assert sum(x.category == "Voice Level: Original" for x in catalog) == 2
    q = midi_coda_quantization(piece, original.phrase, compact=True)
    width_count = len(original_chord_levels(q, 4, 4))
    for voice in {x.voice for x in catalog if x.voice}:
        subset = [x for x in catalog if x.voice == voice]
        assert sum(x.category == "Voice Level: Dotted" for x in subset) == 2
        assert sum(x.category == "Voice Level: Chordified" for x in subset) == width_count
        assert sum(x.category == "Voice Level: Slowed Down" for x in subset) == 2
        assert all(x.status in ("inventory", "generated", "unchanged",
                                 "author-invalid", "unrepresentable")
                   for x in subset)
        assert all(x.status != "unrepresentable" or x.reason for x in subset)
    # Both-hand is an unchanged Score Level, with separate hand lessons
    # providing per-Part and per-Voice exercises.
    assert len(midi_coda_stages(piece, (original,), kind="learn")) == 1


def test_invalid_zero_chord_width_is_reported_not_silently_dropped(tmp_path):
    piece = _midi(tmp_path, [
        ("right", 0, 1, 60), ("right", 1, 2, 62)], numerator=3)
    catalog = midi_coda_catalog(piece, _original(piece))
    invalid = [x for x in catalog if x.category == "Voice Level: Chordified"
               and x.request == "chord-0"]
    assert len(invalid) == 1
    assert invalid[0].status == "author-invalid"
    assert invalid[0].stage is None


def test_active_meter_uses_last_transition_before_selected_excerpt(tmp_path):
    piece = _midi(tmp_path, [("right", 0, 1, 60)])
    piece = replace(piece, time_signatures=(
        (0, 4, 4), (4, 5, 8), (6.5, 3, 4)))
    assert _first_meter(piece, 0) == (4, 4)
    assert _first_meter(piece, 4) == (5, 8)
    assert _first_meter(piece, 6) == (5, 8)
    assert _first_meter(piece, 7) == (3, 4)


def test_no_op_is_explicit_and_keeps_complete_author_request_catalog(tmp_path):
    piece = _midi(tmp_path, [("right", 0, 1, 60)])
    catalog = midi_coda_catalog(piece, _original(piece))
    assert any(e.category == "Voice Level: Dotted" and
               e.status == "unchanged" for e in catalog)
    assert any(e.category == "Voice Level: Slowed Down" and
               e.status == "generated" for e in catalog)
    assert all(e.status != "generated" or e.stage is not None for e in catalog)
