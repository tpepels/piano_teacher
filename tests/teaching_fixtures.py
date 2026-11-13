"""Authentic immutable teaching fixtures, never alternate production selectors."""
from dataclasses import replace
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note,Phrase,Piece
from piano_teacher.practice import Assessment,NoteAssessment
from piano_teacher.teaching_decisions import TeachingBinding,TeachingEvent,TeachingState,TeachingRouteFacts
from piano_teacher.diagnosis_policies import LearnerSnapshot
from piano_teacher.application.mistake_responses import resolve_mistake_policy


def teaching(*,status="correct",kind="full_result",automatic=True,mode="practice",warmup=False,bpm=80,streak=0):
    notes = tuple(Note(float(i),float(i)+.5,60+i,0,0,"right") for i in range(8))
    p = LearningPlan(Piece("teaching",120,notes,(Phrase(1,1,2,0.,8.,notes),),bar_boundaries=(0.,4.,8.)))
    p.set_bpm(bpm)
    p.streak=streak
    state = TeachingState(1,TeachingBinding("run","session","piece",p.identity,0,0,0,0),
        p.course_state(),resolve_mistake_policy("adaptive"),(),LearnerSnapshot(p.identity,()),None,
        TeachingRouteFacts(mode=mode,automatic=automatic,warmup=warmup,performed_bpm=bpm))
    event = TeachingEvent(1,"event",kind,assessment=Assessment(tuple(NoteAssessment(n,status) for n in p.active_variant.notes),0))
    return p,event,state
