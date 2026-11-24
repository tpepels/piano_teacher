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

    def halt_continuation(self) -> None:
        """Stop automatic flow and drop any scheduled preparation or next take."""
        self._session.stop_automatic()
        self._timeline.cancel_preparation()
        self._timeline.cancel_continuation()

    def reset_for_stop(self, *, rewind_seconds: float) -> None:
        """Return timeline and session intent to idle after Stop."""
        self._timeline.reset_for_stop(rewind_seconds=rewind_seconds)
        self._session.reset_for_stop()


    # --- Timeline ----------------------------------------------------

    @property
    def announce_serial(self):
        return self._timeline.announce_serial

    @property
    def announced_continuation(self):
        return self._timeline.announced_continuation

    @property
    def continuous_horizon_beats(self):
        return self._timeline.continuous_horizon_beats

    @property
    def musical_timeline(self):
        return self._timeline.musical

    def record_timeline_take(self, take, **kwargs):
        return self._timeline.musical.record_take(take, **kwargs)

    def reset_musical_timeline(self) -> None:
        self._timeline.musical.reset()

    @property
    def next_at(self):
        return self._timeline.next_at

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
    def practice_preparation(self):
        return self._timeline.practice_preparation

    @property
    def preparation_deadline(self):
        return self._timeline.preparation_deadline

    @property
    def preparation_pending(self):
        return self._timeline.preparation_pending

    @property
    def rest_take_end(self):
        return self._timeline.rest_take_end

    @property
    def run_at(self):
        return self._timeline.run_at

    @property
    def scheduled_start(self):
        return self._timeline.scheduled_start

    @property
    def short_rest(self):
        return self._timeline.short_rest

    @property
    def tempo_epoch(self):
        return self._timeline.tempo_epoch

    @property
    def visual_gap_beats(self):
        return self._timeline.visual_gap_beats

    @property
    def visual_offset_beats(self):
        return self._timeline.visual_offset_beats

    def adopt_committed_stage(self, *args, **kwargs):
        return self._timeline.adopt_committed_stage(*args, **kwargs)

    def advance_boundary(self, *args, **kwargs):
        return self._timeline.advance_boundary(*args, **kwargs)

    def advance_source_stride(self, *args, **kwargs):
        return self._timeline.advance_source_stride(*args, **kwargs)

    def announced_deadline(self, *args, **kwargs):
        return self._timeline.announced_deadline(*args, **kwargs)

    def bind_scheduled_start(self, *args, **kwargs):
        return self._timeline.bind_scheduled_start(*args, **kwargs)

    def cancel_continuation(self, *args, **kwargs):
        return self._timeline.cancel_continuation(*args, **kwargs)

    def cancel_preparation(self, *args, **kwargs):
        return self._timeline.cancel_preparation(*args, **kwargs)

    def clear_grading_floor(self, *args, **kwargs):
        return self._timeline.clear_grading_floor(*args, **kwargs)

    def clear_pause_for_restart(self, *args, **kwargs):
        return self._timeline.clear_pause_for_restart(*args, **kwargs)

    def clear_scheduled_start(self, *args, **kwargs):
        return self._timeline.clear_scheduled_start(*args, **kwargs)

    def clear_take_end(self, *args, **kwargs):
        return self._timeline.clear_take_end(*args, **kwargs)

    def configure_reading_horizon(self, *args, **kwargs):
        return self._timeline.configure_reading_horizon(*args, **kwargs)

    def enter_preparation_phase(self, *args, **kwargs):
        return self._timeline.enter_preparation_phase(*args, **kwargs)

    def finish_rewind(self, *args, **kwargs):
        return self._timeline.finish_rewind(*args, **kwargs)

    def grading_is_frozen(self, *args, **kwargs):
        return self._timeline.grading_is_frozen(*args, **kwargs)

    def musical_seconds(self, *args, **kwargs):
        return self._timeline.musical_seconds(*args, **kwargs)

    def note_tempo(self, *args, **kwargs):
        return self._timeline.note_tempo(*args, **kwargs)

    def position(self, *args, **kwargs):
        return self._timeline.position(*args, **kwargs)

    def preparation_schedule(self, *args, **kwargs):
        return self._timeline.preparation_schedule(*args, **kwargs)

    def prepare_rewind(self, *args, **kwargs):
        return self._timeline.prepare_rewind(*args, **kwargs)

    def reannounce_after_rest_pause(self, *args, **kwargs):
        return self._timeline.reannounce_after_rest_pause(*args, **kwargs)

    def record_take_end(self, *args, **kwargs):
        return self._timeline.record_take_end(*args, **kwargs)

    def report_rest_geometry(self, *args, **kwargs):
        return self._timeline.report_rest_geometry(*args, **kwargs)

    def select_opening(self, *args, **kwargs):
        return self._timeline.select_opening(*args, **kwargs)

    def tempo_epoch_for(self, *args, **kwargs):
        return self._timeline.tempo_epoch_for(*args, **kwargs)

    def withdraw_announcement(self, *args, **kwargs):
        return self._timeline.withdraw_announcement(*args, **kwargs)


    # --- Session intent and take lifecycle ---------------------------

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

    def activate_preloaded_feedback(self, *args, **kwargs):
        return self._session.activate_preloaded_feedback(*args, **kwargs)

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

    def prepare_section_review(self, *args, **kwargs):
        return self._session.prepare_section_review(*args, **kwargs)

    def refloor_fresh_announcement(self, *args, **kwargs):
        return self._session.refloor_fresh_announcement(*args, **kwargs)

    def require_authorized_start(self, *args, **kwargs):
        return self._session.require_authorized_start(*args, **kwargs)

    def resume_suspended_admission(self, *args, **kwargs):
        return self._session.resume_suspended_admission(*args, **kwargs)

    def resume_timeline(self, *args, **kwargs):
        return self._session.resume_timeline(*args, **kwargs)

    def schedule_preparation(self, *args, **kwargs):
        return self._session.schedule_preparation(*args, **kwargs)

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

    def advance(self, *args, **kwargs):
        return self._admission.advance(*args, **kwargs)

    def automatic_request_blocked(self, *args, **kwargs):
        return self._admission.automatic_request_blocked(*args, **kwargs)

    def fail(self, *args, **kwargs):
        return self._admission.fail(*args, **kwargs)

    def invalidate(self, *args, **kwargs):
        return self._admission.invalidate(*args, **kwargs)

    def present(self, *args, **kwargs):
        return self._admission.present(*args, **kwargs)

    def request(self, *args, **kwargs):
        return self._admission.request(*args, **kwargs)

    def reserve(self, *args, **kwargs):
        return self._admission.reserve(*args, **kwargs)

    def snapshot(self, *args, **kwargs):
        return self._admission.snapshot(*args, **kwargs)

    def status(self, *args, **kwargs):
        return self._admission.status(*args, **kwargs)

    def suspend_pending(self, *args, **kwargs):
        return self._admission.suspend_pending(*args, **kwargs)

    def take_suspended(self, *args, **kwargs):
        return self._admission.take_suspended(*args, **kwargs)

    def withdraw(self, *args, **kwargs):
        return self._admission.withdraw(*args, **kwargs)
