"""MIDI-only beaming: musical grouping without changing MIDI grading."""
from xml.etree import ElementTree as ET

from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


def _score(specs, *, beats=4, beat_type=4, length=None):
    if length is None:
        length = beats * 4 / beat_type
    notes = tuple(Note(start, start + duration, pitch, 0, 0, hand,
                       f"n{i}", voice=voice)
                  for i, (start, duration, pitch, hand, voice) in enumerate(specs))
    phrase = Phrase(1, 1, 1, 0., length, notes)
    score = build_lesson_score(
        phrase, boundaries=(0., length),
        time_signatures=((0., beats, beat_type),))
    return score, ET.fromstring(score.musicxml)


def _notes(root, hand="RH"):
    return [node for node in root.findall(f"./part[@id='{hand}']/measure/note")
            if node.find("pitch") is not None]


def _beams(note):
    return [(int(tag.get("number")), tag.text) for tag in note.findall("beam")]


def test_four_four_eighths_group_by_quarter_with_unaltered_attacks():
    specs = [(i * .5, .5, 60 + i, "right", "voice")
             for i in range(8)]
    score, root = _score(specs)
    assert [_beams(n) for n in _notes(root)] == [
        [(1, "begin")], [(1, "end")]] * 4
    model = build_score_model(score, boundaries=(0., 4.))
    assert [n["onset_beats"] for n in model["notes"]] == [i * .5 for i in range(8)]
    assert all(e["beams"] for e in model["notation_events"]
               if e["kind"] == "note")


def test_six_eight_groups_three_eighths_per_dotted_quarter():
    _, root = _score([(i * .5, .5, 60 + i, "right", "v") for i in range(6)],
                     beats=6, beat_type=8)
    assert [_beams(n) for n in _notes(root)] == [
        [(1, "begin")], [(1, "continue")], [(1, "end")]] * 2


def test_sixteenths_have_two_complete_beam_levels():
    _, root = _score([(i * .25, .25, 60 + i, "right", "v")
                      for i in range(4)])
    assert [_beams(n) for n in _notes(root)] == [
        [(1, "begin"), (2, "begin")],
        [(1, "continue"), (2, "continue")],
        [(1, "continue"), (2, "continue")],
        [(1, "end"), (2, "end")]]


def test_mixed_eighth_sixteenth_and_secondary_hooks():
    _, root = _score([
        (0, .5, 60, "right", "v"),
        (.5, .25, 62, "right", "v"),
        (.75, .25, 64, "right", "v"),
        (1, .25, 65, "right", "v"),
        (1.25, .5, 67, "right", "v"),
    ])
    assert [_beams(n) for n in _notes(root)] == [
        [(1, "begin")],
        [(1, "continue"), (2, "begin")],
        [(1, "end"), (2, "end")],
        [(1, "begin"), (2, "forward hook")],
        [(1, "end")]]


def test_rests_and_measure_boundaries_break_beams():
    _, root = _score([
        (0, .5, 60, "right", "v"),
        (1, .5, 62, "right", "v"),
        (1.5, .5, 64, "right", "v"),
        (2.5, .5, 65, "right", "v"),
        (3, .5, 67, "right", "v"),
    ])
    assert [_beams(n) for n in _notes(root)] == [
        [], [(1, "begin")], [(1, "end")], [], []]


def test_hands_and_polyphonic_voices_do_not_share_beams():
    _, root = _score([
        (0, .5, 60, "right", "a"),
        (.5, .5, 62, "right", "a"),
        (0, .5, 48, "left", "b"),
        (.5, .5, 50, "left", "b"),
        (0, .5, 72, "right", "c"),
        (.5, .5, 74, "right", "c"),
    ])
    assert sum(bool(_beams(n)) for n in _notes(root, "RH")) == 4
    assert sum(bool(_beams(n)) for n in _notes(root, "LH")) == 2


def test_hidden_release_padding_does_not_split_a_written_beam():
    score, root = _score([
        (0, .45, 60, "right", "v"),
        (.5, .5, 62, "right", "v"),
    ])
    assert [_beams(n) for n in _notes(root)] == [
        [(1, "begin")], [(1, "end")]]
    assert any(n.get("print-object") == "no"
               for n in root.findall("./part[@id='RH']/measure/note"))
    assert [n["onset_beats"] for n in build_score_model(
        score, boundaries=(0., 4.))["notes"]] == [0., .5]


def test_irregular_ratios_are_not_mis_beamed():
    _, root = _score([
        (0, .375, 60, "right", "v"),
        (.375, .625, 62, "right", "v"),
    ])
    assert not any(n.findall("beam") for n in _notes(root))


def test_real_verovio_exports_genuine_beam_for_midi_generated_exercise():
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.beams import (
        expected_beam_groups, extract_beam_fragments)

    score, _ = _score([
        (0., .5, 60, "right", "v"),
        (.5, .5, 62, "right", "v"),
    ])
    model = build_score_model(score, boundaries=(0., 4.))
    ids = [n["id"] for n in model["notation_events"]
           if n["kind"] == "note"]
    assert len(ids) == 2
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48,
                               "pageWidth": 900, "pageHeight": 650,
                               "svgViewBox": True, "svgBoundingBoxes": True,
                               "svgContentBoundingBoxes": True})
    assert toolkit.loadData(score.musicxml)
    page = toolkit.renderToSVG(1)
    key = "|".join(ids)
    assert key in expected_beam_groups([page], model)
    assert key in extract_beam_fragments([page], model)
