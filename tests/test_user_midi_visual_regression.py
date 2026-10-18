"""Regression contract for the user's seven real MIDI visual fixtures.

Verovio is the notation authority. The full source-SVG-vs-Godot-pixel
comparison is executed by scripts/check_user_midi_visual_regression.py;
these tests pin the real, unmodified source corpus independently of rendering.
"""
from pathlib import Path

import mido
import pytest

from scripts.check_user_midi_visual_regression import CASES, MIDI_DIR


def test_seven_original_midi_files_are_present():
    assert len(CASES) == 7
    assert len({filename for filename, _ in CASES}) == len(CASES)
    assert {p.name for p in MIDI_DIR.glob("*.midi")} == {
        filename for filename, _ in CASES
    }, "A visual regression MIDI was added, renamed or removed; update the manifest"
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
