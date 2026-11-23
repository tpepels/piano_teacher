"""The lesson domain: one owner for what the learner is practising.

Internals (never referenced outside the domain's own modules):
- source: SourceIdentity, the selected source, plan and score revision;
- cursor: LessonCursor, the opening beat and course guidance;
- decisions: TeachingDecisions, the only writer of lesson progress;
- guided: GuidedSession, untimed Free selection and return context;
- flow: PracticeFlowCourseSession, the Practice Flow course state.

Other modules read lesson facts through the read-only properties below and
change lesson state only through these named operations.
"""
from __future__ import annotations


class Lesson:
    def __init__(self, *, source, cursor, guided, flow):
        self._source = source
        self._cursor = cursor
        self._decisions = None
        self._guided = guided
        self._flow = flow

    def attach_decisions(self, decisions) -> None:
        """Bind the decision owner once, during composition."""
        if self._decisions is not None:
            raise RuntimeError("Lesson decisions are already attached")
        self._decisions = decisions


    # --- Source and plan identity ------------------------------------

    def advance_revision(self, *args, **kwargs):
        return self._source.advance_revision(*args, **kwargs)

    @property
    def fingerprint(self):
        return self._source.fingerprint

    def install_source(self, *args, **kwargs):
        return self._source.install(*args, **kwargs)

    @property
    def plan(self):
        return self._source.plan

    def publish_revision(self, *args, **kwargs):
        return self._source.publish_revision(*args, **kwargs)

    def replace_plan(self, *args, **kwargs):
        return self._source.replace_plan(*args, **kwargs)

    @property
    def revision(self):
        return self._source.revision



    # --- Lesson cursor -----------------------------------------------

    @property
    def course_guided(self):
        return self._cursor.course_guided

    @property
    def opening_beat(self):
        return self._cursor.opening_beat

    def select_opening(self, *args, **kwargs):
        return self._cursor.select_opening(*args, **kwargs)

    def set_course_guided(self, *args, **kwargs):
        return self._cursor.set_course_guided(*args, **kwargs)


    # --- Teaching decisions (the only progress writer) ---------------

    def apply_progress(self, *args, **kwargs):
        return self._decisions.apply_progress(*args, **kwargs)

    def decision_binding(self, *args, **kwargs):
        return self._decisions.binding(*args, **kwargs)

    def forget_source_decisions(self, *args, **kwargs):
        return self._decisions.source_installed(*args, **kwargs)

    def install_command(self, *args, **kwargs):
        return self._decisions.install_command(*args, **kwargs)

    def manual_effect(self, *args, **kwargs):
        return self._decisions.manual_effect(*args, **kwargs)

    def prepare_decision(self, *args, **kwargs):
        return self._decisions.prepare(*args, **kwargs)



    # --- Guided (untimed Free) selection -----------------------------

    def advance_guided(self, *args, **kwargs):
        return self._guided.advance(*args, **kwargs)

    def bind_guided_selection(self, *args, **kwargs):
        return self._guided.bind_selected(*args, **kwargs)

    def clear_guided_selection(self, *args, **kwargs):
        return self._guided.clear_selection(*args, **kwargs)

    def discard_guided_return(self, *args, **kwargs):
        return self._guided.discard_return(*args, **kwargs)

    def finish_guided_preparation(self, *args, **kwargs):
        return self._guided.finish_preparation(*args, **kwargs)

    @property
    def guided_beat_range(self):
        return self._guided.beat_range

    @property
    def guided_controller(self):
        return self._guided.controller

    def guided_display_phrase(self, *args, **kwargs):
        return self._guided.display_phrase(*args, **kwargs)

    @property
    def guided_fragment(self):
        return self._guided.fragment

    def guided_marks(self, *args, **kwargs):
        return self._guided.marks(*args, **kwargs)

    @property
    def guided_return_context(self):
        return self._guided.return_context

    @property
    def persistent_hints(self):
        return self._guided.persistent_hints

    def select_guided(self, *args, **kwargs):
        return self._guided.select(*args, **kwargs)

    def select_timed_return(self, *args, **kwargs):
        return self._guided.select_timed_return(*args, **kwargs)

    def set_hints(self, *args, **kwargs):
        return self._guided.set_hints(*args, **kwargs)

    def stop_guided(self, *args, **kwargs):
        return self._guided.stop(*args, **kwargs)


    # --- Practice Flow course session --------------------------------

    def execute_flow(self, *args, **kwargs):
        return self._flow.execute(*args, **kwargs)

    @property
    def flow_active(self) -> bool:
        """Practice Flow governs the selected source (not the warm-up)."""
        return self._flow.active(self.plan)

    def display_phrase(self, *, learning: bool):
        """The phrase shown on the staff: Free's window while learning."""
        plan = self.plan
        if plan is None:
            raise ValueError("Open a piece first")
        return self.guided_display_phrase(
            plan.active_phrase, plan.piece.bar_boundaries, active=learning)

    def flow_guided_entry(self, *args, **kwargs):
        return self._flow.guided_entry(*args, **kwargs)

    def flow_listen_again(self, *args, **kwargs):
        return self._flow.listen_again(*args, **kwargs)

    def flow_listen_finished(self, *args, **kwargs):
        return self._flow.listen_finished(*args, **kwargs)

    def flow_opening(self, *args, **kwargs):
        return self._flow.opening(*args, **kwargs)

    def flow_say(self, *args, **kwargs):
        return self._flow.say(*args, **kwargs)

    @property
    def flow_state(self):
        return self._flow.state

    def flow_status(self, *args, **kwargs):
        return self._flow.status(*args, **kwargs)

    def flow_tempo_entry(self, *args, **kwargs):
        return self._flow.tempo_entry(*args, **kwargs)

    def settle_flow_decision(self, *args, **kwargs):
        return self._flow.settle_decided(*args, **kwargs)
