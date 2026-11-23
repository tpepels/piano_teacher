"""Musical-rate and source-bound playback timing calculations.

No private grading clock, stage selector or score renderer. Samples one
chosen source, its exact authored tempo map and the established
PlaybackSession/VisualTransport state for command or read-side use.
"""
from __future__ import annotations
from .playback_facts import PlaybackSourceFacts, PlaybackRuntimeFacts, PreparationRequest
from .musical_scheduler import SCHEDULER, RestMeasurement, ContinuationMeasurement


class TransportTiming:
    def __init__(self, *, source_identity, lesson_cursor,
                 playback_session, visual_transport, tempo_map_cache,
                 attempt_progression, attempt_settlement, score_read,
                 midi_ingress, playback, clock):
        self.source_identity, self.lesson_cursor = source_identity, lesson_cursor
        self.playback_session, self.visual_transport = playback_session, visual_transport
        self.tempo_map_cache, self.attempt_progression = tempo_map_cache, attempt_progression
        self.attempt_settlement, self.score_read = attempt_settlement, score_read
        self.midi_ingress, self.playback, self.clock = midi_ingress, playback, clock

    def presentation_bpm(self) -> float:
        pending = self.attempt_settlement.pending
        if pending is not None and pending.receipt is None and pending.decision.next_exposure is not None:
            return float(pending.decision.next_exposure.bpm)
        plan = self.source_identity.plan
        return float(plan.bpm) if plan is not None else 0.0

    def playback_facts(self, *, from_beat: float | None = None) -> PlaybackRuntimeFacts:
        """Frozen source, meter and transport facts; never hand over the engine."""
        source = None
        if self.source_identity.plan is not None:
            plan = self.source_identity.plan
            bar, meter = self.playback_session.count_in_bar_beats, tuple(self.playback_session.count_in_meter)
            if from_beat is not None:
                _, bar, meter = self.attempt_progression.count_in_bar(
                    phrase=plan.active_phrase,boundaries=plan.piece.bar_boundaries,
                    time_signatures=plan.piece.time_signatures,position=from_beat)
            tempo = self.active_tempo_map()
            segments = tuple((float(s["start_beat"]),float(s["end_beat"]),
                              float(s["bpm"])) for s in
                             (tempo.as_segments() if tempo is not None else ()))
            source = PlaybackSourceFacts(
                fingerprint=self.source_identity.fingerprint,stage_key=plan.identity,
                revision=self.source_identity.revision,hand=plan.hand,bpm=float(plan.bpm),
                end_beat=plan.active_phrase.sounding_end-plan.active_phrase.start,
                count_in_bar_beats=float(bar),count_in_meter=tuple(meter),
                tempo_segments=segments)
        return self.playback_session.facts(source)

    def request_playback(self, *, from_beat: float, **kwargs):
        facts = self.playback_facts(from_beat=from_beat)
        if self.playback.automatic_request_blocked(
                facts, action=str(kwargs.get("action", "")),
                mode=str(kwargs.get("mode", "")), from_beat=from_beat):
            # Repeated renderer/audio readiness callbacks are events, not
            # permission for unlimited new transactions on one failed
            # score. Keep the prior terminal failure visible and await
            # an explicit user selection rather than raising in every tick.
            return None
        return self.playback.request(facts, from_beat=from_beat, **kwargs)

    def active_tempo_map(self):
        """Reuse an immutable authored tempo map until stage or BPM changes.

        This runs on the 20 ms worker as well as during state snapshots.
        ExerciseStage.tempo_map() may transform every note, so rebuilding it
        for every clock read creates work proportional to the full passage.
        """
        if self.source_identity.plan is None or self.playback_session.mode not in ("practice", "listen"):
            return None
        return self.tempo_map_cache.get(self.source_identity.plan.active_stage, self.source_identity.plan.bpm)

    def elapsed_beat(self, elapsed_seconds: float) -> float:
        return SCHEDULER.elapsed_beats(
            self.active_tempo_map(),self.visual_transport.play_from_beat,
            elapsed_seconds,self.source_identity.plan.bpm)

    def elapsed_seconds(self, beat: float) -> float:
        tempo = self.active_tempo_map()
        return SCHEDULER.source_seconds(tempo,beat,self.source_identity.plan.bpm)

    def next_count_in(self) -> tuple[float,tuple[int,int]]:
        plan = self.source_identity.plan
        return self.attempt_progression.next_count_in(
            phrase=plan.active_phrase if plan is not None else None,
            boundaries=plan.piece.bar_boundaries if plan is not None else (),
            time_signatures=plan.piece.time_signatures if plan is not None else (),
            bpm=float(plan.bpm) if plan is not None else 0.0,
            start_from=self.lesson_cursor.opening_beat,
            already_active=self.playback_session.running or self.visual_transport.paused,
            current_bar_beats=self.playback_session.count_in_bar_beats,
            current_meter=tuple(self.playback_session.count_in_meter))

    def next_count_in_beats(self) -> float:
        return self.next_count_in()[0]

    def next_count_in_meter(self) -> list[int]:
        return list(self.next_count_in()[1])

    def collect_continuation_measurement(self, deadline: float,
                                          from_beat: float
                                          ) -> ContinuationMeasurement:
        """Sample queue and engraving facts; deadline calculus lives in SCHEDULER."""
        return ContinuationMeasurement(
            deadline=deadline,
            announced_at=self.visual_transport.announced_deadline(from_beat),
            rest_beats=self.visual_transport.visual_gap_beats,
            horizon_beats=self.visual_transport.continuous_horizon_beats,
            rest=self.collect_rest_measurement(
                from_beat=from_beat,
                source_end=deadline if self.visual_transport.rest_take_end is None else None),
            automatic=self.source_identity.plan is not None and self.playback_session.auto)

    def start_rate_bpm(self, from_beat: float, bpm: float) -> float:
        """Authored tempo-map rate at a take's first beat, at this BPM."""
        if self.source_identity.plan is None or bpm <= 0 or self.playback_session.mode not in ("practice", "listen"):
            return float(bpm)
        tempo = self.tempo_map_cache.get(self.source_identity.plan.active_stage, bpm)
        return float(tempo.bpm_at(from_beat)) if tempo is not None else float(bpm)

    def schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float,
                              reading_lead_included: bool = False,
                              announce: bool = True,
                              short_deadline: float | None = None):
        self.playback_session.schedule_preparation(PreparationRequest(
            self.score_read.source_model(),target,now,from_visual,reverse_seconds,
            self.presentation_bpm(),self.visual_transport.continuous_horizon_beats,
            reading_lead_included,announce,short_deadline))

    def visual_motion(self, now: float) -> tuple[float, float, float]:
        """Read the one transport projection, including authored tempo and silence."""
        phrase = self.source_identity.plan.active_phrase
        return self.visual_transport.position(
            now, phrase_length=phrase.sounding_end-phrase.start, bpm=self.source_identity.plan.bpm,
            running=self.playback_session.running,
            pending_auto_result=(self.attempt_settlement.pending_result is not None and self.playback_session.auto),
            tempo_map=self.active_tempo_map())

    def update_short_rest(self, kwargs: dict) -> None:
        """Godot's written-rest geometry between takes (owner, round 4).

        continuation_clear_beats: the written rest bar printed directly after
        a take's last source beat, plus the margin that new ink keeps from it.
        continuation_header_beats: the next opening's header plus a frame
        margin. The next source is admitted straight after the rest on the
        empty staff; its one count-in bar is spoken over the rest bar.
        """
        clear = kwargs.get("continuation_clear_beats")
        header = kwargs.get("continuation_header_beats")
        if clear is None or header is None:
            return
        self.visual_transport.report_rest_geometry(clear, header)

    def collect_rest_measurement(self, *,
                                  from_beat: float = 0.0,
                                  source_end: float | None = None
                                  ) -> RestMeasurement | None:
        """Read authored meter and actual native glyph clearance only.

        This routine has no timing arithmetic. The musical scheduler owns
        the outgoing/incoming tempo conversion, count-in and deadline.
        """
        if self.visual_transport.short_rest is None or self.source_identity.plan is None or self.presentation_bpm() <= 0:
            return None
        clear, header = self.visual_transport.short_rest
        outgoing_bpm = self.presentation_bpm()
        if source_end is None:
            if self.visual_transport.rest_take_end is None:
                return None
            source_end,outgoing_bpm = self.visual_transport.rest_take_end
        _, bar, _ = self.attempt_progression.count_in_bar(
            phrase=self.source_identity.plan.active_phrase,
            boundaries=self.source_identity.plan.piece.bar_boundaries,
            time_signatures=self.source_identity.plan.piece.time_signatures,
            position=from_beat)
        return RestMeasurement(
            source_end=source_end,outgoing_bpm=outgoing_bpm,
            clear_beats=clear,header_beats=header,
            count_in_beats=bar,tempo_epoch=self.visual_transport.tempo_epoch)

    def update_continuous_horizon(self, value) -> None:
        if value is None:
            return
        self.visual_transport.configure_reading_horizon(value)

    def musical_seconds(self, at: float) -> float:
        """Graded musical time of wall instant ``at``, in seconds since run_at.

        The one clock the Recorder and the live input view share (R1 F2).
        It stands still from the Pause moment until grading resumes after
        Resume's lead (Resume moves run_at by the paused time plus that
        lead): a key held across the pause excludes the paused interval, and
        a key-up while paused or in the lead counts at the pause moment.
        """
        return self.visual_transport.musical_seconds(
            at,grading_after=self.midi_ingress.resume_grading_after)

