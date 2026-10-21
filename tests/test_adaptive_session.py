"""Timing, boundary rewind, slowdown and partial-mastery integration."""
import pytest
from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.server import PracticeEngine


def piece(bars=4):
    notes=tuple(Note(float(i),float(i)+.5,60+i,0,0,"right") for i in range(bars*4))
    return Piece("Recovery",100,notes,(Phrase(1,1,bars,0,bars*4,notes),))


def boot(tmp_path,monkeypatch,bars):
    now=[10.0]
    monkeypatch.setattr(server.time,"monotonic",lambda:now[0])
    engine=PracticeEngine(tmp_path,enable_midi=False)
    engine.plan=LearningPlan(piece(bars))
    engine.midi_port=object()
    engine.start()
    return engine,now


def test_tempo_capped_lead_and_five_errors_slow_ten_percent(tmp_path,monkeypatch):
    e,now=boot(tmp_path,monkeypatch,2)
    try:
        assert e.state()["lead_in_bars"]==1
        assert e.state()["count_in_beats"]==2.5
        assert e.state()["clock_beat"]==pytest.approx(-2.5)
        start=e.run_at
        sec=60/e.plan.bpm
        for i in range(3):
            e.recorder.presses.append(PlayedNote(60+i,i*sec,(i+.5)*sec))
        now[0]=start+8*sec+.03
        state=e.state()
        assert state["phase"]=="recovering"
        assert state["recovery_beat"]==0
        assert state["bpm"]==36
        assert state["streak"]==0 and state["mastered"]==0
        now[0]=e.next_at+.01
        waiting=e.state()
        assert waiting["phase"]=="loading"
        e.control("score_ready",revision=waiting["revision"])
        assert e.state()["phase"]=="count_in"
        assert e.state()["clock_beat"]==pytest.approx(-2.0)
    finally:
        e.db.close()


def test_complete_current_chunk_before_rewinding(tmp_path,monkeypatch):
    e,now=boot(tmp_path,monkeypatch,4)
    try:
        start=e.run_at
        sec=60/e.plan.bpm
        for i in range(8):
            e.recorder.presses.append(PlayedNote(60+i,i*sec,(i+.5)*sec))
        now[0]=start+8*sec+.01
        assert e.state()["phase"]=="playing"
        now[0]=start+15*sec
        assert e.state()["phase"]=="playing"
        now[0]=start+16*sec+.01
        assert e.state()["phase"]=="recovering"
        assert e.state()["recovery_beat"]==8
        now[0]=e.next_at+.01
        waiting=e.state()
        assert waiting["phase"]=="loading"
        e.control("score_ready",revision=waiting["revision"])
        assert e.state()["play_from_beat"]==8
        assert e.state()["clock_beat"]==pytest.approx(-2.0)
    finally:
        e.db.close()


def test_partial_retry_never_grants_full_mastery(tmp_path,monkeypatch):
    e,now=boot(tmp_path,monkeypatch,4)
    try:
        e.start(from_beat=8)
        start=e.run_at
        sec=60/e.plan.bpm
        for i in range(8,16):
            e.recorder.presses.append(PlayedNote(60+i,(i-8)*sec,(i-7.5)*sec))
        now[0]=start+8*sec+.22
        state=e.state()
        assert state["phase"]=="recovering"
        assert state["mastered"]==0 and state["streak"]==0
        assert state["recovery_beat"]==0
        now[0]=e.next_at+.01
        assert e.state()["play_from_beat"]==0
    finally:
        e.db.close()


def test_stop_cancels_pending_retry(tmp_path,monkeypatch):
    e,now=boot(tmp_path,monkeypatch,2)
    try:
        now[0]=e.run_at+8*60/e.plan.bpm+.1
        assert e.state()["phase"]=="recovering"
        e.control("stop")
        now[0]+=100
        assert e.state()["phase"]=="ready"
    finally:
        e.db.close()


def test_godot_has_virtual_lead_in_notation():
    from pathlib import Path
    script=(Path(__file__).resolve().parents[1]/"godot"/"main.gd").read_text()
    assert "lead_width_px" in script and "lead_first" in script
    assert 'score_overlay.lead_beats = lead_beats' in script
    assert 'score_overlay.lead_meter = last_state.get("count_in_meter"' in script
    assert 'target_x = viewport.x * 0.42 - note_x * displayed_width' in script


def test_custom_target_recovers_instead_of_running_to_original_midi_speed(tmp_path, monkeypatch):
    e, now = boot(tmp_path, monkeypatch, 2)
    try:
        e.control("tempo", bpm=80)
        e.start()
        now[0] = e.run_at + 8 * 60 / e.plan.bpm + .1
        assert e.state()["bpm"] == 72
        assert e.plan.target_bpm == 80
        e.plan.apply_result(correct=8, total=8)
        assert e.plan.bpm == 73  # Next even rung after a recovery at 72 BPM.
        while e.plan.bpm < 80:
            e.plan.apply_result(correct=8, total=8)
        assert e.plan.bpm == 80
    finally:
        e.db.close()


def test_target_bpm_survives_engine_reload(tmp_path, monkeypatch):
    e, now = boot(tmp_path, monkeypatch, 2)
    try:
        e.fingerprint = "tempo-persistence"
        e.plan.set_bpm(80)
        e.plan.bpm = 72
        e._save()
    finally:
        e.db.close()
    other = PracticeEngine(tmp_path, enable_midi=False)
    try:
        other.plan = LearningPlan(piece(2))
        other.fingerprint = "tempo-persistence"
        other._restore()
        assert other.plan.target_bpm == 80
        assert other.plan.bpm == 72
    finally:
        other.db.close()


def test_existing_database_migrates_without_losing_progress(tmp_path):
    import sqlite3
    with sqlite3.connect(tmp_path / "progress.db") as database:
        database.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER)")
        database.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", ("old-piece",0,"right",64,1))
    engine=PracticeEngine(tmp_path,enable_midi=False)
    try:
        engine.plan=LearningPlan(piece(2))
        engine.fingerprint="old-piece"
        engine._restore()
        assert engine.plan.bpm==64
        assert engine.plan.target_bpm==100
        assert engine.plan.streak==1
        engine._save()
        assert "target_bpm" in {r[1] for r in engine.db.execute("PRAGMA table_info(sessions)")}
    finally:
        engine.db.close()


def test_leaving_practice_stops_scheduled_retries():
    from pathlib import Path
    code=(Path(__file__).resolve().parents[1]/"godot"/"main.gd").read_text()
    assert '"recovering", "loading"' in code
    assert '_send_action({"action": "stop"})' in code


def test_three_quarter_time_has_six_lead_in_beats(tmp_path,monkeypatch):
    now=[20.0]
    monkeypatch.setattr(server.time,"monotonic",lambda:now[0])
    notes=(Note(0,1,60,0,0,"right"),Note(4,5,62,0,0,"right"))
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(Piece("3/4",100,notes,(Phrase(1,1,2,0,6,notes),)))
    try:
        e.start()
        assert e.state()["lead_in_bars"]==1
        assert e.state()["count_in_beats"]==2.5
        assert e.state()["clock_beat"]==pytest.approx(-2.5)
    finally:
        e.db.close()
