"""Transport commands and the physical playback authorization, in four owners.

PlaybackAuthorization is the one path from the renderer's physical
protocol (reserve, present, withdraw, fail) and score/audio
acknowledgements to an authorized take. TransportCommands handles Start,
Restart, Pause and Resume. RetainedResultReplay replays a saved result
after a failed save or rolling recovery. RouteCommands enters routes
that change assets or untimed teaching (Listen, Learn, reload) and
handles Practice and Stop.
"""
from __future__ import annotations
from .playback_transitions import PlaybackTransition


class PlaybackAuthorization:
    def __init__(self, *, lesson, transport, transport_timing, timed_playback,
                 lifecycle, listen, presentation, notices, clock):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.timed_playback = timed_playback
        self.lifecycle = lifecycle
        self.listen = listen
        self.presentation = presentation
        self.notices = notices
        self.clock = clock

    def reserve_physical(self, **values) -> dict:
        return self.transport.reserve(self.transport_timing.playback_facts(), **values)

    def present_physical(self, **values) -> dict:
        return self.transport.present(
            self.transport_timing.playback_facts(),
            commit=self.commit_playback_intent,
            capture=self.transport_timing.playback_facts,
            abort=self.abort_playback, **values)

    def withdraw_physical(self, **values) -> dict:
        return self.transport.withdraw(self.transport_timing.playback_facts(), **values)

    def fail_physical(self, **values) -> dict:
        self.transport.fail(notify_failure=self.on_playback_failure, **values)
        return {"accepted": True}

    def abort_playback(self, reason: str) -> None:
        self.lifecycle.stop(reason=reason)

    def on_playback_failure(self, reason: str) -> None:
        if self.transport.running:
            self.lifecycle.stop(reason=reason)
        self.notices.feedback = "The score stopped displaying correctly"
        self.notices.next_action = "Select this lesson again after checking the score."

    def commit_playback_intent(self, intent, receipt) -> None:
        """Apply source effects at the coordinator's single authorization gate."""
        with self.transport.authorization(intent,receipt) as authorized:
            if authorized.action in ("start","restart"):
                selected = authorized.transition.exposure
                authorized.validate_selected(selected,intent)
                # TimedPlayback installs this exact decision ONCE as part of
                # the authorized start. Do not preinstall its lesson mutation
                # in a second transport command adapter.
                self.timed_playback.start(mode=selected.mode,from_beat=selected.from_beat,
                    scheduled_deadline=authorized.deadline,count_in_plan=intent.count_in,
                    effect=authorized.transition.effect,reason=authorized.action)
            elif authorized.action == "resume":
                self.resume_current_session(
                    presentation_lead_seconds=max(0.0,authorized.deadline-self.clock()),
                    scheduled_deadline=authorized.deadline)
            elif authorized.action in ("auto","score_ready"):
                self.timed_playback.start(from_beat=intent.from_beat,mode=intent.mode,
                    loop_continuation=authorized.action == "auto",
                    scheduled_deadline=authorized.deadline,
                    count_in_plan=intent.count_in,reason=authorized.action)
                self.transport.bind_scheduled_start(
                    transport_id=self.transport.transport_id,
                    from_beat=self.transport.play_from_beat,
                    run_at=self.transport.run_at,
                    stage_key=self.lesson.plan.identity,
                    revision=self.lesson.revision)
            elif authorized.action == "listen":
                self.transport.start_listen(revision=self.lesson.revision,
                    count_in=intent.count_in,deadline=authorized.deadline)
                self.notices.feedback = "Count in, then listen"

    def control_acknowledgement(self, action: str, kwargs: dict, *, reason=None) -> None:
        if action == "score_ready":
            # The compiled native score has now supplied real printed rest
            # and header clearance. Install it before the score-ready ACK
            # can select a future fixed-deadline automatic continuation.
            self.transport_timing.update_short_rest(kwargs)
            revision = int(kwargs.get("revision",-1))
            decision = self.transport.score_acknowledged(revision,
                current_revision=self.lesson.revision,teaching_bound=self.lesson.guided_controller is not None)
            if decision == "listen":
                self.timed_playback.begin_listen_if_ready()
            elif decision == "learn":
                self.lesson.guided_controller.start(now=self.clock())
            elif decision == "practice":
                position = (self.transport.pending_rewind
                    if self.transport.pending_rewind is not None else self.lesson.opening_beat)
                mode = "perform" if self.transport.mode == "perform" else "practice"
                self.transport_timing.request_playback(action="score_ready",mode=mode,from_beat=position)
        elif self.transport.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self.timed_playback.begin_listen_if_ready()

    def resume_current_session(self, *, presentation_lead_seconds=0.0,
                                scheduled_deadline=None):
        completed = self.timed_playback.resume(
            presentation_lead_seconds=presentation_lead_seconds,
            scheduled_deadline=scheduled_deadline)
        if completed.deferred_score_revision is not None:
            # Infrastructure acknowledgement stays within this transaction.
            # Re-entering control() from Resume would recursively start a
            # second command scope and repeat the application router.
            self.control_acknowledgement(
                "score_ready", {"revision": completed.deferred_score_revision},
                reason="score_ready")
            self.presentation.prepare_score_presentation()
        self.timed_playback.begin_listen_if_ready()



class RetainedResultReplay:
    def __init__(self, *, lesson, take, transport, settlement,
                 rolling_recovery, notices, clock):
        self.lesson = lesson
        self.take = take
        self.transport = transport
        self.settlement = settlement
        self.rolling_recovery = rolling_recovery
        self.notices = notices
        self.clock = clock

    def pending(self) -> bool:
        """A failed save or rolling recovery is waiting to be replayed."""
        return self.take.settlement_failed or self.take.pending_rolling is not None

    def replay(self) -> None:
        """Play after a failed save or rolling recovery replays that same result."""
        if self.take.settlement_failed:
            revision = self.lesson.revision
            # Drop the failure instruction; the replayed continuation
            # publishes its own next action (count-in or next passage).
            self.notices.next_action = ""
            self.notices.feedback = (
                self.settlement.retry_failed_publication(
                    now=self.clock()) or "Assessment saved")
            if self.lesson.revision != revision:
                self.transport.await_score(self.lesson.revision)
            return
        if self.take.pending_rolling is not None:
            decision, phrase, grid, score_beat, _old_now = self.take.pending_rolling
            self.rolling_recovery.apply_rolling_recovery(decision, phrase, grid, score_beat, self.clock())
            self.transport.clear_pause_for_restart()
            return
        raise ValueError("No retained result to replay")


class RouteCommands:
    def __init__(self, *, lesson, transport, exposure_workflows,
                 lesson_execution, lifecycle, notices):
        self.lesson = lesson
        self.transport = transport
        self.exposure_workflows = exposure_workflows
        self.lesson_execution = lesson_execution
        self.lifecycle = lifecycle
        self.notices = notices

    def practice(self, kwargs: dict, *, effect=None) -> None:
        self.exposure_workflows.prepare_practice(effect=effect,reason="practice")
        if kwargs.get("wait_for_player", False):
            # Listen returns to a ready score without an auto count-in.
            self.transport.wait_for_player()
            self.notices.feedback = "Ready to play"
            self.notices.next_action = "Play one piano key to begin, or press Play."

    def stop(self) -> None:
        self.lifecycle.stop(reason="stop")
        # A stopped session has no take a later rest could follow (M6).
        self.transport.clear_take_end()
        self.notices.feedback = "Stopped"
        self.notices.next_action = "Start when you are ready."

    def enter_source_route(self, action: str, transition) -> None:
        """Enter a selected route that changes assets or untimed teaching."""
        effect, route = transition.effect, transition.route
        selected = self.lesson.install_command(effect)
        if route == "listen":
            self.exposure_workflows.prepare_listen(effect=effect,reason=action)
        elif route == "prepare_practice":
            self.exposure_workflows.prepare_practice(exposure=selected,reason=action)
        elif route == "learn":
            self.lesson_execution.begin_learn(exposure=selected,reason=action)
        elif route == "reload_score":
            self.lifecycle.stop(reason=action)
            self.lesson.advance_revision()
            self.transport.await_score(self.lesson.revision)
            self.notices.feedback = "Preparing sheet music"
        else:
            raise ValueError(f"Route {route!r} is admitted physically, not entered")


class TransportCommands:
    def __init__(self, *, lesson, transport, transport_timing, timed_playback,
                 score, routes, replay, authorization):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.timed_playback = timed_playback
        self.score = score
        self.routes = routes
        self.replay = replay
        self.authorization = authorization

    def control_transport(self, action: str, kwargs: dict, *, effect=None) -> None:
        if action == "practice":
            self.routes.practice(kwargs, effect=effect)
        elif action == "stop":
            self.routes.stop()
        elif action in ("start", "restart"):
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            if self.replay.pending():
                self.replay.replay()
                return
            effect = effect or self.lesson.manual_effect(action)
            transition = PlaybackTransition.from_effect(
                effect,action=action,source_changed=(
                    self.score.current_artifacts.source_bpm_changed(self.lesson.plan.piece.bpm)
                    if self.transport.mode not in ("listen", "learn") else False))
            if transition.route in ("listen", "prepare_practice",
                                    "reload_score", "learn"):
                # These routes change assets or enter untimed teaching.
                # The resulting timed source, if any, is requested only
                # after its exact selected score revision is prepared.
                self.routes.enter_source_route(action, transition)
            else:
                selected = transition.exposure
                self.transport_timing.request_playback( action=action,
                    mode=selected.mode, from_beat=selected.from_beat,
                    transition=transition)
        elif action == "pause":
            self.timed_playback.pause(
                pending_admission=self.transport.suspend_pending(
                    self.transport_timing.playback_facts()))
        elif action == "resume":
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            suspended = self.transport.take_suspended(
                self.transport_timing.playback_facts())
            if suspended is not None:
                self.transport.resume_suspended_admission()
                self.transport_timing.request_playback(action=suspended.action,
                    mode=suspended.mode,from_beat=suspended.from_beat,
                    transition=suspended.transition)
                return
            if not self.transport.running:
                # Resume inside a rest resumes the pending teaching
                # decision; it is not a new timed take. Its next take
                # will independently enter the admission transaction.
                self.authorization.resume_current_session()
                return
            from_beat = self.transport.play_from_beat + max(
                0.0, self.transport_timing.elapsed_beat(
                    self.transport.paused_at - self.transport.run_at))
            self.transport_timing.request_playback( action="resume",
                mode=self.transport.mode, from_beat=from_beat)
