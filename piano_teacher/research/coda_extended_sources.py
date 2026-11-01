"""Independent, pinned wider-Coda MusicXML source inventory.

Each tuple: unique ID, existing real score or authored regression MusicXML
path, first authored measure number, final selected measure number.
The diagnostic never treats merely checking a new input as reference parity.
"""
REFERENCE_SHA = "a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"

# Existing checked-in independent MusicXML sources: chords, two-staff
# polyphony, quintuplets, rests, meter changes, sixteenths, and 5:4/7:4.
# Two real repertoire excerpts exercise cases beyond synthesized fixtures.
SOURCES = (
    ("chord-ties", "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml", 1, 2),
    ("grandstaff-voices", "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml", 1, 1),
    ("source-quintuplets", "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml", 1, 1),
    ("trailing-rests", "tests/fixtures/musical_fidelity/xml_trailing_rests.musicxml", 1, 2),
    ("source-mixed-meter", "tests/fixtures/musical_fidelity/xml_mixed_meter.musicxml", 1, 2),
    ("source-sixteenth-beams", "tests/fixtures/connector_pixels/beam16/score.musicxml", 1, 1),
    ("source-five-to-four", "tests/fixtures/research/coda_group_5_4.musicxml", 1, 1),
    ("source-seven-to-four", "tests/fixtures/research/coda_group_7_4.musicxml", 1, 1),
    ("autumn-leaves-excerpt", "docs/evidence/native-audit-2026-10-26/autumn-source.musicxml", 37, 38),
    ("danny-boy-excerpt", "tests/fixtures/extra_shard_pixels/danny-stripe.musicxml", 1, 2),
)
