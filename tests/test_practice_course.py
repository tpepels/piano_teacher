"""The normal lesson a learner gets after opening their MIDI file."""
from session_inputs import take
def test_open_lists_backward_growing_windows_then_a_separate_final(practice_session):
    session = practice_session()
    state = session.snapshot()
    assert (state["first_bar"], state["last_bar"], state["hand"]) == (1, 1, "right")
    assert state["flow"]["step"] == "listen"
    assert state["metronome"]
    steps = session.ask("lesson.overview")["steps"]
    windows = [(step["first_bar"], step["last_bar"]) for step in steps
               if step["hand"] == "right"]
    assert windows == [(1,1),(2,2),(1,2),(3,3),(2,3),(1,3),
                       (4,4),(3,4),(2,4),(1,4),(5,5),(4,5),(3,5),(2,5)]
    assert [step["hand"] for step in steps[:3]] == ["right", "left", "both"]
    assert (steps[-1]["kind"], steps[-1]["hand"], steps[-1]["first_bar"], steps[-1]["last_bar"]) == (
        "perform", "both", 1, 5)
    assert not any(step["completed"] for step in steps)


def test_empty_hand_is_skipped_without_inventing_credit(practice_session):
    session = practice_session(left=False)
    steps = session.ask("lesson.overview")["steps"]
    assert {step["hand"] for step in steps[:-1]} == {"right"}
    assert all(not step["completed"] for step in steps)
    assert steps[-1]["hand"] == "both"


def test_listen_then_free_waits_for_every_note_of_the_four_bar_window(practice_session):
    session = practice_session()
    session.select(1, 4)
    state = session.finish_listen()
    assert state["flow"]["step"] == "free"
    assert state["teaching"]["fragment"]["end_beat"] == 16
    assert state["teaching"]["target_count"] == 8
    waiting = session.tick(100)
    assert waiting["teaching"]["target_index"] == 0
    assert waiting["teaching"]["hint_reason"] != "wrong_note"
    for pitch in (72,79,73,80):
        session.strike(pitch)
        session.tick()
    halfway = session.snapshot()
    assert halfway["flow"]["step"] == "free"
    assert halfway["teaching"]["target_index"] == 4
    assert not halfway["running"]
    session.finish_free()
    tempo = session.ready_score()
    assert tempo["flow"]["step"] == "tempo"
    assert tempo["bpm"] == 40
    assert take(tempo)["transport_id"] == tempo["transport_id"]
    assert take(tempo)["count_in_beats"] == 4


def test_wrong_free_key_waits_and_correction_does_not_credit_future_notes(practice_session):
    session = practice_session()
    state = session.finish_listen()
    first = state["teaching"]["expected_notes"][0]
    session.reach_free_target()
    session.strike(61)
    wrong = session.snapshot()["teaching"]
    assert wrong["target_index"] == 0
    assert wrong["hint_reason"] == "wrong_note"
    assert {mark["id"] for mark in wrong["note_feedback"]} == {first["id"]}
    session.strike(first["pitch"])
    corrected = session.snapshot()["teaching"]
    assert corrected["target_index"] == 1
    assert not corrected["hint_visible"]
    assert corrected["expected_notes"][0]["id"] != first["id"]
    assert {mark["id"] for mark in corrected["note_feedback"]} == {first["id"]}


def test_clean_ladder_and_two_target_successes_advance_only_the_current_hand(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    # Precisely timed clean takes skip a step: 50%, +20%, +20%, target.
    for bpm in (40,56,72):
        assert session.ready_score()["bpm"] == bpm
        session.play_take()
        assert session.snapshot()["mastered"] == 0
    assert session.ready_score()["bpm"] == 80
    session.play_take()
    assert session.snapshot()["hand"] == "right"
    assert session.snapshot()["mastered"] == 0
    session.play_take()
    state = session.snapshot()
    assert state["hand"] == "left"
    assert state["flow"]["step"] == "listen"
    steps = session.ask("lesson.overview")["steps"]
    assert [step["completed"] for step in steps[:3]] == [True, False, False]
    reopened = session.open()
    assert reopened["hand"] == "left" and reopened["flow"]["step"] == "free"
    assert [step["completed"] for step in session.ask("lesson.overview")["steps"][:3]] == [True,False,False]


def test_failures_repeat_then_slow_and_two_at_floor_return_to_original_free(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    session.play_take()
    assert session.snapshot()["bpm"] == 56
    session.play_take(correct=False)
    assert session.snapshot()["bpm"] == 56
    session.play_take(correct=False)
    assert session.snapshot()["bpm"] == 48
    session.play_take(correct=False)
    assert session.snapshot()["bpm"] == 48
    session.play_take(correct=False)
    assert session.snapshot()["bpm"] == 40
    session.play_take(correct=False)
    assert session.snapshot()["bpm"] == 40
    state = session.play_take(correct=False)
    assert state["flow"]["step"] == "free"
    assert state["lesson_level"] == "original"
    assert state["mastered"] == 0


def test_half_speed_retains_the_original_slow_midi_target(practice_session):
    session = practice_session(bars=1, bpm=20)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert (state["original_bpm"], state["target_bpm"], state["bpm"]) == (20,20,10)
    assert state["count_in_beats"] == 4
    deadline = take(state)["deadline_ms"]/1000
    assert deadline-session.clock() >= 24
    session.clock.at = deadline-24
    assert session.snapshot()["countdown"] == 24


def test_failure_breaks_the_target_streak_before_the_hand_can_complete(practice_session):
    session = practice_session(bars=1)
    session.finish_listen()
    session.finish_free()
    for _ in range(3):
        session.play_take()
    session.play_take()
    session.play_take(correct=False)
    session.play_take()
    assert session.snapshot()["hand"] == "right"
    assert session.snapshot()["mastered"] == 0
    session.play_take()
    assert session.snapshot()["hand"] == "left"
    assert session.ask("lesson.overview")["steps"][0]["completed"]


def test_whole_original_final_requires_two_clean_target_takes(practice_session):
    session = practice_session()
    session.select(hand="both", final=True)
    source = session.ask("score.semantic")
    assert source["duration_beats"] == 20
    assert {note["hand"] for note in source["notes"]} == {"right","left"}
    session.open()
    session.finish_free()
    for bpm in (40,56,72,80):
        assert session.ready_score()["bpm"] == bpm
        session.play_take()
    assert not session.ask("lesson.overview")["steps"][-1]["completed"]
    session.play_take()
    assert session.ask("lesson.overview")["steps"][-1]["completed"]


def test_finishing_the_only_hand_starts_the_final_at_half_speed(practice_session):
    session = practice_session(bars=1, left=False)
    session.finish_listen()
    session.finish_free()
    for _ in range(5):
        session.play_take()
    final = session.ready_score()
    assert final["kind"] == "perform" and final["hand"] == "both"
    assert final["mode"] == "practice" and final["flow"]["step"] == "tempo"
    assert final["bpm"] == 40


def test_dim_neighbours_and_other_hand_are_not_active_performance_notes(practice_session):
    session = practice_session(bars=3)
    session.select(2,2)
    model = session.ask("score.semantic")
    active = {note["id"] for note in model["notes"]}
    assert active == set(model["active_note_ids"])
    assert all(note["hand"] == "right" and 0 <= note["onset_beats"] < 4
               for note in model["notes"])
    assert any(note["onset_beats"] < 0 for note in model["display_notes"])
    assert any(note["onset_beats"] >= 4 for note in model["display_notes"])
    assert any(note["hand"] == "left" for note in model["display_notes"])
    assert active < {note["id"] for note in model["display_notes"]}
