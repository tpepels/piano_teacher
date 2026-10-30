"""Bounded real-source verification of retimed notation and tempo recovery.

No Verovio pixel audit, Godot startup, physical MIDI or external network calls.
These fixtures are checked in under tests/fixtures.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.exercise_contracts import (
    DottedPairTiming, OriginalTiming, TwoPhaseTempo,
)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.pieces import import_piece
from piano_teacher.measure_grid import phrase_grid
from piano_teacher.music import Note, Phrase, Piece, source_note_id
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.timed_assessment import (
    assess_timed_window, timed_live_marks, timed_rolling_recovery,
)

FIXTURES = Path(__file__).parent / "fixtures" / "connector_pixels"


def source_fixture(name):
    pytest.importorskip("music21")
    piece, _ = import_piece(FIXTURES / name / "score.musicxml")
    phrase = Phrase(1, 1, len(piece.bar_boundaries)-1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    return piece, phrase


@pytest.mark.parametrize("filename", ("beam16", "tuplets", "beam-chords"))
def test_real_musicxml_retains_original_notes_and_sound_duration(filename, tmp_path):
    piece, phrase = source_fixture(filename)
    original = ExerciseVariant("original", phrase, tuple(range(len(phrase.notes))))
    plan = DottedPairTiming().transform(original)
    assert [e.source_index for e in plan.events] == list(range(len(phrase.notes)))
    transformed = replace(phrase, notes=tuple(
        replace(note, start=phrase.start+event.exercise_start,
                end=phrase.start+event.exercise_end)
        for note, event in zip(phrase.notes, plan.events)))
    assert tuple(note.source_id for note in transformed.notes) == tuple(
        note.source_id for note in phrase.notes)
    assert len(transformed.notes) == len(phrase.notes)
    assert plan.duration_beats == pytest.approx(phrase.end-phrase.start)
    assert all(phrase.start <= n.start < n.end <= phrase.end+1e-7
               for n in transformed.notes)

    selected = ScoreSelection(
        piece, transformed, "both", "course:3:real:dotted-long-short:fixture", 1,
        "real-fixture", transformed_rhythm=True)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path / "preprocessed"))
    model = artifacts.source_model(selected)
    mapped = {note["id"]: note for note in model["notes"]}
    assert set(mapped) == {
        source_note_id(note, i) for i, note in enumerate(phrase.notes)}
    for i, note in enumerate(transformed.notes):
        event = mapped[source_note_id(note, i)]
        assert event["onset_beats"] == pytest.approx(note.start-phrase.start)
        assert event["duration_beats"] == pytest.approx(note.end-note.start)
    assert len(model["notation_events"]) > 0


def test_real_beamed_sixteenths_change_rhythm_but_chords_do_not():
    _, line = source_fixture("beam16")
    notes = [note for note in line.notes if note.hand == "right"]
    original = ExerciseVariant("original", replace(line, notes=tuple(notes)),
                               tuple(range(len(notes))))
    timing = DottedPairTiming().transform(original)
    assert any(abs(e.exercise_start-(n.start-line.start)) > 1e-7
               for e, n in zip(timing.events, notes))
    _, chorded = source_fixture("beam-chords")
    notes = [note for note in chorded.notes if note.hand == "right"]
    original = ExerciseVariant("original", replace(chorded, notes=tuple(notes)),
                               tuple(range(len(notes))))
    result = DottedPairTiming().transform(original)
    assert all(abs(e.exercise_start-(n.start-chorded.start)) < 1e-7
               for e, n in zip(result.events, notes))


def long_phrase():
    notes = tuple(Note(beat, beat+.5, 60+i, 0, 0, "right", f"src-{i}", "v1")
                  for i, beat in enumerate(range(0, 16, 1)))
    phrase = Phrase(1, 1, 4, 0, 16, notes)
    piece = Piece("Four bars", 60, notes, (phrase,),
                  bar_boundaries=(0,4,8,12,16))
    variant = ExerciseVariant("original", phrase, tuple(range(len(notes))))
    tempo = TwoPhaseTempo().generate(OriginalTiming().transform(variant), 60)
    return piece, phrase, tempo


def test_tempo_recovery_recognizes_actual_errors_in_last_two_source_bars():
    piece, phrase, tempo = long_phrase()
    # First two measures are perfect; last two have six missing attacks.
    played = [PlayedNote(n.pitch, tempo.seconds_at(n.start),
                         tempo.seconds_at(n.end)) for n in phrase.notes[:10]]
    first = timed_rolling_recovery(
        phrase, "right", tempo, played, from_beat=0, end_beat=8,
        grid=phrase_grid(phrase, piece.bar_boundaries), threshold=5)
    assert first is None
    second = timed_rolling_recovery(
        phrase, "right", tempo, played, from_beat=0, end_beat=16,
        grid=phrase_grid(phrase, piece.bar_boundaries), threshold=5)
    assert second is not None
    assert second.errors >= 5
    assert second.restart_beat == 8
    assert second.end_beat == 16
    assert second.missed >= 5


def test_tempo_recovery_supports_partial_retry_after_shaping_boundary():
    piece, phrase, tempo = long_phrase()
    origin = tempo.seconds_at(8)
    late_half = [PlayedNote(n.pitch,
                            tempo.seconds_at(n.start)-origin,
                            tempo.seconds_at(n.end)-origin)
                 for n in phrase.notes[8:]]
    assert assess_timed_window(
        phrase, "right", tempo, late_half, from_beat=8).clean
    assert tempo.from_beat(8).seconds_at(8) == pytest.approx(
        tempo.seconds_at(16)-tempo.seconds_at(8))
    assert timed_rolling_recovery(
        phrase, "right", tempo, late_half, from_beat=8, end_beat=16,
        grid=phrase_grid(phrase, piece.bar_boundaries), threshold=5) is None


def test_shaped_grader_distinguishes_early_late_and_wrong_pitch():
    _, phrase, tempo = long_phrase()
    presses = [
        PlayedNote(n.pitch, tempo.seconds_at(n.start),
                   tempo.seconds_at(n.end))
        for n in phrase.notes
    ]
    assert assess_timed_window(phrase, "right", tempo, presses).clean
    delayed = list(presses)
    delayed[11] = PlayedNote(delayed[11].pitch,
                             delayed[11].onset+.18, delayed[11].release+.18)
    assessed = assess_timed_window(phrase, "right", tempo, delayed)
    assert assessed.notes[11].status == "late"
    wrong = list(presses)
    wrong[11] = PlayedNote(49, wrong[11].onset, wrong[11].release)
    assessed = assess_timed_window(phrase, "right", tempo, wrong)
    assert assessed.notes[11].status == "wrong"
    assert assessed.extra_notes == 0


def test_extra_key_after_last_note_invalidates_shaped_full_take():
    _, phrase, tempo = long_phrase()
    pressed = [PlayedNote(n.pitch, tempo.seconds_at(n.start),
                          tempo.seconds_at(n.end)) for n in phrase.notes]
    pressed.append(PlayedNote(15, tempo.duration_seconds+.3,
                              tempo.duration_seconds+.5))
    result = assess_timed_window(phrase, "right", tempo, pressed)
    assert not result.clean
    assert result.extra_notes == 1


def test_shaped_live_feedback_uses_original_notehead_identity():
    piece, phrase, tempo = long_phrase()
    layout_notes = []
    for i, note in enumerate(phrase.notes):
        layout_notes.append({
            "id": f"ink-{i}", "source_id": note.source_id,
            "pitch": note.pitch, "hand": note.hand, "beat": note.start,
            "source_beat": note.start, "is_attack": True, "segment_index": 0,
            "page": 0, "x": (i+1)/20, "y": .5,
        })
    layout = {
        "mapping_schema": "source-note-v1", "pages": 1, "beats": 16,
        "notes": layout_notes,
        "attack_map": {item["source_id"]: item["id"] for item in layout_notes},
        "continuation_map": {},
    }
    # At one second after beat 10, note 10 has passed its matching grace,
    # but no note 10 was played. The preceding note was correct.
    played = [PlayedNote(n.pitch, tempo.seconds_at(n.start),
                         tempo.seconds_at(n.end)) for n in phrase.notes[:10]]
    elapsed = tempo.seconds_at(11.5)
    marks = timed_live_marks(
        phrase, "right", tempo, played, from_beat=0,
        elapsed_seconds=elapsed, grid=phrase_grid(phrase, piece.bar_boundaries),
        layout=layout)
    missed = {m["source_id"] for m in marks if m["status"] == "missed"}
    assert "src-10" in missed
    assert "src-9" not in missed
    assert all(m["note_id"] == layout["attack_map"][m["source_id"]]
               for m in marks)
