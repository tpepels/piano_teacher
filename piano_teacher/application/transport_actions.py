"""Transport commands and the physical playback authorization, in four owners.

PlaybackAuthorization is the one path from the renderer's physical
protocol (reserve, present, withdraw, fail) and score/audio
acknowledgements to an authorized take. TransportCommands handles Start,
Restart, Pause and Resume. RouteCommands enters routes
that change assets or untimed teaching (Listen, Learn, reload) and
handles Practice and Stop.
"""
from __future__ import annotations
from .playback_transitions import PlaybackTransition
from .transport_timing import NO_PIANO


class PlaybackAuthorization:
    def __init__(self, *, lesson, transport, transport_timing, timed_start,
                 pause_resume,
                 lifecycle, listen, presentation, notices, clock):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.timed_start = timed_start
        self.pause_resume = pause_resume
        self.lifecycle = lifecycle
        self.listen = listen
        self.presentation = presentation
        self.notices = notices
        self.clock = clock

    def start_pending(self) -> None:
        """Place a requested take on the musical timeline and start it.

        Python alone decides where it goes; Godot reads the timeline, draws
        the take's notes at its world start and counts in from it.
        """
        intent = self.transport.intent
        if intent is None or (self.transport.paused and intent.action != "resume"):
            return
        facts = self.transport_timing.playback_facts()
        if facts.source is None or not self.transport.intent_matches(facts):
            # A stale intent is invalidated by the next clock tick.
            return
        timeline = self.transport.musical_timeline
        now = self.clock()
        take = self.transport_timing.timeline_take(
            from_beat=intent.from_beat, mode=intent.mode,
            take_id=self.transport.segment_id_for(intent))
        plan = intent.count_in
        placed = None
        if intent.action == "auto" and timeline.open and timeline.segments[-1].kind == "take":
            # A repeat follows the last take: rest to its barline, then one
            # count-in bar easing to the new tempo (late: more rest bars).
            placed = timeline.continue_after_take(
                take, now=now, bar_beats=plan.bar_beats, meter=plan.meter,
                bpm=intent.bpm)
        elif intent.action == "resume" and timeline.segments:
            placed = self._resume_placement(timeline, take, now)
        if placed is None:
            if intent.action in ("restart", "resume") and timeline.open:
                timeline.cut_at(now)
            elif not timeline.open:
                timeline.reset()
            placed = timeline.start_after(
                take, now=now, rest_beats=self.transport.ink_ahead_beats,
                bar_beats=plan.bar_beats, meter=plan.meter, bpm=intent.bpm)
        timeline.next_take = None
        try:
            self._authorize(facts, timeline, placed)
            if (self.transport.auto and intent.mode == "practice"
                    and self.lesson.plan is not None
                    and self.lesson.plan.exercise.kind != "perform"):
                timeline.predict_repeat(bar_beats=plan.bar_beats,
                                        source_from_beat=self.lesson.opening_beat)
        except Exception as exc:
            # _commit already stopped the take and published the failure;
            # the MIDI key, tick or command that triggered it stands.
            print("PLAYBACK_START_FAILED:", type(exc).__name__, exc, flush=True)

    def _authorize(self, facts, timeline, placed) -> None:
        self.transport.authorize(
            facts, deadline=timeline.take_start(placed),
            world_origin=placed.world_start, segment_id=placed.take_id,
            commit=self.commit_playback_intent,
            capture=self.transport_timing.playback_facts,
            abort=self.abort_playback)

    _free: tuple | None = None

    def sync_free(self) -> None:
        """Free on the musical timeline: the staff travels to the first
        target by its published arrival, holds there while the learner
        thinks, and moves on to each next target once it is played."""
        lesson, transport = self.lesson, self.transport
        controller = lesson.guided_controller
        if transport.mode != "learn" or controller is None or lesson.plan is None:
            self._free = None
            return
        if transport.paused:
            return
        now = self.clock()
        arrival = self.transport_timing.score.free_target_arrival(lesson, transport)
        notes = controller.snapshot(now=now).get("expected_notes") or []
        if arrival is None or not notes:
            return
        beat = min(float(note["beat"]) for note in notes)
        key = (lesson.fingerprint, lesson.revision, transport.transport_id, round(arrival, 6))
        bpm = float(lesson.plan.bpm)
        timeline = transport.musical_timeline
        if self._free is None or self._free[0] != key or not timeline.segments:
            # The staff covers the travel distance by the arrival: faster
            # than the tempo on a slow piece (at most a few seconds).
            travel = self.transport_timing.score.free_target_travel(lesson, transport)
            seconds = max(0.0, arrival-now)
            if travel is None or seconds <= 1e-6:
                travel = seconds*bpm/60.0
            travel_bpm = max(bpm, travel*60.0/seconds) if seconds > 1e-6 else bpm
            # The passage opens at the arrival; its first target may come
            # later in the window (a hand starting on beat 2): stop there.
            timeline.start_free(now=now, bpm=travel_bpm, travel_beats=travel+max(0.0, beat))
            self._free = (key, beat)
        elif beat > self._free[1] + 1e-9:
            timeline.move_hold(now=now, beats=beat-self._free[1], bpm=bpm)
            self._free = (key, beat)

    @staticmethod
    def _resume_placement(timeline, take, now):
        """Resume always gives the take one complete count-in bar (owner
        decision 2026-11-08): the run ends where it was paused and the take
        continues from the paused beat (or its opening, when the pause came
        in the count-in or rest) after the visible ink and a fresh bar."""
        timeline.resume(now)
        timeline.cut_at(now)
        return None

    # Godot could not draw a take (it saw it after its first note, or a
    # running take lost its notes): place the same exposure again, once.
    REPLACEABLE_DISPLAY_FAILURES = ("timeline_take_not_drawn",
                                    "running_take_without_admitted_source")
    REPLACE_AGAIN_AFTER_SECONDS = 30.0

    def fail_physical(self, **values) -> dict:
        reason = str(values.get("reason", ""))
        plan, mode = self.lesson.plan, self.transport.mode
        key = (self.lesson.fingerprint, self.lesson.revision,
               plan.identity if plan is not None else "", mode)
        now = self.clock()
        replace = (reason in self.REPLACEABLE_DISPLAY_FAILURES and plan is not None
                   and mode in ("practice", "perform") and self.transport.running
                   and not self.transport.paused
                   and not (self._replaced is not None and self._replaced[0] == key
                            and now - self._replaced[1] < self.REPLACE_AGAIN_AFTER_SECONDS))
        self.transport.fail(notify_failure=(
            self.on_replaced_failure if replace else self.on_playback_failure), **values)
        if replace:
            self._replaced = (key, now)
            self.transport.clear_failure()
            self.transport_timing.request_playback(
                action="score_ready", mode=mode, from_beat=self.lesson.opening_beat)
        return {"accepted": True}

    _replaced: tuple | None = None

    def on_replaced_failure(self, reason: str) -> None:
        self.lifecycle.stop(reason=reason)
        self.notices.feedback = "Count in, then play"
        self.notices.next_action = ""

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
                self.timed_start.start(mode=selected.mode,from_beat=selected.from_beat,
                    scheduled_deadline=authorized.deadline,count_in_plan=intent.count_in,
                    effect=authorized.transition.effect,reason=authorized.action)
            elif authorized.action == "resume":
                self.resume_current_session(
                    presentation_lead_seconds=max(0.0,authorized.deadline-self.clock()),
                    scheduled_deadline=authorized.deadline)
            elif authorized.action in ("auto","score_ready"):
                self.timed_start.start(from_beat=intent.from_beat,mode=intent.mode,
                    loop_continuation=authorized.action == "auto",
                    scheduled_deadline=authorized.deadline,
                    count_in_plan=intent.count_in,reason=authorized.action)
            elif authorized.action == "listen":
                self.transport.start_listen(revision=self.lesson.revision,
                    count_in=intent.count_in,deadline=authorized.deadline)
                self.notices.feedback = "Count in, then listen"

    def control_acknowledgement(self, action: str, kwargs: dict, *, reason=None) -> None:
        if action == "score_ready":
            # The compiled native score has now supplied real printed rest
            # and header clearance. Install it before the score-ready ACK
            # can select a future fixed-deadline automatic continuation.
            self.transport_timing.update_placement_facts(kwargs)
            revision = int(kwargs.get("revision",-1))
            decision = self.transport.score_acknowledged(revision,
                current_revision=self.lesson.revision,teaching_bound=self.lesson.guided_controller is not None)
            if decision == "listen":
                self.pause_resume.begin_listen_if_ready()
            elif decision == "learn":
                self.lesson.guided_controller.start(now=self.clock())
            elif decision == "practice" and not self.transport_timing.piano_connected():
                # The score is ready but nothing can be graded: wait visibly
                # instead of leaving the exposure stuck awaiting its score.
                self.transport.wait_for_player()
                self.notices.publish(NO_PIANO, "Switch on or plug in your piano, then press Play.")
            elif decision == "practice":
                position = (self.transport.pending_rewind
                    if self.transport.pending_rewind is not None else self.lesson.opening_beat)
                mode = "perform" if self.transport.mode == "perform" else "practice"
                self.transport_timing.request_playback(action="score_ready",mode=mode,from_beat=position)
        elif self.transport.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self.pause_resume.begin_listen_if_ready()

    def resume_current_session(self, *, presentation_lead_seconds=0.0,
                                scheduled_deadline=None):
        completed = self.pause_resume.resume(
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
        self.pause_resume.begin_listen_if_ready()



class RouteCommands:
    def __init__(self, *, lesson, transport, exposure_workflows,
                 course, lifecycle, notices):
        self.lesson = lesson
        self.transport = transport
        self.exposure_workflows = exposure_workflows
        self.course = course
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
            self.course.begin_learn(exposure=selected,reason=action)
        else:
            raise ValueError(f"Route {route!r} is admitted physically, not entered")


class TransportCommands:
    def __init__(self, *, lesson, transport, transport_timing, pause_resume,
                 score, routes, authorization):
        self.lesson = lesson
        self.transport = transport
        self.transport_timing = transport_timing
        self.pause_resume = pause_resume
        self.score = score
        self.routes = routes
        self.authorization = authorization

    def control_transport(self, action: str, kwargs: dict, *, effect=None) -> None:
        if action == "section_next":
            selected = self.lesson.install_command(effect)
            self.routes.course.enter_selected_exposure(selected,reason=action)
        elif action == "section_repeat":
            self.transport_timing.update_placement_facts(kwargs)
            transition = PlaybackTransition.from_effect(effect, action="start")
            self.transport_timing.request_playback(action="start", mode="practice",
                from_beat=transition.exposure.from_beat, transition=transition)
        elif action == "practice":
            self.routes.practice(kwargs, effect=effect)
        elif action == "stop":
            self.score.cancel_preparation()
            self.routes.stop()
        elif action in ("start", "restart"):
            self.transport_timing.update_placement_facts(kwargs)
            effect = effect or self.lesson.manual_effect(action)
            transition = PlaybackTransition.from_effect(effect, action=action)
            if transition.route in ("listen", "prepare_practice", "learn"):
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
            self.pause_resume.pause(
                pending_admission=self.transport.suspend_pending(
                    self.transport_timing.playback_facts()))
        elif action == "resume":
            self.transport_timing.update_placement_facts(kwargs)
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
