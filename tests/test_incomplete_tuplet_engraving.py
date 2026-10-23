"""Invisible singleton MIDI tuplets versus genuine complete written groups."""
from xml.etree import ElementTree as ET

from piano_teacher.notation.lesson import (
    DIVISIONS, _append_note, _write_tuplet_groups,
)


def _signatures(measure):
    return [(note.findtext("duration"),
             note.findtext("time-modification/actual-notes"),
             note.findtext("time-modification/normal-notes"),
             [dict(t.attrib) for t in note.findall("notations/tuplet")])
            for note in measure.findall("note")]


def test_isolated_expressive_quintuplet_rest_and_note_have_no_fake_group_label():
    # In Autumn Leaves the MIDI has a 1.6-beat rest and an isolated 0.4-beat
    # onset, represented precisely as 5:4. They are *not* five eighths.
    measure = ET.Element("measure")
    _append_note(measure, None, 16128, 1)
    _append_note(measure, 67, 4032, 1)
    original = _signatures(measure)
    assert all(item[1:3] == ("5", "4") for item in original)
    _write_tuplet_groups(measure)
    after = _signatures(measure)
    assert after == original, (
        "Unpaired tuplets must keep exact MusicXML durations and hidden "
        "Verovio timing markers, without invented visible '5' labels"
    )
    assert all(
        len(item[3]) == 2
        and item[3][0]["type"] == "start"
        and item[3][0]["show-number"] == "none"
        and item[3][0]["bracket"] == "no"
        and item[3][1]["type"] == "stop"
        for item in after
    )


def test_a_complete_written_group_of_five_keeps_one_visible_bracket():
    measure = ET.Element("measure")
    for pitch in (60, 62, 64, 65, 67):
        _append_note(measure, pitch, round(DIVISIONS * .5 * 4 / 5), 1)
    _write_tuplet_groups(measure)
    specs = _signatures(measure)
    assert all(item[1:3] == ("5", "4") for item in specs)
    assert [len(item[3]) for item in specs] == [1, 0, 0, 0, 1]
    assert specs[0][3][0]["type"] == "start"
    assert specs[-1][3][0]["type"] == "stop"
    assert all(item[3][0]["show-number"] == "actual"
               and item[3][0]["bracket"] == "yes"
               for item in (specs[0], specs[-1]))
