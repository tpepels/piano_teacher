"""Bounded real MusicXML: engraving, Listen, grading and provisional MIDI
feedback consume one selected stage and one piecewise TempoMap.

No physical MIDI device, soundcard, Godot launch or corpus audit is assumed.
"""
from pathlib import Path

import pytest

from piano_teacher.application.listen_session import ListenSelection, ListenSession
from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
from piano_teacher.demo import DemoAudio
from piano_teacher.exercise_contracts import OriginalTiming, TwoPhaseTempo
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.measure_grid import phrase_grid
from piano_teacher.practice import PlayedNote
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.timed_assessment import assess_timed_window, timed_live_marks


FIXTURE = Path(__file__).parent / "fixtures/connector_pixels/beams/score.musicxml"


class CapturingAudio:
    def __init__(self, path):
        self.path = path
        self.rendered = []

    def render(self, variant, bpm):
        self.rendered.append((variant, bpm))
        return DemoAudio(self.path, variant.phrase.end * 60 / bpm,
                         0, 8000, "source-verified")


def test_real_score_shared_timeline_from_notation_through_listen_and_feedback(tmp_path):
    piece = load_musicxml(FIXTURE, bpm=80)
    phrase = piece.phrases[0]
    assert phrase.end-phrase.start == 4
    variant = ExerciseVariant("two-phase-tempo", phrase,
                              tuple(range(len(phrase.notes))))
    tempo = TwoPhaseTempo(speed_fraction=.5).generate(
        OriginalTiming().transform(variant), 60)
    assert [(segment.start_beat, segment.end_beat, segment.bpm)
            for segment in tempo.segments] == [(0,2,30),(2,4,60)]

    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path/"preprocessed"))
    selected = ScoreSelection(piece, phrase, "both", "shared-timeline", 7,
                              "beam-source", transformed_rhythm=False)
    model = artifacts.source_model(selected)
    notes = {entry["id"]: entry for entry in model["notes"]}
    assert set(notes) == {note.source_id for note in phrase.notes}
    assert all(notes[note.source_id]["onset_beats"] ==
               pytest.approx(note.start-phrase.start) for note in phrase.notes)

    capture = CapturingAudio(tmp_path/"captured.wav")
    session = ListenSession(tmp_path/"demo", cache=capture)
    token = session.prepare(ListenSelection(
        variant, 60, "shared-timeline", 7, piece.bar_boundaries,
        piece.time_signatures, tempo))
    session.thread.join(timeout=3)
    assert not session.thread.is_alive()
    assert session.snapshot()["audio_available"]
    assert session.snapshot()["duration_seconds"] == pytest.approx(6.0)
    assert session.snapshot()["canonical_source_ids"] == [
        note.source_id for note in phrase.notes]
    (warped, render_bpm), = capture.rendered
    assert render_bpm == 60
    assert [n.source_id for n in warped.notes] == [
        n.source_id for n in phrase.notes]
    for source, rendered in zip(phrase.notes, warped.notes):
        # The renderer uses fixed-BPM coordinates, but each audible
        # attack/release must equal the shaped clock in real seconds.
        assert (rendered.start-phrase.start)*60/render_bpm == pytest.approx(
            tempo.seconds_at(source.start-phrase.start))
        assert (rendered.end-phrase.start)*60/render_bpm == pytest.approx(
            tempo.seconds_at(source.end-phrase.start))

    played = [
        PlayedNote(n.pitch, tempo.seconds_at(n.start-phrase.start),
                   tempo.seconds_at(n.end-phrase.start))
        for n in phrase.notes
    ]
    assert assess_timed_window(phrase, "both", tempo, played).clean

    right = sorted((n for n in phrase.notes if n.hand == "right"),
                   key=lambda n: n.start)
    after_change = next(n for n in right if abs(n.start-phrase.start-2)<1e-7)
    view = LiveInputView()
    view.receive(
        pitch=after_change.pitch, is_on=True,
        now=100+tempo.seconds_at(after_change.start-phrase.start),
        phrase=phrase, hand="right", bpm=60, from_beat=0,
        run_at=100, running=True, paused=False, preview=False,
        mode="practice", transport_id=9, tempo_map=tempo)
    assert view.events[-1]["source_id"] == after_change.source_id
    assert view.events[-1]["status"] == "on_time"

    layout_notes = [
        {"id": f"ink-{index}", "source_id": n.source_id,
         "pitch": n.pitch, "hand": n.hand,
         "beat": n.start-phrase.start, "source_beat": n.start-phrase.start,
         "is_attack": True, "segment_index": 0,
         "page": 0, "x": (index+1)/(len(phrase.notes)+1), "y": .5}
        for index, n in enumerate(phrase.notes)
    ]
    layout = {"mapping_schema":"source-note-v1", "pages":1,
              "beats":phrase.end-phrase.start, "notes":layout_notes,
              "attack_map": {n["source_id"]: n["id"] for n in layout_notes},
              "continuation_map": {}}
    missing = right[5]
    taken = [n for n in played if n.pitch != missing.pitch]
    marks = timed_live_marks(
        phrase, "right", tempo, taken, from_beat=0,
        elapsed_seconds=tempo.seconds_at(3.7),
        grid=phrase_grid(phrase,piece.bar_boundaries), layout=layout)
    missed = [m for m in marks
              if m["source_id"] == missing.source_id and m["status"] == "missed"]
    assert missed
    assert all(m["note_id"] == layout["attack_map"][m["source_id"]]
               for m in marks)
    assert session.acknowledge_audio(token)
    assert session.acknowledge_score(7)
    assert session.begin_playback(7) is not None
