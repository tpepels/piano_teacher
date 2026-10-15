"""Only the active generated stage is rendered and scored."""
import pytest
from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_score import LessonScore
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.score import EngravedScore
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.server import PracticeEngine


def piece():
    notes=(Note(0,1,60,0,0,"right"),Note(0,1,64,0,0,"right"),
           Note(0,1,67,0,0,"right"),Note(1,2,69,0,0,"right"),
           Note(0,1,48,1,0,"left"),Note(0,1,52,1,0,"left"))
    return Piece("Lesson",100,notes,(Phrase(1,1,2,0,8,notes),))


def test_three_clean_runs_then_reveal_more_chord_notes():
    p=LearningPlan(piece())
    assert p.hand=="right" and p.active_variant.level=="skeleton"
    assert len(p.active_phrase.notes)==2
    p.set_bpm(100)
    for _ in range(3):
        message=p.apply_result(correct=2,total=2)
    assert "outline" in message and p.active_variant.level=="outline"
    assert p.streak==0 and len(p.active_phrase.notes)==3
    p.set_bpm(100)
    for _ in range(3):
        p.apply_result(correct=3,total=3)
    assert p.active_variant.level=="original"
    p.set_bpm(100)
    for _ in range(3):
        p.apply_result(correct=4,total=4)
    assert p.hand=="left" and p.active_variant.level=="skeleton"


def test_failure_resets_current_stage_streak():
    p=LearningPlan(piece())
    p.set_bpm(100)
    p.apply_result(correct=2,total=2)
    assert p.streak==1
    p.apply_result(correct=1,total=2)
    assert p.streak==0 and p.variant_index==0


def test_renderer_uses_only_required_variant_not_original(tmp_path,monkeypatch):
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(piece())
    e.score=object() # Source object would fail if passed to renderer.
    try:
        def fake_renderer(notation,first,last,hand,*,total_beats,bpm):
            assert isinstance(notation,LessonScore)
            assert notation.phrase.notes==e.plan.active_phrase.notes
            assert len(notation.phrase.notes)==2 and total_beats==8
            assert bpm == 40
            return EngravedScore(("<svg/>",), {"pages":1,"anchors":[{"beat":0,"x":.5}],
                "notes":[{"pitch":n.pitch,"beat":n.start-notation.phrase.start}
                         for n in notation.phrase.notes]})
        monkeypatch.setattr(server,"render_layout",fake_renderer)
        assert e.engraving().pages==("<svg/>",)
        phrase=e.plan.active_phrase
        played=[PlayedNote(n.pitch,n.start*.6,n.end*.6) for n in phrase.notes]
        result=evaluate(phrase,"right",100,played)
        assert result.clean and len(result.notes)==2
        assert len(e.plan.exercise.phrase.notes)>2
    finally:
        e.db.close()


def test_stage_change_increments_score_revision(tmp_path):
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(piece())
    e.plan.set_bpm(100)
    e.fingerprint="stage-change"
    try:
        for _ in range(3):
            e.pending_result=type("R",(),{"correct":2,"extra_notes":0,"notes":[1,2]})()
            e._commit_pending()
        assert e.plan.active_variant.level=="outline"
        assert e.score_revision==1
    finally:
        e.db.close()


def test_stage_resume_is_persisted(tmp_path):
    first=PracticeEngine(tmp_path,enable_midi=False)
    first.plan=LearningPlan(piece())
    first.plan.variant_index=1
    first.plan.streak=2
    first.plan.bpm=65
    first.fingerprint="saved-stage"
    first._save()
    first.db.close()
    second=PracticeEngine(tmp_path,enable_midi=False)
    try:
        second.plan=LearningPlan(piece())
        second.fingerprint="saved-stage"
        second._restore()
        assert second.plan.active_variant.level=="outline"
        assert second.plan.streak==2 and second.plan.bpm==65
        assert second.state()["required_notes"]==3
        assert second.state()["lesson_level"]=="outline"
    finally:
        second.db.close()
