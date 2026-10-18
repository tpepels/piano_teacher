"""Phase A contract: one versioned musical model, no Verovio or pixel layout."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import builtins
import json
import threading
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

import pytest

from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.music import Note, Phrase, Piece, KeySignature
from piano_teacher.practice import evaluate, PlayedNote
from piano_teacher.score_model import SCHEMA, build_score_model
from piano_teacher.learning import LearningPlan
from piano_teacher.server import Handler, PracticeEngine


def fixture():
    notes = (
        Note(0, 1, 60, 0, 0, "right", "r1", voice="lead"),
        Note(0, 1, 64, 0, 0, "right", "r2", voice="lead"),
        Note(.5, 1.25, 67, 0, 0, "right", "r3", voice="counter"),
        Note(2.5, 4, 48, 1, 0, "left", "l1"),
        Note(5, 6, 62, 0, 0, "right", "r4"),
    )
    phrase = Phrase(1, 1, 2, 0, 7, notes)
    boundaries = (0, 3, 7)
    meters = ((0, 3, 4), (3, 4, 4))
    return phrase, boundaries, meters


def make_model(active_hand="both"):
    phrase, boundaries, meters = fixture()
    notation = build_lesson_score(phrase, boundaries=boundaries,
                                  time_signatures=meters)
    return build_score_model(notation, boundaries=boundaries, hand=active_hand)


def test_semantic_schema_is_renderer_and_bpm_independent(monkeypatch):
    phrase, boundaries, meters = fixture()
    notation = build_lesson_score(phrase, boundaries=boundaries,
                                  time_signatures=meters)
    imported = builtins.__import__

    def without_renderer(name, *args, **kwargs):
        if name == "verovio" or name.startswith("verovio."):
            raise AssertionError("ScoreModel must not import Verovio")
        return imported(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_renderer)
    model = build_score_model(notation, boundaries=boundaries, hand="right")
    assert model["schema"] == SCHEMA
    assert model["beat_unit"] == "quarter"
    assert "bpm" not in model and "x" not in model and "pages" not in model
    assert model["staff_order"] == ["right", "left"]
    assert [n["id"] for n in model["notes"]] == ["r1", "r2", "r3", "l1", "r4"]
    assert set(model["active_note_ids"]) == {"r1", "r2", "r3", "r4"}
    assert json.loads(json.dumps(model)) == model


def test_real_meter_grid_ties_voices_chords_and_rests():
    model = make_model()
    measures = model["measures"]
    assert [(m["number"], m["start_beat"], m["end_beat"],
             tuple(m["meter"])) for m in measures] == [
                 (1, 0, 3, (3, 4)), (2, 3, 7, (4, 4))]
    symbols = model["notation_events"]
    assert all(s["staff"] in ("right", "left") for s in symbols)
    assert any(s["kind"] == "rest" and s["source_id"] is None for s in symbols)
    assert sum(s["kind"] == "note" and s["is_attack"] for s in symbols) == 5
    assert len({s["id"] for s in symbols}) == len(symbols)
    tied = [s for s in symbols if s["source_id"] == "l1"]
    assert len(tied) == 2
    assert tied[0]["beat"] == pytest.approx(2.5)
    assert tied[0]["tie_start"] and not tied[0]["tie_stop"]
    assert tied[1]["beat"] == pytest.approx(3)
    assert tied[1]["tie_stop"] and not tied[1]["tie_start"]
    assert not tied[1]["is_attack"]
    chord = [s for s in symbols if s["source_id"] in ("r1", "r2")]
    assert {s["beat"] for s in chord} == {0}
    assert sum(s["chord"] for s in chord) == 1


def test_grading_and_visual_score_share_exact_source_attacks():
    phrase, boundaries, meters = fixture()
    model = make_model("both")
    expected = {note["id"]: (note["onset_beats"], note["duration_beats"],
                              note["midi_pitch"]) for note in model["notes"]}
    assert expected == {
        n.source_id: (n.start - phrase.start, n.end - n.start, n.pitch)
        for n in phrase.notes}
    # The renderer's attack IDs and the evaluator's note events are the
    # identical source attacks, not a second set reconstructed from SVGs.
    attacks = {s["source_id"] for s in model["notation_events"]
               if s["kind"] == "note" and s["is_attack"]}
    assert attacks == set(expected)
    played = [PlayedNote(n.pitch, n.start * .75, n.end * .75)
              for n in phrase.notes]
    result = evaluate(phrase, "both", 80, played)
    assert len(result.notes) == len(model["active_note_ids"])
    assert result.clean
    assert len({s["voice"] for s in model["notation_events"]
                if s["staff"] == "right" and s["kind"] == "note"}) >= 2


def test_active_hand_is_a_filter_not_a_different_engraving():
    both = make_model("both")
    right = make_model("right")
    left = make_model("left")
    assert both["notes"] == right["notes"] == left["notes"]
    assert both["measures"] == right["measures"] == left["measures"]
    assert both["notation_events"] == right["notation_events"] == left["notation_events"]
    assert len(right["active_note_ids"]) == 4
    assert left["active_note_ids"] == ["l1"]


def test_cross_bar_pitch_spelling_and_key_changes_survive():
    phrase, boundaries, meters = fixture()
    notation = build_lesson_score(phrase, boundaries=boundaries,
        time_signatures=meters,
        key_signatures=(KeySignature(0, 0), KeySignature(3, 2)))
    model = build_score_model(notation, boundaries=boundaries)
    assert [m["keys"] for m in model["measures"]] == [
        {"right": 0, "left": 0}, {"right": 2, "left": 2}]
    assert all(e["spelling"]["step"] in "CDEFGAB" for e in
               model["notation_events"] if e["kind"] == "note")


def test_independent_staff_key_signatures_are_not_lost():
    phrase, boundaries, meters = fixture()
    notation = build_lesson_score(phrase, boundaries=boundaries,
        time_signatures=meters,
        key_signatures=(KeySignature(0, 2, "right"),
                        KeySignature(0, -1, "left")))
    model = build_score_model(notation, boundaries=boundaries)
    assert model["measures"][0]["keys"] == {"right": 2, "left": -1}


def test_real_score_model_preserves_32nd_and_64th_musicxml_events():
    """The live Python model must expose the short rhythmic values
    consumed by native Godot, not an inferred Verovio pixel layout."""
    events = (
        Note(0.0, .125, 72, 0, 0, "right", "short32a"),
        Note(.125, .25, 74, 0, 0, "right", "short32b"),
        Note(.25, .3125, 76, 0, 0, "right", "short64a"),
        Note(.3125, .375, 77, 0, 0, "right", "short64b"),
        Note(.375, .5, 79, 0, 0, "right", "short32c"),
    )
    phrase = Phrase(1, 1, 1, 0, 4, events)
    notation = build_lesson_score(
        phrase, boundaries=(0, 4), time_signatures=((0, 4, 4),))
    model = build_score_model(notation, boundaries=(0, 4))
    typed = {e["source_id"]: (e["note_type"], e["beat"])
             for e in model["notation_events"]
             if e["kind"] == "note" and e["is_attack"]}
    assert typed == {
        "short32a": ("32nd", 0),
        "short32b": ("32nd", .125),
        "short64a": ("64th", .25),
        "short64b": ("64th", .3125),
        "short32c": ("32nd", .375),
    }
    assert {n["id"] for n in model["notes"]} == set(typed)
    assert all(e["time_modification"] is None
               for e in model["notation_events"] if e["kind"] == "note")


def test_missing_or_duplicated_engraved_source_binding_is_rejected():
    phrase, boundaries, meters = fixture()
    notation = build_lesson_score(phrase, boundaries=boundaries,
                                  time_signatures=meters)
    bindings = notation.note_bindings.copy()
    bindings.pop(next(iter(bindings)))
    with pytest.raises(ValueError, match="lost its identity"):
        build_score_model(replace(notation, note_bindings=bindings),
                          boundaries=boundaries)


def test_engine_exposes_same_current_variant_without_touching_engraving(tmp_path):
    phrase, boundaries, meters = fixture()
    piece = Piece("Phase A", 80, phrase.notes, (phrase,),
                  bar_boundaries=boundaries, time_signatures=meters)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece)
        # There is deliberately no Verovio or SVG invocation in this call.
        model = engine.semantic_score()
        assert model["revision"] == engine.score_revision
        assert model["duration_beats"] == 7
        assert model["active_hand"] == engine.plan.hand
        assert engine._layout_cache is None
        assert len(model["notes"]) == len(engine.display_phrase().notes)
        assert len(model["active_note_ids"]) == sum(
            n.hand == engine.plan.hand for n in engine.display_phrase().notes)
    finally:
        engine.db.close()


def test_http_semantic_endpoint_is_json_and_does_not_trigger_png(tmp_path):
    phrase, boundaries, meters = fixture()
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(Piece("Phase A", 80, phrase.notes, (phrase,),
        bar_boundaries=boundaries, time_signatures=meters))
    handler = type("PhaseAScoreHandler", (Handler,), {
        "engine": engine, "log_message": lambda self, *args: None})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    runner = threading.Thread(target=httpd.serve_forever, daemon=True)
    runner.start()
    try:
        with urlopen(f"http://127.0.0.1:{httpd.server_port}/score/model",
                     timeout=3) as response:
            assert response.headers.get_content_type() == "application/json"
            payload = json.load(response)
        assert payload["schema"] == SCHEMA
        # The active learning variant may be a two-note skeleton, not the
        # full imported piece. Never leak eliminated tones into the renderer.
        assert len(payload["notes"]) == len(engine.display_phrase().notes)
        assert {n["id"] for n in payload["notes"]} == {
            n.source_id for n in engine.display_phrase().notes}
        assert engine._layout_cache is None
    finally:
        httpd.shutdown()
        httpd.server_close()
        runner.join(timeout=3)
        engine.db.close()
