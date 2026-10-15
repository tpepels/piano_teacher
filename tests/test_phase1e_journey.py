"""A full timed teaching journey: fail -> slow -> recover -> 3 clean -> advance.

Exercises are generated from the source notes. No device, font or Godot mock
is necessary to exercise transport decisions, score revisions or mastery.
"""
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.score import EngravedScore
from piano_teacher.server import PracticeEngine


def music():
    notes=tuple(Note(float(i),i+.5,pitch,0,0,"right")
                for i in range(8) for pitch in (60,64,67))
    return Piece("Journey",100,notes,(Phrase(1,1,2,0,8,notes),))


def test_failure_slowdown_recovery_and_three_clean_mastery(tmp_path,monkeypatch):
    t=[100.0]
    monkeypatch.setattr(server.time,"monotonic",lambda:t[0])
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(music())
    e.fingerprint="complete-journey"
    e.plan.set_bpm(80)
    e.midi_port=object()  # In-process test only: no MIDI simulation endpoint.
    def fake_engraving():
        phrase=e.plan.active_phrase
        return EngravedScore(("<svg/>",),{
            "pages":1,"beats":8,
            "anchors":[{"beat":0,"page":0,"system":"s","x":.15,"top":.1,"bottom":.9}],
            "notes":[{"id":f"n{i}","pitch":n.pitch,"beat":n.start-phrase.start,
                      "x":(.15+.08*i),"y":.4,"page":0,"system":"s"}
                     for i,n in enumerate(phrase.notes)],
        })
    monkeypatch.setattr(e,"engraving",fake_engraving)
    try:
        assert e.plan.active_variant.level=="skeleton"
        assert len(e.plan.active_phrase.notes)==8
        e.start()
        assert e.state()["phase"]=="count_in"
        assert e.state()["count_in_beats"]==8
        # Five missing required pitches: wait until the two-bar boundary,
        # then enter recovery instead of interrupting the current measure.
        t[0]=e.run_at+7*60/80
        assert e.state()["phase"]=="playing"
        t[0]=e.run_at+8*60/80+.02
        failed=e.state()
        assert failed["phase"]=="recovering"
        assert failed["bpm"]==72
        assert failed["recovery_beat"]==0
        assert failed["mastered"]==0 and failed["streak"]==0
        t[0]=e.next_at+.01
        assert e.state()["phase"]=="count_in"
        assert e.state()["count_in_beats"]==8
        # Two clean performances restore the selected 80 BPM target,
        # without counting towards three target-speed clean repeats.
        for expected_bpm in (79,80,80,80,80):
            before=e.plan.bpm
            phrase=e.plan.active_phrase
            seconds=60.0/before
            assert e.recorder is not None
            e.recorder.presses[:]=[
                PlayedNote(n.pitch,(n.start-phrase.start)*seconds,
                           (n.end-phrase.start)*seconds) for n in phrase.notes
            ]
            t[0]=e.run_at+8*seconds+.3
            feedback=e.state()
            assert feedback["phase"]=="feedback"
            assert feedback["feedback_marks"]
            assert all(mark["status"]=="correct" for mark in feedback["feedback_marks"])
            t[0]=e.next_at+.01
            after=e.state()
            assert after["bpm"]==expected_bpm
            if after["phase"]=="loading":
                assert expected_bpm==80
                break
            assert after["phase"]=="count_in"
        else:
            pytest.fail("Three clean target-speed repeats did not unlock the next level")
        assert e.plan.active_variant.level=="outline"
        assert after["awaiting_score_revision"]==after["revision"]
        assert after["lesson_step"]==2
        assert after["lesson_steps_mastered"]==1
        revision=after["revision"]
        transport=e.transport_id
        # A stale visual acknowledgement cannot start a different lesson.
        e.control("score_ready",revision=revision-1)
        assert e.state()["phase"]=="loading"
        e.control("score_ready",revision=revision)
        started=e.state()
        assert started["phase"]=="count_in"
        assert started["transport_id"]==transport+1
        assert started["required_notes"]>8
    finally:
        e.midi_port=None
        e.db.close()
