"""Tempo changes reuse native notation; source changes retain readiness handoff."""
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


def test_recovery_keeps_feedback_then_reuses_native_score_for_same_chunk(harness):
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
    preparing = e.state()
    assert preparing["phase"] == "recovering"
    assert preparing['practice_preparation']['phase'] == 'preparing'
    measure = preparing['practice_preparation']['measure']
    assert (measure['start_beat'], measure['end_beat'], measure['duration_beats']) == (4, 8, 4)
    assert e.engraving() is original
    assert e.transport_id == transport
    now[0] = e.next_at + .01
    restarted = e.state()
    assert restarted["phase"] == "playing"
    assert restarted["revision"] == revision
    assert restarted["awaiting_score_revision"] is None
    assert restarted["play_from_beat"] == 8
    assert restarted["transport_id"] == transport + 1
    assert restarted["recovery_beat"] is None
    # The visual loop gap supplies preparation; a tempo-only retry neither
    # re-engraves notation nor prepends a second empty count-in measure.
    assert restarted["count_in_beats"] == 0
    assert restarted["clock_beat"] == pytest.approx(.01*72/60)
    assert e.engraving() is original


def test_clean_tempo_restore_reuses_native_score_without_advancing_lesson(harness):
    e, now = harness
    e.plan.bpm = 72
    expected_bpm = e.plan._next_automatic_bpm()
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
    assert waiting["bpm"] == expected_bpm
    assert e.plan.identity == identity
    assert waiting["phase"] == "playing"
    assert waiting["revision"] == revision
    assert waiting["awaiting_score_revision"] is None
    assert waiting["count_in_beats"] == 0
    assert waiting["play_from_beat"] == 0
    assert e.engraving() is original


def test_cache_reuses_source_ink_when_transport_bpm_changes(harness):
    e, now = harness
    original = e.engraving()
    # Recovery can change actual tempo without changing the selected target.
    e.plan.bpm = 72
    revised = e.engraving()
    # Recovery changes transport BPM, never printed horizontal distances.
    assert note_spacing(revised.layout) == pytest.approx(note_spacing(original.layout), rel=.001)
    assert e.plan.target_bpm == 80
    e.start()
    now[0] = e.run_at + 1
    e.control("restart")
    assert e.engraving() is revised
    reversing = e.state()
    assert reversing["phase"] == "recovering" and not reversing['running']
    assert reversing['practice_preparation']['phase'] == 'reverse'
    assert reversing['countdown'] == 0 and reversing['count_in_beats'] == 0
    measure = reversing['practice_preparation']['measure']
    assert (measure['start_beat'], measure['end_beat'], measure['duration_beats']) == (-4, 0, 4)
    assert reversing['transition_in_seconds'] == pytest.approx(e.feedback_seconds + 10/3)
    now[0] = e._preparation_at
    preparing = e.state()
    assert preparing['practice_preparation']['phase'] == 'preparing'
    assert preparing['visual_scroll_beat'] == pytest.approx(-4)
    assert preparing['transition_in_seconds'] == pytest.approx(10/3)
    now[0] = e.next_at + .01
    restarted = e.state()
    assert restarted['phase'] == 'playing' and restarted['count_in_beats'] == 0
    assert restarted['clock_beat'] == pytest.approx(.01*72/60)
    assert e.engraving() is revised


def test_manual_restart_during_recovery_keeps_native_score_and_visible_preparation(harness):
    e, now = harness
    original = e.engraving()
    e.start()
    now[0] = e.run_at + 16 * .75 + .02
    assert e.state()["phase"] == "recovering"
    revision = e.score_revision
    e.control("restart")
    waiting = e.state()
    assert waiting["phase"] == "recovering" and not waiting['running']
    assert waiting['practice_preparation']['phase'] == 'reverse'
    assert waiting["revision"] == revision
    assert waiting["awaiting_score_revision"] is None
    assert waiting["play_from_beat"] == 0
    assert waiting['practice_preparation']['source_from_beat'] == 0
    assert waiting['practice_preparation']['measure']['duration_beats'] == 4
    assert waiting['transition_in_seconds'] == pytest.approx(
        e.feedback_seconds + 4*60/waiting['bpm'])
    assert waiting['countdown'] == 0 and waiting['count_in_beats'] == 0
    now[0] = e._preparation_at + 2*60/waiting['bpm']
    preparing = e.state()
    assert preparing['practice_preparation']['phase'] == 'preparing'
    assert preparing['visual_scroll_beat'] == pytest.approx(-2)
    assert not preparing['running'] and e.engraving() is original
    now[0] = e.next_at + .01
    restarted = e.state()
    assert restarted['phase'] == 'playing' and restarted['play_from_beat'] == 0
    assert restarted['count_in_beats'] == 0 and restarted['revision'] == revision
    assert e.engraving() is original


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
