"""Tempo-dependent notation changes only after the preceding feedback is read."""
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.server import PracticeEngine


@pytest.fixture
def harness(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    notes = tuple(Note(float(i), i + .5, 60 + i % 5, 0, 0, "right")
                  for i in range(16))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(Piece("Tempo layout", 100, notes,
                                    (Phrase(1, 1, 4, 0, 16, notes),)))
    engine.plan.set_bpm(80)
    engine.midi_port = object()
    try:
        yield engine, now
    finally:
        engine.db.close()


def note_spacing(layout):
    """Read consecutive actual noteheads in units of the five-line staff."""
    first, second = layout["notes"][:2]
    assert first["system"] == second["system"]
    system = next(s for s in layout["systems"] if s["system"] == first["system"])
    page = first["page"]
    staff_gap = (system["staff_lines"][1] - system["staff_lines"][0]) * layout["heights"][page]
    return (second["x"] - first["x"]) * layout["widths"][page] / staff_gap


def test_recovery_keeps_old_feedback_then_waits_for_new_spacing_and_retries_same_chunk(harness):
    e, now = harness
    original = e.engraving()
    revision = e.score_revision
    e.start()
    transport = e.transport_id
    for i in range(8):
        e.recorder.presses.append(PlayedNote(60 + i % 5, i * .75, (i + .5) * .75))
    now[0] = e.run_at + 16 * .75 + .02
    failed = e.state()
    assert failed["phase"] == "recovering"
    assert failed["bpm"] == 72 and failed["recovery_beat"] == 8
    assert failed["revision"] == revision
    assert failed["feedback_marks"]
    # Polling either endpoint while reading mistakes must keep their geometry.
    now[0] = e.next_at - .01
    assert e.state()["phase"] == "recovering"
    assert e.engraving() is original
    assert e.transport_id == transport
    now[0] = e.next_at + .01
    loading = e.state()
    assert loading["phase"] == "loading"
    assert loading["revision"] == revision + 1
    assert loading["awaiting_score_revision"] == revision + 1
    assert loading["recovery_beat"] == 8
    widened = e.engraving()
    assert note_spacing(widened.layout) > note_spacing(original.layout)
    # Rendering time cannot consume the retry's count-in or queue revisions.
    now[0] += 120
    assert e.state()["phase"] == "loading"
    assert e.score_revision == revision + 1 and e.transport_id == transport
    e.control("score_ready", revision=revision)
    assert e.state()["phase"] == "loading"
    e.control("score_ready", revision=revision + 1)
    restarted = e.state()
    assert restarted["phase"] == "count_in"
    assert restarted["play_from_beat"] == 8
    assert restarted["transport_id"] == transport + 1
    assert restarted["recovery_beat"] is None
    assert 0 < restarted["countdown"] <= 4
    assert e.engraving() is widened


def test_clean_tempo_restore_waits_for_spacing_without_advancing_lesson(harness):
    e, now = harness
    e.plan.bpm = 72
    original = e.engraving()
    identity = e.plan.identity
    revision = e.score_revision
    e.start()
    phrase = e.plan.active_phrase
    e.recorder.presses[:] = [PlayedNote(n.pitch, n.start * 60 / 72, n.end * 60 / 72)
                            for n in phrase.notes]
    now[0] = e.run_at + 16 * 60 / 72 + .3
    assert e.state()["phase"] == "feedback"
    assert e.engraving() is original
    now[0] = e.next_at + .01
    waiting = e.state()
    assert waiting["bpm"] == 79
    assert e.plan.identity == identity
    assert waiting["phase"] == "loading"
    assert waiting["revision"] == revision + 1
    assert waiting["awaiting_score_revision"] == revision + 1
    restored = e.engraving()
    assert note_spacing(restored.layout) < note_spacing(original.layout)
    e.control("score_ready", revision=revision + 1)
    assert e.state()["phase"] == "count_in"
    assert e.state()["play_from_beat"] == 0


def test_cache_follows_actual_bpm_and_restart_keeps_fresh_clock(harness):
    e, now = harness
    original = e.engraving()
    # Recovery can change actual tempo without changing the selected target.
    e.plan.bpm = 72
    widened = e.engraving()
    assert note_spacing(widened.layout) > note_spacing(original.layout)
    assert e.plan.target_bpm == 80
    e.start()
    now[0] = e.run_at + 1
    e.control("restart")
    assert e.engraving() is widened
    assert e.state()["phase"] == "count_in"
    assert e.state()["countdown"] == pytest.approx(10 / 3)


def test_manual_restart_during_recovery_renders_before_starting_fresh_count_in(harness):
    e, now = harness
    e.engraving()
    e.start()
    now[0] = e.run_at + 16 * .75 + .02
    assert e.state()["phase"] == "recovering"
    revision = e.score_revision
    e.control("restart")
    waiting = e.state()
    assert waiting["phase"] == "loading"
    assert waiting["revision"] == revision + 1
    e.engraving()
    now[0] += 90
    e.control("score_ready", revision=revision + 1)
    assert e.state()["phase"] == "count_in"
    assert e.state()["play_from_beat"] == 0
    assert 0 < e.state()["countdown"] <= 4


def test_pickup_count_in_uses_source_meter_instead_of_short_first_bar(harness):
    e, _ = harness
    notes = (Note(0, .5, 60, 0, 0, "right"), Note(1, 1.5, 62, 0, 0, "right"))
    e.plan = LearningPlan(Piece("Three quarter pickup", 100, notes,
                               (Phrase(1, 1, 2, 0, 4, notes),),
                               bar_boundaries=(0, 1, 4), time_signatures=((0, 3, 4),)))
    e.plan.set_bpm(80)
    e.start()
    state = e.state()
    assert state["count_in_meter"] == [3, 4]
    assert state["count_in_bar_beats"] == 3
    assert state["count_in_beats"] == 3
    assert state["countdown"] == pytest.approx(2.25)
