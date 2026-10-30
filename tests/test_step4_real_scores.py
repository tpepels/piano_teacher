"""Bounded MusicXML proof of Coda chordification and source identity.

Runs the repository's checked-in sixteenth-note score; no Verovio pixel audit.
"""
from dataclasses import replace
from pathlib import Path

from piano_teacher.exercise_contracts import ChordBlockTiming
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.music import Phrase, source_note_id
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model


FIXTURE = (Path(__file__).parent / "fixtures" / "connector_pixels" /
           "beam16" / "score.musicxml")


def test_chordified_real_sixteenths_keep_every_source_attack_and_grading_time():
    piece = load_musicxml(FIXTURE, bpm=80)
    source = Phrase(1, 1, len(piece.bar_boundaries)-1,
                    piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    variant = ExerciseVariant("original", source, tuple(range(len(piece.notes))))
    timed = ChordBlockTiming().transform(variant)
    assert timed.name == "coda-chord-blocks"
    assert len(timed.events) == len(piece.notes)
    assert any(abs(event.source_start-source.start-event.exercise_start) > 1e-6
               for event in timed.events)
    phrase = replace(source, notes=tuple(
        replace(note, start=source.start+event.exercise_start,
                end=source.start+event.exercise_end)
        for note, event in zip(source.notes, timed.events)))
    score = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml, retimed_source=True)
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    expected = {source_note_id(note, i) for i, note in enumerate(source.notes)}
    rendered = {note["id"] for note in model["notes"]}
    assert rendered == expected
    onsets = {note["id"]: note["onset_beats"] for note in model["notes"]}
    for index, note in enumerate(phrase.notes):
        assert onsets[source_note_id(source.notes[index], index)] == (
            note.start-phrase.start)
    assert tuple(note.start for note in piece.notes) == tuple(
        note.start for note in source.notes)
