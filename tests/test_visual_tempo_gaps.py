"""The visual practice timeline is the same scheduled map as MIDI assessment."""
from __future__ import annotations

import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def test_shaped_tempo_then_full_rest_has_no_new_time_origin(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    notes = (Note(0, .5, 60, 0, 0, "right"),
             Note(3, 3.5, 62, 0, 0, "right"),
             Note(4, 4.5, 64, 0, 0, "right"),
             Note(7, 7.5, 65, 0, 0, "right"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    piece = Piece("Shaped rest boundary", 80, notes, (phrase,),
                  bar_boundaries=(0, 4, 8),
                  time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece, tempo_strategy="two-phase-tempo")
    engine.plan.bpm = 80
    try:
        engine.start()
        downbeat = engine.run_at
        # Authoritative 64 BPM for beats 0..4 and 80 BPM for 4..8;
        # four silent quarter beats then advance at 80 BPM.
        expected_source_seconds = 4 * 60 / 64 + 4 * 60 / 80
        assert expected_source_seconds == pytest.approx(6.75)
        clock[0] = downbeat + 6.0
        playing = engine.state()
        assert playing["visual_run_at_ms"] == pytest.approx(downbeat * 1000)
        assert playing["visual_scroll_beat"] == pytest.approx(7.0)
        segments = playing["visual_tempo_segments"]
        assert [(v["start_beat"], v["end_beat"], v["bpm"])
                for v in segments] == [(0, 4, 64), (4, 8, 80), (8, 12, 80)]
        assert playing["tempo_segments"] == segments[:-1]

        clock[0] = downbeat + expected_source_seconds + .3
        gap = engine.state()
        assert gap["phase"] == "preview_gap"
        assert gap["visual_scroll_beat"] == pytest.approx(8.4)
        assert gap["visual_scroll_speed"] == pytest.approx(80/60)
        assert gap["visual_run_at_ms"] == pytest.approx(downbeat * 1000)
        assert gap["visual_tempo_segments"] == segments

        clock[0] = downbeat + expected_source_seconds + 2.0
        gap_later = engine.state()
        assert gap_later["visual_scroll_beat"] == pytest.approx(8 + 2*80/60)
        assert gap_later["visual_scroll_speed"] == pytest.approx(80/60)

        deadline = downbeat + expected_source_seconds + 4*60/80
        assert engine.next_at == pytest.approx(deadline)
        clock[0] = deadline + .1
        replay = engine.state()
        assert replay["phase"] == "playing"
        assert replay["count_in_beats"] == 0
        assert replay["visual_scroll_beat"] == pytest.approx(12 + .1*64/60)
        assert replay["play_from_beat"] == 0
    finally:
        engine.db.close()

def test_failed_shaped_take_rewinds_from_the_true_visual_position(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    notes = tuple(Note(i, i+.25, 60+i, 0, 0, "right") for i in (0, 2, 4, 6))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    piece = Piece("Shaped failed take", 80, notes, (phrase,),
                  bar_boundaries=(0, 4, 8),
                  time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece, tempo_strategy="two-phase-tempo")
    engine.plan.bpm = 80
    engine.midi.port = object()  # Exercise grading without physical MIDI events.
    try:
        engine.start()
        assert not engine.preview_only
        clock[0] = engine.run_at + 6.75 + .25
        result = engine.state()
        assert result["phase"] == "recovering"
        assert engine._visual_rewind_from == pytest.approx(8+.25*80/60)
    finally:
        engine.db.close()
