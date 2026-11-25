"""The transport domain: one owner for playback timing, intent and admission.

Internals (never referenced outside this module):
- timeline: VisualTransport, the musical timeline facts;
- session: PlaybackSession, the session's playback intent and take lifecycle;
- admission: PlaybackCoordinator, the physical intent/receipt ledger.

Other modules read transport facts through the read-only properties below
and change transport state only through these named operations.
"""
from __future__ import annotations


class Transport:
    def __init__(self, *, timeline, session, admission):
        self._timeline = timeline
        self._session = session
        self._admission = admission

    def reset_for_stop(self) -> None:
        """Return timeline and session intent to idle after Stop."""
        self._timeline.reset_for_stop()
        self._session.reset_for_stop()


    # --- Timeline ----------------------------------------------------


    @property
    def musical_timeline(self):
        return self._timeline.musical

    @property
    def ink_ahead_beats(self) -> float:
        return self._timeline.ink_ahead_beats

    def report_ink_ahead(self, beats) -> None:
        self._timeline.report_ink_ahead(beats)

    @property
    def free_travel_beats(self) -> float:
        return self._timeline.free_travel_beats

    def report_free_travel(self, beats) -> None:
        self._timeline.report_free_travel(beats)


    @property
    def continuation_pending(self) -> bool:
        return self._timeline.continuation_pending

    def await_continuation(self) -> None:
        self._timeline.await_continuation()

    @property
    def next_boundary_beat(self):
        return self._timeline.next_boundary_beat

    @property
    def paused(self):
        return self._timeline.paused

    @property
    def paused_at(self):
        return self._timeline.paused_at

    @property
    def pending_rewind(self):
        return self._timeline.pending_rewind

    @property
    def play_from_beat(self):
        return self._timeline.play_from_beat

    @property
    def run_at(self):
        return self._timeline.run_at

    @property
    def visual_gap_beats(self):
        return self._timeline.visual_gap_beats

    def advance_boundary(self, *args, **kwargs):
        return self._timeline.advance_boundary(*args, **kwargs)

    def cancel_continuation(self, *args, **kwargs):
        return self._timeline.cancel_continuation(*args, **kwargs)

    def clear_grading_floor(self, *args, **kwargs):
        return self._timeline.clear_grading_floor(*args, **kwargs)


    def finish_rewind(self, *args, **kwargs):
        return self._timeline.finish_rewind(*args, **kwargs)

    def grading_is_frozen(self, *args, **kwargs):
        return self._timeline.grading_is_frozen(*args, **kwargs)

    def musical_seconds(self, *args, **kwargs):
        return self._timeline.musical_seconds(*args, **kwargs)

    def prepare_rewind(self, *args, **kwargs):
        return self._timeline.prepare_rewind(*args, **kwargs)

    def select_opening(self, *args, **kwargs):
        return self._timeline.select_opening(*args, **kwargs)

    @property
    def auto(self):
        return self._session.auto

    @property
    def awaiting_score_revision(self):
        return self._session.awaiting_score_revision

    @property
    def count_in_bar_beats(self):
        return self._session.count_in_bar_beats

    @property
    def count_in_beats(self):
        return self._session.count_in_beats

    @property
    def count_in_meter(self):
        return self._session.count_in_meter

    @property
    def mode(self):
        return self._session.mode

    @property
    def pause_context(self):
        return self._session.pause_context

    @property
    def running(self):
        return self._session.running

    @property
    def transport_id(self):
        return self._session.transport_id

    def apply_continuation(self, *args, **kwargs):
        return self._session.apply_continuation(*args, **kwargs)

    def apply_feedback_fault(self, *args, **kwargs):
        return self._session.apply_feedback_fault(*args, **kwargs)

    def authorization(self, *args, **kwargs):
        return self._session.authorization(*args, **kwargs)

    def await_score(self, *args, **kwargs):
        return self._session.await_score(*args, **kwargs)

    def begin_listen_if_ready(self, *args, **kwargs):
        return self._session.begin_listen_if_ready(*args, **kwargs)

    def begin_timed(self, *args, **kwargs):
        return self._session.begin_timed(*args, **kwargs)

    def capture_guided_start(self, *args, **kwargs):
        return self._session.capture_guided_start(*args, **kwargs)

    def capture_start(self, *args, **kwargs):
        return self._session.capture_start(*args, **kwargs)

    def continue_course(self, *args, **kwargs):
        return self._session.continue_course(*args, **kwargs)

    def facts(self, *args, **kwargs):
        return self._session.facts(*args, **kwargs)

    def finish_full_passage(self, *args, **kwargs):
        return self._session.finish_full_passage(*args, **kwargs)

    def finish_resume(self, *args, **kwargs):
        return self._session.finish_resume(*args, **kwargs)

    def finish_take(self, *args, **kwargs):
        return self._session.finish_take(*args, **kwargs)

    def freeze_after_fault(self, *args, **kwargs):
        return self._session.freeze_after_fault(*args, **kwargs)

    def open_take(self, *args, **kwargs):
        return self._session.open_take(*args, **kwargs)

    def pause(self, *args, **kwargs):
        return self._session.pause(*args, **kwargs)

    def prepare_admitted_continuation(self, *args, **kwargs):
        return self._session.prepare_admitted_continuation(*args, **kwargs)


    def require_authorized_start(self, *args, **kwargs):
        return self._session.require_authorized_start(*args, **kwargs)

    def resume_suspended_admission(self, *args, **kwargs):
        return self._session.resume_suspended_admission(*args, **kwargs)

    def resume_timeline(self, *args, **kwargs):
        return self._session.resume_timeline(*args, **kwargs)

    def score_acknowledged(self, *args, **kwargs):
        return self._session.score_acknowledged(*args, **kwargs)

    def select_exposure(self, *args, **kwargs):
        return self._session.select_exposure(*args, **kwargs)

    def select_source(self, *args, **kwargs):
        return self._session.select_source(*args, **kwargs)

    def source_revised(self, *args, **kwargs):
        return self._session.source_revised(*args, **kwargs)

    def start_listen(self, *args, **kwargs):
        return self._session.start_listen(*args, **kwargs)

    def stop_automatic(self, *args, **kwargs):
        return self._session.stop_automatic(*args, **kwargs)

    def wait_for_player(self, *args, **kwargs):
        return self._session.wait_for_player(*args, **kwargs)


    # --- Physical admission ------------------------------------------

    @property
    def intent(self):
        return self._admission.intent

    @property
    def active_segment_id(self) -> str:
        return self._admission.active_segment_id

    def advance(self, *args, **kwargs):
        return self._admission.advance(*args, **kwargs)

    def segment_id_for(self, *args, **kwargs):
        return self._admission.segment_id_for(*args, **kwargs)

    def intent_matches(self, *args, **kwargs):
        return self._admission.intent_matches(*args, **kwargs)

    def clear_failure(self, *args, **kwargs):
        return self._admission.clear_failure(*args, **kwargs)

    def authorize(self, *args, **kwargs):
        return self._admission.authorize(*args, **kwargs)

    def automatic_request_blocked(self, *args, **kwargs):
        return self._admission.automatic_request_blocked(*args, **kwargs)

    def fail(self, *args, **kwargs):
        return self._admission.fail(*args, **kwargs)

    def invalidate(self, *args, **kwargs):
        return self._admission.invalidate(*args, **kwargs)

    def request(self, *args, **kwargs):
        return self._admission.request(*args, **kwargs)

    def snapshot(self, *args, **kwargs):
        return self._admission.snapshot(*args, **kwargs)

    def status(self, *args, **kwargs):
        return self._admission.status(*args, **kwargs)

    def suspend_pending(self, *args, **kwargs):
        return self._admission.suspend_pending(*args, **kwargs)

    def take_suspended(self, *args, **kwargs):
        return self._admission.take_suspended(*args, **kwargs)

