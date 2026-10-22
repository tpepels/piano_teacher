"""Regression contract for the user's seven real MIDI visual fixtures.

Verovio is the notation authority. The full source-SVG-vs-Godot-pixel
comparison is executed by scripts/check_user_midi_visual_regression.py;
these tests pin the real, unmodified source corpus independently of rendering.
"""
from pathlib import Path

import mido
import pytest

from scripts.check_user_midi_visual_regression import CASES, MIDI_DIR
from piano_teacher.lesson_timing import preparation_meter, lead_in_beats
from piano_teacher.score import import_piece


def test_seven_original_midi_files_are_present():
    assert len(CASES) == 7
    assert len({filename for filename, _ in CASES}) == len(CASES)
    assert {p.name for p in MIDI_DIR.glob("*.midi")} >= {
        filename for filename, _ in CASES
    }, "An original visual regression MIDI was renamed or removed"
    # Additional real scores are independently pinned and audited by Phase 5;
    # retaining this earlier seven-score probe must not exclude them.
    from scripts.audit_phase5_scores import validate_inventory
    import json
    inventory = Path(__file__).parent / 'fixtures/phase5-midi-inventory.json'
    assert not validate_inventory(json.loads(inventory.read_text()), MIDI_DIR)
    for filename, hand in CASES:
        assert hand in {"left", "right", "both"}
        assert (MIDI_DIR / filename).stat().st_size > 1000


@pytest.mark.parametrize("filename,initial_meter,initial_bpm", [
    ("Ala_–_Joep_Beving.midi", (3, 4), 110),
    ("Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi",
     (4, 4), 190),
    ("Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", (1, 8), 60),
    ("Danny_Boy(Bill_Evans_Ver_).midi", (4, 4), 60),
    ("Merry-Go-Round-of-Life.midi", (3, 4), 100),
    ("Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", (1, 8), 56),
    ("Waltz_for_Debby.midi", (3, 4), 120),
])
def test_real_midi_meters_and_tempos_are_not_silently_rewritten(
        filename, initial_meter, initial_bpm):
    midi = mido.MidiFile(str(MIDI_DIR / filename))
    signatures = []
    tempos = []
    for track in midi.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "time_signature":
                signatures.append((tick / midi.ticks_per_beat,
                                   (msg.numerator, msg.denominator)))
            elif msg.type == "set_tempo":
                tempos.append((tick / midi.ticks_per_beat, msg.tempo))
    assert signatures and signatures[0][1] == initial_meter, filename
    assert tempos and round(60_000_000 / tempos[0][1]) == initial_bpm, filename
    if filename.startswith("Chopin"):
        assert (0.5, (12, 8)) in signatures, (
            "The visible 1/8 to 12/8 meter change is genuine source metadata"
        )
    if filename.startswith("Peace_Piece"):
        assert any(meter == (131, 4) for _, meter in signatures), (
            "Retain the source anomaly as a documented import-repair regression"
        )


def test_chopin_pickup_prepares_with_following_measure_not_half_a_beat():
    piece, _ = import_piece(MIDI_DIR / "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi")
    assert piece.time_signatures[0] == (0.0, 1, 8)
    assert piece.time_signatures[1] == (0.5, 12, 8)
    meter = preparation_meter((1, 8), piece.time_signatures, 0.0)
    assert meter == (12, 8)
    assert lead_in_beats(meter[0] * 4 / meter[1], 24) >= 1.0
    # The score remains faithful to the real imported pickup measure.
    assert piece.bar_boundaries[1] == pytest.approx(0.5)


def test_pickup_meter_only_changes_immediate_short_preparation():
    assert preparation_meter((3, 4), ((0.0, 3, 4),), 0.0) == (3, 4)
    assert preparation_meter((1, 8), ((0.0, 1, 8),), 0.0) == (1, 8)
    assert preparation_meter((1, 8), ((0.0, 1, 8), (20.0, 4, 4)), 0.0) == (1, 8)
    assert preparation_meter((1, 8), ((0.0, 1, 8), (0.5, 4, 4)), 0.0) == (4, 4)
