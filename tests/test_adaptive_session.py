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


def test_eight_beat_lead_and_five_errors_slow_ten_percent(tmp_path,monkeypatch):
    e,now=boot(tmp_path,monkeypatch,2)
    try:
        assert e.state()["lead_in_bars"]==2
        assert e.state()["count_in_beats"]==8
        assert e.state()["clock_beat"]==pytest.approx(-8)
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
        assert e.state()["phase"]=="count_in"
        assert e.state()["clock_beat"]==pytest.approx(-8)
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
        assert e.state()["play_from_beat"]==8
        assert e.state()["clock_beat"]==pytest.approx(-8)
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
    assert 'cursor["x"] = float(cursor.get("x", 0.0)) + clock / lead_beats * fraction' in script
    assert "if _transport_beat_now() < 0.0:" in script


def test_custom_target_recovers_instead_of_running_to_original_midi_speed(tmp_path, monkeypatch):
    e, now = boot(tmp_path, monkeypatch, 2)
    try:
        e.control("tempo", bpm=80)
        e.start()
        now[0] = e.run_at + 8 * 60 / e.plan.bpm + .1
        assert e.state()["bpm"] == 72
        assert e.plan.target_bpm == 80
        e.plan.apply_result(correct=8, total=8)
        assert e.plan.bpm == 79
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
