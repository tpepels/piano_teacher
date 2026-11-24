"""Musical-rate and source-bound playback timing calculations.

No private grading clock, stage selector or score renderer. Samples one
chosen source, its exact authored tempo map and the established
PlaybackSession/VisualTransport state for command or read-side use.
"""
from __future__ import annotations
from .playback_facts import PlaybackSourceFacts, PlaybackRuntimeFacts, PreparationRequest
from .musical_scheduler import SCHEDULER, RestMeasurement, ContinuationMeasurement
from .musical_timeline import TakeSpec, take_spans, rest_to_barline



NO_PIANO = "Connect your MIDI piano to play in tempo."

class TransportTiming:
    def __init__(self, *, lesson, transport, score, attempt_progression, take,
                          midi_input, clock):
        self.lesson = lesson
        self.transport = transport
        self.attempt_progression = attempt_progression
        self.score = score
        self.take = take
        self.clock = clock
        self.midi_input = midi_input

    def presentation_bpm(self) -> float:
        pending = self.take.pending
        if pending is not None and pending.receipt is None and pending.decision.next_exposure is not None:
            return float(pending.decision.next_exposure.bpm)
        plan = self.lesson.plan
        return float(plan.bpm) if plan is not None else 0.0

    def playback_facts(self, *, from_beat: float | None = None) -> PlaybackRuntimeFacts:
        """Frozen source, meter and transport facts; never hand over the engine."""
        source = None
        if self.lesson.plan is not None:
            plan = self.lesson.plan
            bar, meter = self.transport.count_in_bar_beats, tuple(self.transport.count_in_meter)
            if from_beat is not None:
                _, bar, meter = self.attempt_progression.count_in_bar(
                    phrase=plan.active_phrase,boundaries=plan.piece.bar_boundaries,
                    time_signatures=plan.piece.time_signatures,position=from_beat)
            tempo = self.active_tempo_map()
            segments = tuple((float(s["start_beat"]),float(s["end_beat"]),
                              float(s["bpm"])) for s in
                             (tempo.as_segments() if tempo is not None else ()))
            source = PlaybackSourceFacts(
                fingerprint=self.lesson.fingerprint,stage_key=plan.identity,
                revision=self.lesson.revision,hand=plan.hand,bpm=float(plan.bpm),
                end_beat=plan.active_phrase.sounding_end-plan.active_phrase.start,
                count_in_bar_beats=float(bar),count_in_meter=tuple(meter),
                tempo_segments=segments)
        return self.transport.facts(source)

    def piano_connected(self) -> bool:
        """Timed (graded) playback needs a connected MIDI piano."""
        return self.midi_input.connected

    def request_playback(self, *, from_beat: float, **kwargs):
        if (str(kwargs.get("mode", "")) in ("practice", "perform")
                and not self.piano_connected()):
            raise ValueError(NO_PIANO)
        facts = self.playback_facts(from_beat=from_beat)
        if self.transport.automatic_request_blocked(
                facts, action=str(kwargs.get("action", "")),
                mode=str(kwargs.get("mode", "")), from_beat=from_beat):
            # Repeated renderer/audio readiness callbacks are events, not
            # permission for unlimited new transactions on one failed
            # score. Keep the prior terminal failure visible and await
            # an explicit user selection rather than raising in every tick.
            return None
        return self.transport.request(facts, from_beat=from_beat, **kwargs)

    def active_tempo_map(self):
        """Reuse an immutable authored tempo map until stage or BPM changes.

        This runs on the 20 ms worker as well as during state snapshots.
        ExerciseStage.tempo_map() may transform every note, so rebuilding it
        for every clock read creates work proportional to the full passage.
        """
        if self.lesson.plan is None or self.transport.mode not in ("practice", "listen"):
            return None
        return self.score.tempo_map(self.lesson.plan.active_stage, self.lesson.plan.bpm)

    def elapsed_beat(self, elapsed_seconds: float) -> float:
        """Source beats played `elapsed_seconds` after run_at, read from the
        running take on the musical timeline (its inverse) when it is there."""
        transport = self.transport
        take = transport.musical_timeline.take(transport.active_segment_id)
        if take is not None:
            at = transport.run_at+elapsed_seconds
            world = transport.musical_timeline.world_at(at)
            return (take.source_from_beat-transport.play_from_beat
                    +world-take.world_start)
        return SCHEDULER.elapsed_beats(
            self.active_tempo_map(),self.transport.play_from_beat,
            elapsed_seconds,self.lesson.plan.bpm)

    def elapsed_seconds(self, beat: float) -> float:
        tempo = self.active_tempo_map()
        return SCHEDULER.source_seconds(tempo,beat,self.lesson.plan.bpm)

    def timeline_take(self, *, from_beat: float, mode: str, take_id: str) -> TakeSpec:
        """The selected window from `from_beat` as a take on the musical
        timeline: its authored tempo at the practice BPM and the rest from
        its last sounding note to the following barline."""
        plan = self.lesson.plan
        phrase = plan.active_phrase
        end = phrase.sounding_end-phrase.start
        start = min(max(0.0,float(from_beat)),end)
        bpm = float(plan.bpm)
        tempo = self.score.tempo_map(plan.active_stage,plan.bpm)
        local = (tempo.from_beat(start).as_segments()
                 if tempo is not None and start < tempo.duration_beats else ())
        spans = take_spans([(s["start_beat"],s["end_beat"],s["bpm"]) for s in local],
                           0.0,end-start,bpm)
        grid = self.attempt_progression.grid_for(phrase,plan.piece.bar_boundaries)
        return TakeSpec(take_id,mode,start,spans,rest_to_barline(end,grid))

    def next_count_in(self) -> tuple[float,tuple[int,int]]:
        plan = self.lesson.plan
        return self.attempt_progression.next_count_in(
            phrase=plan.active_phrase if plan is not None else None,
            boundaries=plan.piece.bar_boundaries if plan is not None else (),
            time_signatures=plan.piece.time_signatures if plan is not None else (),
            bpm=float(plan.bpm) if plan is not None else 0.0,
            start_from=self.lesson.opening_beat,
            already_active=self.transport.running or self.transport.paused,
            current_bar_beats=self.transport.count_in_bar_beats,
            current_meter=tuple(self.transport.count_in_meter))

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
            announced_at=self.transport.announced_deadline(from_beat),
            rest_beats=self.transport.visual_gap_beats,
            horizon_beats=self.transport.continuous_horizon_beats,
            rest=self.collect_rest_measurement(
                from_beat=from_beat,
                source_end=deadline if self.transport.rest_take_end is None else None),
            automatic=self.lesson.plan is not None and self.transport.auto)

    def schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float,
                              reading_lead_included: bool = False,
                              announce: bool = True,
                              short_deadline: float | None = None):
        self.transport.schedule_preparation(PreparationRequest(
            self.score.source_model(),target,now,from_visual,reverse_seconds,
            self.presentation_bpm(),self.transport.continuous_horizon_beats,
            reading_lead_included,announce,short_deadline))

    def visual_motion(self, now: float) -> tuple[float, float, float]:
        """Read the one transport projection, including authored tempo and silence."""
        phrase = self.lesson.plan.active_phrase
        return self.transport.position(
            now, phrase_length=phrase.sounding_end-phrase.start, bpm=self.lesson.plan.bpm,
            running=self.transport.running,
            pending_auto_result=(self.take.pending_result is not None and self.transport.auto),
            tempo_map=self.active_tempo_map())

    def update_short_rest(self, kwargs: dict) -> None:
        """Godot's written-rest geometry between takes (owner, round 4).

        continuation_clear_beats: the written rest bar printed directly after
        a take's last source beat, plus the margin that new ink keeps from it.
        continuation_header_beats: the next opening's header plus a frame
        margin. The next source is admitted straight after the rest on the
        empty staff; its one count-in bar is spoken over the rest bar.
        """
        ahead = kwargs.get("ink_ahead_beats")
        if ahead is not None:
            self.transport.report_ink_ahead(ahead)
        clear = kwargs.get("continuation_clear_beats")
        header = kwargs.get("continuation_header_beats")
        if clear is None or header is None:
            return
        self.transport.report_rest_geometry(clear, header)

    def collect_rest_measurement(self, *,
                                  from_beat: float = 0.0,
                                  source_end: float | None = None
                                  ) -> RestMeasurement | None:
        """Read authored meter and actual native glyph clearance only.

        This routine has no timing arithmetic. The musical scheduler owns
        the outgoing/incoming tempo conversion, count-in and deadline.
        """
        if self.transport.short_rest is None or self.lesson.plan is None or self.presentation_bpm() <= 0:
            return None
        clear, header = self.transport.short_rest
        outgoing_bpm = self.presentation_bpm()
        if source_end is None:
            if self.transport.rest_take_end is None:
                return None
            source_end,outgoing_bpm = self.transport.rest_take_end
        _, bar, _ = self.attempt_progression.count_in_bar(
            phrase=self.lesson.plan.active_phrase,
            boundaries=self.lesson.plan.piece.bar_boundaries,
            time_signatures=self.lesson.plan.piece.time_signatures,
            position=from_beat)
        return RestMeasurement(
            source_end=source_end,outgoing_bpm=outgoing_bpm,
            clear_beats=clear,header_beats=header,
            count_in_beats=bar,tempo_epoch=self.transport.tempo_epoch)

    def update_continuous_horizon(self, value) -> None:
        if value is None:
            return
        self.transport.configure_reading_horizon(value)

    def musical_seconds(self, at: float) -> float:
        """Graded musical time of wall instant ``at``, in seconds since run_at.

        The one clock the Recorder and the live input view share (R1 F2).
        It stands still from the Pause moment until grading resumes after
        Resume's lead (Resume moves run_at by the paused time plus that
        lead): a key held across the pause excludes the paused interval, and
        a key-up while paused or in the lead counts at the pause moment.
        """
        return self.transport.musical_seconds(
            at,grading_after=self.midi_input.resume_grading_after)

