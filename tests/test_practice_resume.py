"""Saved learning resumes on original notes without inventing mastery."""
import sqlite3

import pytest


@pytest.mark.parametrize("selection", [(1,1,"right"),(1,4,"left"),(None,None,"both")],
                         ids=["first-window","expanded-left","final"])
def test_reopen_warms_up_the_same_complete_window_and_hand(practice_session, selection):
    session = practice_session()
    first, last, hand = selection
    if first is not None:
        session.select(first, last, hand)
    else:
        session.select(hand="both", final=True)
    before = session.snapshot()
    session.open()
    reopened = session.ready_score()
    assert reopened["flow"]["step"] == "free"
    assert (reopened["first_bar"], reopened["last_bar"], reopened["hand"]) == (
        before["first_bar"], before["last_bar"], hand)
    assert reopened["teaching"]["target_index"] == 0
    assert reopened["teaching"]["fragment"]["end_beat"] == (last or 5)*4
    session.finish_free()
    state = session.ready_score()
    assert state["flow"]["step"] == "tempo"
    assert state["bpm"] == 40
    assert state["mastered"] == 0


def test_partial_chord_and_held_key_are_not_saved_as_learning(practice_session):
    session = practice_session(bars=1, chords=True)
    state = session.finish_listen()
    target = state["teaching"]["expected_notes"]
    assert len(target) == 3
    session.key(target[0]["pitch"])
    assert session.snapshot()["teaching"]["target_index"] == 0
    session.open()
    reopened = session.ready_score()["teaching"]
    assert reopened["target_index"] == 0
    assert not reopened["heard_pitches"]
    assert len(reopened["expected_notes"]) == 3
    assert session.snapshot()["mastered"] == 0


def test_explicit_final_learn_teaches_the_whole_piece_before_half_speed(practice_session):
    session = practice_session()
    session.select(hand="both", final=True)
    free = session.ready_score()
    assert free["mode"] == "learn" and free["phase"] == "guided_wait"
    assert free["flow"]["step"] == "free"
    assert free["teaching"]["target_count"] == 10
    session.finish_free()
    tempo = session.ready_score()
    assert tempo["mode"] == "practice" and tempo["bpm"] == 40


def floor_return(session):
    session.finish_free()
    session.play_take(correct=False)
    return session.play_take(correct=False)


def test_second_floor_return_survives_reopen_and_announces_a_real_aid(practice_session):
    session = practice_session(bars=1, chords=True)
    session.finish_listen()
    original = session.ask("score.semantic")
    first_return = floor_return(session)
    assert first_return["lesson_level"] == "original"
    assert not first_return["guided_recovery"]
    session.open()
    second_return = floor_return(session)
    assert "Simplified:" in second_return["flow"]["message"]
    aid = session.ask("score.semantic")
    assert len(aid["notes"]) < len(original["notes"])
    assert second_return["mastered"] == 0
    session.finish_free()
    returned = session.ready_score()
    assert returned["mode"] == "learn"
    assert returned["flow"]["step"] == "free"
    assert {note["id"] for note in session.ask("score.semantic")["notes"]} == {
        note["id"] for note in original["notes"]}
    assert returned["mastered"] == 0
    session.finish_free()
    assert session.ready_score()["bpm"] == 40


def test_no_genuine_aid_keeps_original_free_and_other_hands_have_their_own_return_count(practice_session):
    session = practice_session(bars=1, single=True)
    session.finish_listen()
    floor_return(session)
    second = floor_return(session)
    assert second["flow"]["step"] == "free"
    assert second["lesson_level"] == "original"
    assert "Simplified:" not in second["flow"]["message"]
    session.select(1, 1, "left")
    session.command("listen")
    session.finish_listen()
    left = floor_return(session)
    assert left["hand"] == "left"
    assert left["lesson_level"] == "original"
    assert left["mastered"] == 0


def test_old_positional_progress_migrates_without_awarding_new_window_credit(practice_session):
    session = practice_session()
    fingerprint = session.snapshot()["piece_fingerprint"]
    session.close()
    database = session.data/"progress.db"
    database.unlink()
    with sqlite3.connect(database) as old:
        old.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER)")
        old.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", (fingerprint,99,"left",120,9))
        old.execute("CREATE TABLE mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY(fingerprint,exercise))")
        old.execute("INSERT INTO mastery VALUES (?,?,?)", (fingerprint,"learn:1-2:right",80))
    state = session.open()
    assert (state["first_bar"], state["last_bar"], state["hand"]) == (1,1,"right")
    assert state["target_bpm"] == 80
    assert state["mastered"] == 0
    assert not any(step["completed"] for step in session.ask("lesson.overview")["steps"])
