"""Bounded production regressions for four formerly accepted Peace Piece failures."""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.importing.pieces import import_piece
from piano_teacher.notation.lesson import DIVISIONS, _append_note, _write_tuplet_groups
from piano_teacher.notation.midi_beaming import beam_midi_measure
from piano_teacher.preprocessing_cache import PreprocessingCache


@pytest.fixture(scope="module")
def peace_piece():
    path = next((Path(__file__).resolve().parents[1] / "midi").glob("Peace_Piece*.midi"))
    piece, _ = import_piece(path)
    return path, piece


@pytest.mark.parametrize("first_bar", [31, 37, 53, 67])
def test_peace_piece_original_attacks_reach_native_geometry(first_bar, peace_piece, tmp_path):
    path, piece = peace_piece
    phrase = next(p for p in piece.phrases if p.first_bar == first_bar)
    original = [(n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes]
    selected = ScoreSelection(piece, phrase, "both", "peace-regression", 1, path.name)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path))
    model = artifacts.semantic_score(selected)
    layout = artifacts.geometry(selected)
    bindings = artifacts._selected_notation(selected).note_bindings
    heads = {head["id"]: head for head in layout["notes"]}
    assert set(heads) == set(bindings)
    attacks = [head for head in heads.values() if head["is_attack"]]
    assert {head["source_id"] for head in attacks} == {row[0] for row in original}
    assert len(attacks) == len(original)
    sources = {note.source_id: note for note in phrase.notes}
    for head in attacks:
        source = sources[head["source_id"]]
        assert head["source_beat"] == pytest.approx(source.start - phrase.start, abs=1e-12)
        assert (head["pitch"], head["hand"]) == (source.pitch, source.hand)
    semantic_notes = {note["id"]: note for note in model["notes"]}
    assert set(semantic_notes) == set(sources)
    for identity, source in sources.items():
        assert semantic_notes[identity]["onset_beats"] == round(source.start - phrase.start, 8)
        assert semantic_notes[identity]["duration_beats"] == round(min(source.end, phrase.end) - source.start, 8)
    for identity, binding in bindings.items():
        assert heads[identity]["beat"] == pytest.approx(binding["display_beat"], abs=1 / DIVISIONS)
    assert [(n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes] == original
    from piano_teacher.notation.assets.chords import chord_lanes, refused_chords
    assert refused_chords(model) == []
    mapped = {leader: heads for item in layout["native_chord_templates"].values()
              for leader, heads in item.get("leaders", {}).items()}
    for leader, notes, _ in chord_lanes(model):
        assert sorted(mapped[leader["id"]]) == sorted(note["id"] for note in notes)


@pytest.mark.parametrize("hidden_rest", [False, True])
def test_beams_do_not_extend_singleton_tuplet_scope(hidden_rest):
    measure = ET.Element("measure")
    if hidden_rest:
        _append_note(measure, 60, 2520, 1)
    _append_note(measure, None if hidden_rest else 62, 840, 1,
                 hidden_rest=hidden_rest)
    _append_note(measure, 64, 2520, 1)
    _append_note(measure, 65, 2520, 1)
    _write_tuplet_groups(measure)
    before = [ET.tostring(n) for n in measure.findall("note")]
    beam_midi_measure(measure, 4, 4, DIVISIONS, 4 * DIVISIONS)
    notes = measure.findall("note")
    singleton = notes[1 if hidden_rest else 0]
    assert singleton.findall("beam") == []
    if hidden_rest:
        assert notes[0].findall("beam") == []
    assert [n.findtext("beam") for n in notes[-2:]] == ["begin", "end"]
    # Beaming must preserve exact durations, IDs, ratios and local tuplet marks.
    for note, original in zip(notes, before):
        for beam in note.findall("beam"):
            note.remove(beam)
        assert ET.tostring(note) == original


def test_complete_triplet_keeps_one_beam_inside_its_tuplet():
    measure = ET.Element("measure")
    for pitch in (60, 62, 64):
        _append_note(measure, pitch, 3360, 1)
    _write_tuplet_groups(measure)
    beam_midi_measure(measure, 4, 4, DIVISIONS, 4 * DIVISIONS)
    assert [n.findtext("beam") for n in measure.findall("note")] == ["begin", "continue", "end"]
