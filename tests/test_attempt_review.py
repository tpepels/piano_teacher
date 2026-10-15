"""Actual review grouping and bounded retry using the production practice engine."""
from __future__ import annotations

import time

import pytest

from piano_teacher.practice import Assessment, NoteAssessment, PlayedNote
from piano_teacher.server import PracticeEngine
from piano_teacher.warmups import materialize


def engine_for_review(tmp_path):
    path = materialize("warmup:chords", tmp_path / "music")
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.load(str(path), warmup=True)
    return engine


def test_review_identifies_actual_expected_and_wrong_pitches_by_measure(tmp_path):
    engine = engine_for_review(tmp_path)
    try:
        phrase = engine.plan.active_phrase
        notes = [n for n in phrase.notes if n.hand == engine.plan.hand]
        assert len(notes) >= 3
        wrong, missed = notes[0], notes[2]
        actual_wrong_pitch = wrong.pitch + 1
        assessment = Assessment((
            NoteAssessment(wrong, "wrong", actual_wrong_pitch),
            NoteAssessment(missed, "missed"),
        ), 1, (PlayedNote(80, 0.06, .18),))
        review = engine._performance_review(phrase, assessment)
        assert review["wrong"] == 1
        assert review["missed"] == 1
        assert review["extra_notes"] == 1
        assert review["sections"]
        all_issues = [issue for section in review["sections"] for issue in section["issues"]]
        wrong_issue = next(issue for issue in all_issues if issue["status"] == "wrong")
        assert wrong_issue["pitch"] == wrong.pitch
        assert wrong_issue["played_pitch"] == actual_wrong_pitch
        assert wrong_issue["played_name"] != wrong_issue["name"]
        assert wrong_issue["source_id"] == wrong.source_id
        assert any(issue["status"] == "missed" and issue["pitch"] == missed.pitch
                   for issue in all_issues)
        assert any(issue["status"] == "extra" and issue["pitch"] == 80
                   for issue in all_issues)
    finally:
        engine.db.close()


def test_retry_must_match_real_reviewed_two_bar_section(tmp_path):
    engine = engine_for_review(tmp_path)
    try:
        phrase = engine.plan.active_phrase
        note = next(n for n in phrase.notes if n.hand == engine.plan.hand)
        review = engine._performance_review(phrase, Assessment(
            (NoteAssessment(note, "missed"),), 0))
        target = review["sections"][0]
        engine.mode = "perform"
        engine.performance_summary = review
        engine.review_stage_identity = engine.plan.identity
        for invalid in ({"first_bar": -1, "last_bar": 2},
                        {"first_bar": target["first_bar"], "last_bar": target["last_bar"]+1},
                        {"first_bar": str(target["first_bar"]), "last_bar": target["last_bar"]}):
            with pytest.raises(ValueError):
                engine.control("review_retry", **invalid)
            assert engine.mode == "perform"
            assert engine.performance_summary is review
        engine.control("review_retry", first_bar=target["first_bar"],
                       last_bar=target["last_bar"])
        assert engine.mode == "practice"
        assert engine.open_from_beat == target["start_beat"]
        assert engine.review_end_beat == target["end_beat"]
        assert engine.retry_range["first_bar"] == target["first_bar"]
        assert engine.awaiting_score_revision is None
        assert not engine.running
        assert engine.performance_summary is None
    finally:
        engine.db.close()


def test_bounded_retry_stops_at_selected_chunk_and_cannot_grant_mastery(tmp_path):
    engine = engine_for_review(tmp_path)
    try:
        phrase = engine.plan.active_phrase
        note = next(n for n in phrase.notes if n.hand == engine.plan.hand)
        review = engine._performance_review(phrase, Assessment(
            (NoteAssessment(note, "missed"),), 0))
        target = review["sections"][0]
        engine.mode = "perform"
        engine.performance_summary = review
        engine.review_stage_identity = engine.plan.identity
        engine.control("review_retry", first_bar=target["first_bar"],
                       last_bar=target["last_bar"])
        engine.midi_port = object()  # isolated MIDI test device; no real instrument
        engine.engraving()  # real canonical source-note geometry
        engine.start()
        assert not engine.preview_only
        assert engine.review_end_beat < phrase.end-phrase.start
        assert engine.state()["duration"] == pytest.approx(
            (target["end_beat"]-target["start_beat"]) * 60 / engine.plan.bpm)
        engine.run_at = time.monotonic() - 2000
        final = engine.state()
        assert final["phase"] == "review"
        assert final["performance_summary"]["missed"] > 0
        assert engine.review_end_beat is None
        assert engine.plan.mastered == {}
        assert not engine.running
        assert engine.next_at == 0
    finally:
        engine.db.close()


def test_assessment_wrong_note_tracks_actual_key_without_changing_accuracy():
    from piano_teacher.music import Note, Phrase
    from piano_teacher.practice import evaluate
    note = Note(0, 2, 60, 0, 0, "right")
    phrase = Phrase(1, 1, 1, 0, 4, (note,))
    scored = evaluate(phrase, "right", 60, [PlayedNote(62, 0.02, .5)])
    assert scored.correct == 0
    assert scored.extra_notes == 0
    assert scored.notes[0].status == "wrong"
    assert scored.notes[0].played_pitch == 62
