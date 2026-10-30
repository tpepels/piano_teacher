"""Regression for the actual Moonlight Sonata I MIDI, not synthetic beams.

The source MIDI contains twelve eighth-triplet attacks per 4/4 measure.
Their physical releases are 0.01875 beat short, which previously produced
irregular-ratio flagged notes and lost the whole trio's beam metadata.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

from piano_teacher.music import Phrase, load_midi
from piano_teacher.learning import LearningPlan
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model

SOURCE = Path(__file__).resolve().parents[1]/"midi"/"Moonlight_Sonata_I.midi"


def _first_bar():
    piece = load_midi(SOURCE)
    source_notes = tuple(n for n in piece.notes if 0 <= n.start < 4)
    assert len([n for n in source_notes if n.hand == "right"]) == 12
    return piece, Phrase(1, 1, 1, 0.0, 4.0, source_notes)


def _source_xml(piece, phrase):
    score = build_lesson_score(
        phrase, boundaries=(0., 4.),
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures)
    return score, ET.fromstring(score.musicxml)


def _right_notes(root):
    return [n for n in root.findall("./part[@id='RH']/measure/note")
            if n.find("pitch") is not None]


def test_actual_moonlight_first_bar_has_four_beamed_eighth_triplets():
    piece, phrase = _first_bar()
    old_endings = tuple(n.end for n in phrase.notes)
    score, root = _source_xml(piece, phrase)
    notes = _right_notes(root)
    assert len(notes) == 12
    for trio in range(4):
        group = notes[trio*3:trio*3+3]
        assert [n.findtext("type") for n in group] == ["eighth"]*3, [
            (n.findtext("duration"), n.findtext("type"),
             n.findtext("time-modification/actual-notes"),
             n.findtext("time-modification/normal-notes")) for n in group]
        assert [n.findtext("time-modification/actual-notes") for n in group] == ["3"]*3
        assert [n.findtext("time-modification/normal-notes") for n in group] == ["2"]*3
        assert [[(b.get("number"), b.text) for b in n.findall("beam")]
                for n in group] == [[("1", "begin")], [("1", "continue")],
                                   [("1", "end")]]
        assert any(t.get("type") == "start" for t in
                   group[0].findall("notations/tuplet"))
        assert any(t.get("type") == "stop" for t in
                   group[-1].findall("notations/tuplet"))
    model = build_score_model(score, boundaries=(0., 4.))
    rendered = [e for e in model["notation_events"]
                if e["kind"] == "note" and e["staff"] == "right"]
    assert len(rendered) == 12
    assert sum(bool(e["beams"]) for e in rendered) == 12
    # Engraving never mutates physical source note duration or source MIDI.
    assert tuple(n.end for n in phrase.notes) == old_endings


def test_moonlight_initial_practice_stage_uses_complete_triplet_groups():
    piece = load_midi(SOURCE)
    plan = LearningPlan(piece)
    assert plan.exercise.phrase.first_bar == 1
    assert plan.hand == "right"
    variants = plan.variants
    assert variants[-1].level == "original"
    assert len(variants[-1].notes) == 12
    # The old skeleton kept only the four on-beat attacks. That destroyed
    # every beamed group and showed repeated isolated flags + dotted rests.
    first = variants[0]
    assert len(first.notes) == 3
    assert [round(n.start, 6) for n in first.notes] == [
        0., round(1/3, 6), round(2/3, 6)]
    score, root = _source_xml(piece, first.phrase)
    grouped = _right_notes(root)
    assert len(grouped) == 3
    assert [[tag.text for tag in n.findall("beam")] for n in grouped] == [
        ["begin"], ["continue"], ["end"]]
    assert set(first.source_indices) <= set(variants[-1].source_indices)


def test_actual_moonlight_verovio_beam_survives_svg_to_native_asset_pipeline():
    verovio = __import__("pytest").importorskip("verovio")
    __import__("pytest").importorskip("cairosvg")
    __import__("pytest").importorskip("PIL")
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.beams import (
        expected_beam_groups, extract_beam_fragments)

    piece = load_midi(SOURCE)
    first = LearningPlan(piece).variants[0]
    score, root = _source_xml(piece, first.phrase)
    model = build_score_model(score, boundaries=(0., 4.))
    ids = [e["id"] for e in model["notation_events"]
           if e["kind"] == "note" and e["staff"] == "right"]
    assert len(ids) == 3
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48,
                               "pageWidth": 900, "pageHeight": 650,
                               "svgViewBox": True,
                               "svgBoundingBoxes": True,
                               "svgContentBoundingBoxes": True})
    assert toolkit.loadData(score.musicxml)
    svg = toolkit.renderToSVG(1)
    key = "|".join(ids)
    assert key in expected_beam_groups([svg], model)
    fragments = extract_beam_fragments([svg], model)
    assert key in fragments, "Verovio beam was not available to Godot's native atlas"
    assert fragments[key]["note_ids"] == ids
    assert len(fragments[key]["tip_offsets"]) == 3
