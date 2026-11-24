"""Mutable lifetime of the one practice/listening transport.

PlaybackCoordinator alone authorizes graphical takes; TeachingDecisions alone
selects and validates lesson exposures. This owner applies those decisions to transport lifetime.
It has no application engine reference and never selects teaching progress.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Any
from copy import deepcopy

from ..music import Phrase
from .playback_transitions import CountInPlan
from .musical_scheduler import SCHEDULER
from .musical_scheduler import SNAPSHOT_LATENCY_SECONDS
from .playback_facts import (
    PlaybackRuntimeFacts, PlaybackSourceFacts,
    TimedTakeSource, TimedStartRequest, StartedTake, PreparationRequest,
    ListenActivation, ResumeRequest, ResumedTimeline,
    ResumeCompletion, FullPassageFacts, PassageCompletion, PlaybackAuthorization,
    PassageRuntimeFacts, ScheduledContinuation, AppliedContinuation,
    PreloadedFeedbackSource,
)
from .score_ack import ScoreAckState, choose_score_ack_action
from .transport_commands import require_pausable
from .teaching_continuation import (
    FeedbackFault, HandoffScore, ContinueSelectedScore, AwaitSelectedScore,
    StopSelectedContinuation,
)
from .musical_scheduler import ContinuationMeasurement


@dataclass(slots=True)
class PlaybackSession:
    mode: str = "practice"
    auto: bool = False
    awaiting_score_revision: int | None = None
    pause_context: str | None = None
    authorizing: bool = False
    deferred_score_ack: int | None = None
    _pending_guided_capture: dict | None = field(default=None,repr=False)
    _full_completion: tuple[str, PassageCompletion] | None = field(default=None,repr=False)
    _applied_continuation: tuple[object, AppliedContinuation] | None = field(default=None,repr=False)
    _transport: Any = field(init=False, repr=False)
    _take: Any = field(init=False, repr=False)
    _score: Any = field(init=False, repr=False)
    _midi_input: Any = field(init=False, repr=False)
    _measurement: Any = field(init=False, repr=False)
    _assessment: Any = field(init=False, repr=False)
    _progression: Any = field(init=False, repr=False)
    _listen: Any = field(init=False, repr=False)
    _clock: Any = field(init=False, repr=False)

    def bind_transport(self, *, transport, take, score, midi_input,
                       measurement, assessment, progression, listen,
                       clock) -> None:
        """Bind the timeline and the domain interfaces this lifecycle uses."""
        self._transport = transport
        self._take = take
        self._score = score
        self._midi_input = midi_input
        self._measurement = measurement
        self._assessment = assessment
        self._progression = progression
        self._listen = listen
        self._clock = clock

    @property
    def running(self) -> bool:
        """One live-take bit, owned by the same timeline as Pause and onset."""
        return self._transport.running

    @property
    def transport_id(self) -> int:
        return self._transport.transport_id

    @property
    def count_in_beats(self) -> float:
        return self._transport.count_in_beats

    @property
    def count_in_bar_beats(self) -> float:
        return self._transport.count_in_bar_beats

    @property
    def count_in_meter(self) -> list[int]:
        return self._transport.count_in_meter

    def require_authorized_start(self) -> None:
        if not self.authorizing:
            raise ValueError("Timed playback requires an admitted score receipt")

    def open_take(self, *, phrase: Phrase | None = None,
                  recording: bool = False) -> int:
        """Reset exactly one take epoch across existing input/evidence owners."""
        self._take.cancel_settlement(reason="new_exposure",now=self._clock())
        self._full_completion = None
        self._applied_continuation = None
        self._score.cancel_successor()
        self.begin_epoch()
        self._midi_input.reset_live_input()
        self._transport.clear_grading_floor()
        self._take.begin_take(recording=recording)
        self._assessment.clear()
        return self.transport_id

    def begin_timed(self, source: TimedTakeSource,
                    request: TimedStartRequest) -> StartedTake:
        """Apply one chosen timed exposure, preserving its admitted deadline."""
        if self._measurement.attempt_id is not None:
            self._take.interrupt_current(reason="restart",played=(
                self._take.recorder.presses if self._take.recorder else ()))
        self._midi_input.clear_resume_gate()
        self._transport.clear_grading_floor()
        self.mode = request.mode
        self._take.begin_timed_review()
        self._transport.begin_take(loop_continuation=request.loop_continuation)
        self.open_take(phrase=source.phrase,recording=True)
        self._transport.running = True
        self.auto = request.automatic
        self.awaiting_score_revision = None
        scheduled = self._progression.schedule_start(
            phrase=source.phrase,boundaries=source.boundaries,
            time_signatures=source.time_signatures,bpm=source.bpm,
            position=request.position,loop_continuation=request.loop_continuation,
            now=self._clock(),
            count_in_plan=request.count_in_plan)
        self._transport.count_in_bar_beats = scheduled.count_in_bar_beats
        self._transport.count_in_meter = list(scheduled.count_in_meter)
        self._transport.count_in_beats = scheduled.count_in_beats
        deadline = SCHEDULER.initial(
            now=scheduled.run_at-SCHEDULER.beats_seconds(
                scheduled.count_in_beats,source.bpm),
            bpm=source.bpm,count_in_beats=scheduled.count_in_beats,
            reserved_at=request.scheduled_deadline,
            reading_lead_seconds=(request.presentation_lead_seconds
                if request.scheduled_deadline is None else 0.0),
            continuation=request.scheduled_deadline is not None).run_at
        self._transport.install_timed_origin(from_beat=scheduled.from_beat,
            run_at=deadline,gap_beats=source.visual_gap_beats)
        scope = ("perform" if request.mode == "perform" else
            "partial" if self._take.automatic_remedial_review else
            "section_review" if self._take.review_end_beat is not None else
            "partial" if scheduled.from_beat > source.phrase.first_attack_beat+1e-7 else "full")
        return StartedTake(scope,scheduled.from_beat,
            self._take.review_end_beat or source.phrase.sounding_end-source.phrase.start,
            scheduled.next_boundary_beat,deadline,scheduled.next_action)

    def capture_start(self, context: dict) -> None:
        try:
            self._measurement.begin(context)
        except Exception:
            self._transport.running = False
            self._take.suspend_recording()
            self.auto = False
            raise
        self._measurement.phase_changed(
            "count_in" if self.count_in_beats else "active",self._clock())

    def capture_guided_start(self, context: dict) -> None:
        """Keep the exact prepared source context across a storage retry."""
        if self._pending_guided_capture is None:
            self._pending_guided_capture = deepcopy(context)
        elif self._pending_guided_capture != context:
            raise ValueError("Another guided source awaits capture publication")
        self._retry_guided_capture()

    def _retry_guided_capture(self) -> None:
        if self._pending_guided_capture is None:
            return
        try:
            self._measurement.begin(self._pending_guided_capture)
        except Exception:
            if not self._transport.paused:
                self.pause(context="loading",now=self._clock())
            raise
        self._pending_guided_capture = None

    @contextmanager
    def authorization(self, intent, receipt):
        """Execute only the coordinator's original admitted transition."""
        self.authorizing = True
        try:
            if intent.action in ("start","restart"):
                if self._take.pending_result is not None:
                    self._take.cancel_settlement(reason="restart",now=self._clock())
                    self._score.cancel_successor()
                    self._transport.cancel_continuation()
                if intent.transition is None:
                    raise ValueError("Manual playback lacks the original selected transition")
            elif intent.action not in ("resume","auto","score_ready","listen"):
                raise ValueError("Unsupported playback action")
            yield PlaybackAuthorization(intent.action,receipt.deadline_ms/1000.0,
                intent.transition)
        finally:
            self.authorizing = False

    def start_listen(self, *, revision: int, count_in: CountInPlan,
                     deadline: float) -> None:
        start = self._listen.authorize_playback(revision,count_in)
        if start is None:
            raise ValueError("Listen score or audio is no longer prepared")
        self._activate_listen(start,deadline=deadline)

    def begin_listen_if_ready(self, *, revision: int) -> ListenActivation:
        if (self.mode != "listen" or self._transport.paused or self.running
                or self.awaiting_score_revision != revision):
            return ListenActivation()
        start = self._listen.begin_playback(revision,commit=False)
        if start is None:
            return ListenActivation()
        return ListenActivation(requested_count_in=start.count_in_beats,
            from_beat=start.from_beat)

    def _activate_listen(self, start, *, deadline: float) -> None:
        self.awaiting_score_revision = None
        self.open_take()
        self._transport.running = True
        self._transport.count_in_bar_beats = start.count_in_bar_beats
        self._transport.count_in_meter = list(start.count_in_meter)
        self._transport.count_in_beats = start.count_in_beats
        self._transport.install_timed_origin(
            from_beat=start.from_beat,
            run_at=deadline,
            gap_beats=self._transport.visual_gap_beats)

    def facts(self, source: PlaybackSourceFacts | None) -> PlaybackRuntimeFacts:
        return PlaybackRuntimeFacts(source=source,now=self._clock(),mode=self.mode,
            running=self.running,paused=self._transport.paused,
            run_at=self._transport.run_at,paused_at=self._transport.paused_at,
            play_from_beat=self._transport.play_from_beat,
            resume_grading_after=self._midi_input.resume_grading_after,
            pause_context=self.pause_context,
            pending_result=self._take.feedback_pending,
            transport_id=self.transport_id)

    def score_acknowledged(self, revision: int, *, current_revision: int,
                           teaching_bound: bool) -> str:
        decision = choose_score_ack_action(revision,ScoreAckState(
            requested_revision=self.awaiting_score_revision,
            current_revision=current_revision,paused=self._transport.paused,
            mode=self.mode,teaching_bound=teaching_bound))
        if decision == "defer":
            self.deferred_score_ack = revision
        elif decision == "listen":
            self._listen.acknowledge_score(revision)
        elif decision == "learn":
            self.awaiting_score_revision = None
        return decision

    def schedule_preparation(self, request: PreparationRequest) -> None:
        self._transport.schedule_source_preparation(request.source_model,
            source_from_beat=request.target,from_visual=request.from_visual,
            now=request.now,reverse_seconds=request.reverse_seconds,bpm=request.bpm,
            horizon_beats=request.horizon_beats,
            reading_lead_included=request.reading_lead_included,
            short_deadline=request.short_deadline,announce=request.announce)
        if request.announce:
            pending = self._take.pending
            if pending is not None and pending.receipt is None:
                self._score.announce_successor(pending,deadline=self._transport.next_at)
            else:
                self._transport.announce_continuation(
                    request.target,self._transport.next_at,request.bpm)
        else:
            self._transport.withdraw_announcement()
        self._transport.running = False
        self._take.suspend_recording()
        self._transport.count_in_beats = 0.0
        self._measurement.phase_changed("preparation",request.now)

    def resume_suspended_admission(self) -> None:
        """Release the stationary clock only after physical source validation."""
        if not self._transport.paused or self.running:
            raise ValueError("Cannot resume an unpaused pending admission")
        self._transport.resume(now=self._clock(),shift_run_at=False)
        self.pause_context = None

    def wait_for_player(self) -> None:
        self.awaiting_score_revision = None

    def await_score(self, revision: int) -> None:
        self.awaiting_score_revision = revision

    def stop_automatic(self) -> None:
        self.auto = False

    def continue_course(self) -> None:
        self.auto = True

    def select_source(self) -> None:
        self.mode = "practice"

    def source_revised(self, revision: int) -> bool:
        if self.awaiting_score_revision is not None:
            self.awaiting_score_revision = revision
            self.deferred_score_ack = None
            return True
        return False

    def prepare_section_review(self) -> None:
        self.awaiting_score_revision = None
        self.auto = False

    def prepare_admitted_continuation(self) -> None:
        self._transport.cancel_continuation()
        self._transport.finish_preparation_gate()
        self._transport.finish_rewind()

    def refloor_fresh_announcement(self, source: TimedTakeSource, *,
                                   physical_rest_enabled: bool) -> None:
        announced = self._transport.announced_continuation
        if announced is None or self.running or not physical_rest_enabled or source.bpm <= 0:
            return
        _,bar,_ = self._progression.count_in_bar(phrase=source.phrase,
            boundaries=source.boundaries,time_signatures=source.time_signatures,
            position=announced[0])
        self._transport.refloor_announcement(now=self._clock(),bpm=source.bpm,
            count_in_beats=bar,latency=SNAPSHOT_LATENCY_SECONDS)

    def activate_preloaded_feedback(self, source: PreloadedFeedbackSource | None, *,
                                    revision: int, fingerprint: str) -> float | None:
        if (source is None or self._take.pending_result is None or not self.auto
                or self.running or self._transport.paused):
            return None
        if self._score.successor_selection(self._take.pending,
                revision=revision,fingerprint=fingerprint) is None:
            return None
        now = self._clock()
        if not self._progression.preloaded_feedback_due(source,now=now,
                run_at=self._transport.run_at,from_beat=self._transport.play_from_beat):
            return None
        # Readiness releases the existing settlement boundary; the next
        # take still requires its independently admitted score deadline.
        self._transport.wait_for_continuation(now)
        return now

    def freeze_after_fault(self, now: float) -> None:
        """Hold the timeline after a failed save or transition, like Pause.

        Grading freezes as for a learner Pause, so a key released while the
        failure is shown cannot be graded as a longer hold.
        """
        if self._transport.paused:
            return
        self._transport.pause(at=now,freeze_grading=self.running,
            grading_after=self._midi_input.resume_grading_after)
        self._measurement.phase_changed("pause",now)

    def pause(self, *, context: str, now: float) -> None:
        require_pausable(paused=self._transport.paused,phase=context)
        self.pause_context = context
        self._transport.pause(at=now,freeze_grading=self.running,
            grading_after=self._midi_input.resume_grading_after)
        self._measurement.phase_changed("pause",now)

    def resume_timeline(self, request: ResumeRequest) -> ResumedTimeline:
        self._retry_guided_capture()
        now = self._clock()
        previous,shift,timing = self._transport.resume_attempt(
            now=now,learning=request.learning,running=self.running,
            automatic_feedback=self._take.feedback_pending and self.auto,
            grading_after=self._midi_input.resume_grading_after,
            mode=self.mode,pause_context=self.pause_context,bpm=request.bpm,
            count_in_beats=self.count_in_beats,
            full_count_in_beats=request.full_count_in_beats,
            bar_beats=self.count_in_bar_beats,
            reading_lead_seconds=request.reading_lead_seconds,
            midi_connected=request.midi_connected,
            scheduled_deadline=request.scheduled_deadline)
        self._midi_input.authorize_grading_after(timing.grading_after)
        self._transport.count_in_beats = timing.count_in_beats
        return ResumedTimeline(now,request.learning,previous,shift)

    def finish_resume(self, resumed: ResumedTimeline) -> ResumeCompletion:
        pending = self._take.pending
        announced = self._transport.announced_continuation
        if pending is not None and self._score.successor_schedule is not None and announced is not None:
            self._score.announce_successor(pending,deadline=announced[1])
        self._measurement.event("timeline_resume",{
            "scheduled_origin_before":resumed.previous_origin-self._measurement.origin,
            "scheduled_origin_after":self._transport.run_at-self._measurement.origin,
            "shift_run_at":resumed.shift_run_at})
        count_in = self.running and (resumed.now < self._transport.run_at
            or resumed.now < self._midi_input.resume_grading_after)
        self._measurement.phase_changed("guided" if resumed.learning else
            "count_in" if count_in else "active",resumed.now)
        self.pause_context = None
        feedback = ("Count in" if count_in else "Playing") if self.running else None
        deferred = self.deferred_score_ack
        self.deferred_score_ack = None
        return ResumeCompletion(feedback,deferred)

    def finish_full_passage(self, facts: FullPassageFacts) -> PassageCompletion:
        """Execute the existing metrical owner's frozen completion plan once."""
        identity = facts.pending.decision.decision_id
        if self._full_completion is not None and self._full_completion[0] == identity:
            return self._full_completion[1]
        plan = self._progression.plan_full_passage(facts,PassageRuntimeFacts(
            self.auto,self._transport.run_at,self._transport.play_from_beat))
        if plan.action == "ready":
            self._transport.wait_for_continuation(facts.now)
            result = PassageCompletion(advance_feedback=True,next_action=plan.next_action)
        elif plan.action == "stop":
            self._transport.cancel_continuation()
            result = PassageCompletion(next_action=plan.next_action)
        else:
            self._score.announce_successor(facts.pending,deadline=plan.deadline)
            early = bool(self._transport.next_at)
            result = PassageCompletion(advance_feedback=early,force_early=early,
                update_clock=not early and facts.now >= self._transport.next_at,
                next_action=plan.next_action)
        self._full_completion = (identity,result)
        return result

    def apply_feedback_fault(self, fault: FeedbackFault, *, now: float) -> None:
        if fault.pause:
            self.freeze_after_fault(now)
        if fault.stop_automatic:
            self.auto = False
        self._transport.cancel_continuation()

    def apply_continuation(self, effect, *,
                           measurement: ContinuationMeasurement | None = None,
                           source_stride_beats: float | None = None
                           ) -> AppliedContinuation:
        """Execute one typed, source-bound publication without reselecting it."""
        if self._applied_continuation is not None and self._applied_continuation[0] == effect.identity:
            return self._applied_continuation[1]
        if isinstance(effect,HandoffScore):
            deadline = max(effect.earliest_deadline,self._clock()+
                SCHEDULER.beats_seconds(effect.count_in_beats,effect.bpm))
            result = AppliedContinuation(ScheduledContinuation(
                effect.exposure.from_beat,deadline))
        elif isinstance(effect,ContinueSelectedScore):
            if measurement is None or source_stride_beats is None:
                raise ValueError("Continuation requires the exact source measurements")
            deadline = SCHEDULER.continuation(measurement,now=self._clock(),bpm=effect.bpm)
            self._transport.advance_source_stride(
                source_stride_beats-effect.exposure.from_beat)
            result = AppliedContinuation(ScheduledContinuation(
                effect.exposure.from_beat,deadline))
        elif isinstance(effect,AwaitSelectedScore):
            self.awaiting_score_revision = effect.identity.revision
            self.auto = False
            self._transport.cancel_continuation()
            result = AppliedContinuation(feedback="Preparing next passage")
        elif isinstance(effect,StopSelectedContinuation):
            self.auto = False
            self._transport.cancel_continuation()
            result = AppliedContinuation(feedback=effect.message or None)
        else:
            raise TypeError("A source-entry effect cannot be applied by playback")
        self._applied_continuation = (effect.identity,result)
        return result

    def select_exposure(self, *, mode: str, automatic: bool,
                        awaited_revision: int | None) -> None:
        self.mode = mode
        self.auto = automatic
        self.awaiting_score_revision = awaited_revision

    def reset_for_stop(self) -> None:
        self._pending_guided_capture = None
        self._full_completion = None
        self._applied_continuation = None
        self.pause_context = None
        self.deferred_score_ack = None
        self._transport.running = False
        self.auto = False
        self._transport.count_in_beats = 0.0
        self.awaiting_score_revision = None

    def finish_take(self) -> None:
        self._transport.running = False

    def begin_epoch(self) -> int:
        self._transport.transport_id += 1
        return self.transport_id
