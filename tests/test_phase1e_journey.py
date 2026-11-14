"""A full timed teaching journey: fail -> slow -> recover -> 3 clean -> advance.

Exercises are generated from the source notes. No device, font or Godot mock
is necessary to exercise transport decisions, score revisions or mastery.
"""
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.engraving.engraving import EngravedScore
from piano_teacher.server import PracticeEngine
from test_seamless_stage_runway import Prepared


def music():
    notes=tuple(Note(float(i),i+.5,pitch,0,0,"right")
                for i in range(8) for pitch in (60,64,67))
    return Piece("Journey",100,notes,(Phrase(1,1,2,0,8,notes),))


def test_harder_outline_starts_fresh_after_three_clean_mastery_passes():
    """Mastering a reduced chord skeleton does not prove outline speed."""
    plan = LearningPlan(music())
    plan.set_bpm(80)
    assert plan.active_variant.level == "skeleton"
    easier = plan.identity
    required = len(plan.active_phrase.notes)
    for _ in range(3):
        plan.apply_result(correct=required,total=required)
    assert plan.active_variant.level == "outline"
    assert len(plan.active_phrase.notes) > required
    assert plan.stage_tempos[easier] == 80
    assert easier in plan.transferable_tempos
    assert plan.carried_bpm() is None
    assert plan.bpm == plan.start_bpm == 40


@pytest.mark.parametrize("changed,carried",[
    ("same-source",80),("new-rhythm",None),
])
def test_earned_tempo_only_crosses_stage_boundaries_with_identical_source_ink(
        changed,carried):
    """A new technique with identical written notes can reuse actual speed.

    A same-sized rearrangement, including unchanged source IDs, must restart:
    the learner has not proved the new rhythm.
    """
    from dataclasses import replace
    from piano_teacher import teaching_course

    plan=LearningPlan(music())
    base=plan.course_state()
    first=base.stages[0]
    key=base.key
    original=first.variant
    if changed=="new-rhythm":
        notes=(replace(original.notes[0],
                       end=original.notes[0].end+.125), *original.notes[1:])
        phrase=replace(original.phrase,notes=notes)
    else:
        phrase=original.phrase
    distinct=replace(first,variant=replace(original,level=changed,phrase=phrase))
    sequences=dict(base.definition.stage_sequences)
    sequences[(base.exercise.key,base.hand)]=(first,distinct,*base.stages[1:])
    definition=replace(base.definition,stage_sequences=sequences)
    progress=replace(base.progress,cursor=(0,0,1),bpm=80,target_bpm=80,
                     stage_tempos=((key,80),),transferable_tempos=(key,))
    current=replace(base,definition=definition,progress=progress)
    assert teaching_course.carried_bpm(current)==carried
    assert teaching_course.stage_start_bpm(current)==(80 if carried else 40)


def test_failure_slowdown_recovery_and_three_clean_mastery(tmp_path,monkeypatch):
    t=[100.0]
    monkeypatch.setattr(server.time,"monotonic",lambda:t[0])
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(music())
    e.fingerprint="complete-journey"
    e.plan.set_bpm(80)
    e.midi.port=object()  # In-process test only: no MIDI simulation endpoint.
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
        assert e.state()["count_in_beats"]==4
        # Five missing required pitches: wait until the two-bar boundary,
        # then enter recovery instead of interrupting the current measure.
        t[0]=e.visual_transport.run_at+7*60/80
        assert e.state()["phase"]=="playing"
        t[0]=e.visual_transport.run_at+8*60/80+.02
        failed=e.state()
        assert failed["phase"]=="recovering"
        assert failed["bpm"]==72
        assert failed["recovery_beat"]==0
        assert failed["mastered"]==0 and failed["streak"]==0
        t[0]=e.visual_transport.next_at+.01
        waiting=e.state()
        assert waiting["phase"]=="playing"
        assert waiting["awaiting_score_revision"] is None
        assert waiting["revision"] == failed["revision"]
        assert waiting["count_in_beats"] == 0
        # The next lesson step is pre-engraved and acknowledged before the
        # third clean take (continuous handoff): the score is replaced at the
        # take boundary without a loading gap. An unprepared stage is covered
        # by test_phase1_score_handoff and test_seamless_stage_runway.
        e.future_score=Prepared(e)
        selection,_number=e._next_stage_selection()
        assert e.acknowledge_preloaded_stage(
            stage_key=selection.stage_key,revision=selection.revision)["accepted"]
        # Clean takes climb successive equal BPM rungs; only target-speed
        # takes count toward the three repetitions needed for mastery.
        for _ in range(20):
            before=e.plan.bpm
            expected_bpm = e.plan._next_automatic_bpm() if before < e.plan.target_bpm else e.plan.target_bpm
            phrase=e.plan.active_phrase
            seconds=60.0/before
            assert e.recorder is not None
            e.recorder.presses[:]=[
                PlayedNote(n.pitch,(n.start-phrase.start)*seconds,
                           (n.end-phrase.start)*seconds) for n in phrase.notes
            ]
            t[0]=e.visual_transport.run_at+8*seconds+.3
            final_take=before >= e.plan.target_bpm and e.plan.streak == 2
            feedback=e.state()
            # A fully prepared next step may advance on the first post-grading
            # tick (_finish... "prepared_on_time"); every other take shows feedback.
            if not final_take:
                assert feedback["phase"]=="feedback"
                assert feedback["feedback_marks"]
                assert all(mark["status"]=="correct" for mark in feedback["feedback_marks"])
            t[0]=e.visual_transport.next_at+.01
            after=e.state()
            if e.plan.active_variant.level == "outline":
                # A harder generated level starts at the novice pace.
                assert expected_bpm==80
                # The prepared harder level starts on its reading runway.
                assert after["phase"] in ("count_in","playing")
                assert after["bpm"] == e.plan.start_bpm
                break
            assert after["bpm"]==expected_bpm
            assert after["phase"]=="playing"
            assert after["revision"] == waiting["revision"]
            assert after["awaiting_score_revision"] is None
            assert after["count_in_beats"] == 0
        else:
            pytest.fail("Three clean target-speed repeats did not unlock the next level")
        assert e.plan.active_variant.level=="outline"
        assert after["awaiting_score_revision"] is None
        assert after["revision"]==selection.revision
        assert after["lesson_step"]==2
        assert after["lesson_steps_mastered"]==1
        assert after["required_notes"]>8
    finally:
        e.midi.port=None
        e.db.close()
