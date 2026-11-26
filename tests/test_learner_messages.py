"""The learner is told why a key earned nothing (owner request 2026-11-25:
"check when the user needs information and give it to the user clearly")."""


def flash(state):
    return state["screen"]["flash"]


def test_a_key_in_the_count_in_is_silent_warmup(practice_session):
    session = practice_session(bars=2)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["phase"] == "count_in"
    before = flash(state)["id"]
    start = state["playback_timeline"]["current"]["deadline_ms"]/1000
    count_in = state["playback_timeline"]["current"]["count_in_beats"]*60/state["bpm"]
    session.clock.at = start-count_in+.2      # far into the count-in
    session.strike(72)
    after = session.tick()
    assert flash(after)["id"] == before
    assert after["midi_notes"] == 0


def test_a_key_before_the_free_target_arrives_says_wait(practice_session):
    session = practice_session(bars=2)
    session.finish_listen()
    state = session.snapshot()
    guided = state["playback_timeline"]["guided"]
    assert guided["deadline_at_ms"]/1000 > session.clock.at   # still travelling
    before = flash(state)["id"]
    session.strike(state["teaching"]["expected_notes"][0]["pitch"])
    after = session.tick()
    assert after["teaching"]["target_index"] == 0
    assert flash(after)["id"] == before+1
    assert flash(after)["text"] == "Wait until the note reaches the line"


def test_the_first_tempo_reads_fifty_percent_even_when_rounded(practice_session):
    # 50% of an odd target tempo is rounded to a whole BPM; the status line
    # still names the rule ("Tempo 50%"), not the arithmetic (52%).
    session = practice_session(bars=2, bpm=31, chords=True)
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["bpm"] == 16
    assert state["screen"]["status"].endswith("Tempo 50%")
