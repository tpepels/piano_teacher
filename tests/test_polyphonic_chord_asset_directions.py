"""Canonical Verovio chord atlases and native isolated voices share direction.

These source-only cases require no fake framebuffer or Godot metadata. The
existing two physical-shaft/erasure acceptance cases still run on real PNGs.
"""
from piano_teacher.notation.assets.chords import (
    chord_instances, polyphonic_chord_directions,
)


def model(groups, *, stems=None, beats=None):
    events = []
    stems = stems or {}
    beats = beats or {}
    for voice, pitches in enumerate(groups, 1):
        for index, (step, octave) in enumerate(pitches):
            event = {
                "id": f"v{voice}n{index}", "kind": "note",
                "staff": "right", "voice": str(voice), "measure": 1,
                "beat": float(beats.get(voice, 0)),
                "note_type": "half", "chord": index > 0,
                "spelling": {"step": step, "octave": octave, "alter": 0},
            }
            if voice in stems and index == 0:
                event["stem"] = stems[voice]
            events.append(event)
    return {
        "notation_events": events,
        "measures": [{"number": 1, "clefs": {"right": {"sign": "G", "line": 2}}}],
    }


def test_crossed_polyphonic_chord_uses_same_verovio_direction_as_other_voice():
    # A separate upper G5 may be voice 2; its lower C/E chord (voice 1)
    # must use a *down* Verovio-engraved stem, not the isolated chord stem.
    lower_chord = model([[("C", 5), ("E", 5)], [("G", 5)]])
    assert polyphonic_chord_directions(lower_chord) == {"v1n0": False}
    instances = chord_instances(lower_chord, pages=[])
    assert instances["v1n0"]["spec"][1] == "down"

    # Vice versa: the higher chord in voice 2 needs an UP physical shaft.
    higher_chord = model([[("C", 5)], [("E", 5), ("G", 5)]])
    assert polyphonic_chord_directions(higher_chord) == {"v2n0": True}
    instances = chord_instances(higher_chord, pages=[])
    assert instances["v2n0"]["spec"][1] == "up"


def test_overlapping_polyphonic_chord_ranges_keep_stable_voice_priority():
    score = model([[("C", 5), ("E", 5)], [("E", 5), ("G", 5)]])
    assert polyphonic_chord_directions(score) == {
        "v1n0": True, "v2n0": False,
    }
    instances = chord_instances(score, pages=[])
    assert {leader: instance["spec"][1] for leader, instance in instances.items()} == {
        "v1n0": "up", "v2n0": "down",
    }


def test_authored_stems_beams_and_other_onsets_keep_their_own_directions():
    source = model([[("C", 5), ("E", 5)], [("G", 5)]],
                   stems={1: "up"})
    assert polyphonic_chord_directions(source) == {}
    score = model([[("C", 5), ("E", 5)], [("G", 5)]])
    # A beam's actual source direction has priority over voice defaults.
    assert chord_instances(score, pages=[],
                           stem_directions={"v1n0": True})["v1n0"]["spec"][1] == "up"
    separated = model([[("C", 5), ("E", 5)], [("G", 5)]],
                      beats={2: 2})
    assert polyphonic_chord_directions(separated) == {}


def test_three_voices_use_register_order_and_preserve_chord_members():
    source = model([[("C", 5), ("E", 5)],
                    [("G", 5)],
                    [("B", 5), ("D", 6)]])
    assert polyphonic_chord_directions(source) == {
        "v1n0": False, "v3n0": True,
    }
    instances = chord_instances(source, pages=[])
    assert instances["v1n0"]["spec"][1] == "down"
    assert instances["v3n0"]["spec"][1] == "up"
    assert instances["v3n0"]["heads"] == ["v3n0", "v3n1"]
