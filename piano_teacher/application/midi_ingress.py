"""Validated physical-note routing with one explicit musical timestamp.

The composition root owns the callback lock and commands; this owner handles
shortcut precedence, ungraded resume suppression and actual note consumers.
No handler receives an engine or discovers collaborators through a root.
"""
from collections import deque
from dataclasses import dataclass
import math
from .musical_scheduler import SCHEDULER
from .session_events import MidiArrival
from ..live_feedback import live_assessment
from ..grading_tolerance import onset_tolerance


@dataclass(frozen=True, slots=True)
class MidiInputFacts:
    fingerprint: str
    score_revision: int
    stage_key: str
    phrase: object
    hand: str
    bpm: float
    mode: str
    running: bool
    paused: bool
    preview: bool
    from_beat: float
    run_at: float
    transport_id: int
    tempo_map: object
    can_pause: bool
    cancellation_generation: int = 0
    device: str = ""


@dataclass(frozen=True, slots=True)
class InputTransportFacts:
    """Immutable backend facts; the ingress never inspects PracticeEngine."""
    next_at: float
    preview_loop_pending: bool
    pending_teaching_result: bool
    pending_rewind: bool
    automatic: bool
    preview_only: bool
    visual_gap_beats: float
    awaiting_score: bool
    exercise_kind: str
    review_end_beat: float | None
    successor_action: str | None


@dataclass(frozen=True, slots=True)
class DeferredMidi:
    """Original authorization context for a boundary-crossing MIDI event.

    Same-score automatic repeats may move to a later transport epoch;
    source revisions, stage or hand changes may not inherit that note.
    """
    message: object
    received_at: float
    corrected_at: float
    arrival: MidiArrival


@dataclass(frozen=True, slots=True)
class MidiIngressEffect:
    consumed: bool = False
    action: str | None = None
    completed_range: tuple | None = None


class MidiIngress:
    def __init__(self,midi,calibration,shortcuts,live,capture,feedback_events):
        self.midi,self.calibration,self.shortcuts = midi,calibration,shortcuts
        self.live,self.capture,self.feedback_events = live,capture,feedback_events
        self.pitch_key = ()
        self.pitches = frozenset()
        self.resume_grading_after = 0.
        self.resume_ignored_pitches = set()
        self.deferred = deque()

    def clear_resume_gate(self) -> None:
        """Remove both suppression deadline and held-key release history."""
        self.resume_grading_after = 0.0
        self.resume_ignored_pitches.clear()

    def authorize_grading_after(self, deadline: float) -> None:
        """One ingress-owned gate for the newly admitted MIDI source epoch."""
        if not math.isfinite(deadline) or deadline < 0.0:
            raise ValueError("Resume grading deadline must be finite and nonnegative")
        self.resume_grading_after = float(deadline)

    def dispatch(self, message, *, facts: MidiInputFacts,
                 received_at: float, corrected_at: float | None,
                 deferred: bool, midi_offset_seconds: float,
                 apply_shortcut, transport_facts, musical_seconds,
                 recorder, teaching, feedback_take) -> None:
        """One ordering for MIDI shortcuts, timestamp deferral and grading.

        The source facts describe the *incoming* take. A shortcut may
        synchronously change the current session; afterward, only the
        separate immutable transport gate is resampled. Never recapture
        source identity and silently credit this key to a new take.
        """
        effect = self.classify(
            message,facts=facts,now=received_at,deferred=deferred)
        if effect.action or effect.completed_range is not None:
            apply_shortcut(effect)
        if effect.consumed:
            return
        gates = transport_facts()
        if self.suppress_for_successor(facts,gates):
            return
        adjusted = (received_at-midi_offset_seconds
                    if corrected_at is None else corrected_at)
        if self.defer_boundary_note(
                message,facts=facts,transport=gates,
                received_at=received_at,corrected_at=adjusted,
                replaying=deferred):
            return
        self.deliver(
            message,facts=facts,received_at=received_at,
            corrected_at=adjusted,musical_at=musical_seconds(adjusted),
            recorder=recorder(),teaching=teaching(),
            feedback_take=feedback_take())

    def classify(self,message,*,facts,now,deferred=False):
        if self.calibration.active:
            if not deferred:
                self.midi.observe(message,now=now)
            if message.type == "note_on" and message.velocity > 0:
                self.calibration.observe(now)
            return MidiIngressEffect(consumed=True)
        if message.type in ("note_on","note_off"):
            key = (facts.fingerprint,facts.score_revision,facts.stage_key,facts.hand)
            if key != self.pitch_key:
                self.pitch_key = key
                self.pitches = frozenset(note.pitch for note in facts.phrase.notes
                    if facts.hand == "both" or note.hand == facts.hand) if facts.phrase is not None else frozenset()
            selected = self.shortcuts.accept(message,device=self.midi.device,
                exercise_pitches=self.pitches,can_pause=facts.can_pause,paused=facts.paused)
            if selected.consumed or selected.action or selected.completed_range is not None:
                action = "learn_retry" if selected.action == "restart" and facts.mode == "learn" else selected.action
                return MidiIngressEffect(selected.consumed,action,selected.completed_range)
        if not deferred:
            self.midi.observe(message,now=now)
        if message.type in ("note_on","note_off"):
            is_on = message.type == "note_on" and message.velocity > 0
            if is_on and now < self.resume_grading_after and facts.running:
                self.resume_ignored_pitches.add(message.note)
                return MidiIngressEffect(consumed=True)
            if message.note in self.resume_ignored_pitches:
                if not is_on:
                    self.resume_ignored_pitches.remove(message.note)
                return MidiIngressEffect(consumed=True)
        return MidiIngressEffect()

    def suppress_for_successor(self, facts: MidiInputFacts,
                               transport: InputTransportFacts) -> bool:
        # A current take can still be running while a start/restart has
        # already selected its successor. No key may earn credit between
        # selection and physical admission of the new source.
        return bool(transport.successor_action in ("start","restart")
            and facts.running)

    def defer_boundary_note(self,message,*,facts: MidiInputFacts,
                            transport: InputTransportFacts,
                            received_at: float, corrected_at: float,
                            replaying: bool) -> bool:
        """Protect the actual hardware timestamp across automatic rollover.

        This is the only MIDI deferral policy. The engine transports the
        immutable state facts but does not re-decide when a key belongs to
        the old take versus the next one. Replay never defers again.
        """
        if replaying or message.type not in ("note_on","note_off") or (
                facts.phrase is None or facts.mode not in ("practice","perform")
                or facts.paused or transport.awaiting_score):
            return False
        due = (not facts.running and transport.next_at
               and received_at >= transport.next_at
               and (transport.preview_loop_pending or
                    transport.pending_teaching_result and transport.automatic or
                    transport.pending_rewind))
        if (facts.running and facts.mode == "practice"
                and transport.exercise_kind != "perform"
                and transport.review_end_beat is None
                and (transport.automatic or transport.preview_only)):
            duration = SCHEDULER.source_seconds(
                facts.tempo_map,
                facts.phrase.sounding_end-facts.phrase.start,facts.bpm)
            played = SCHEDULER.source_seconds(
                facts.tempo_map,facts.from_beat,facts.bpm)
            finish = facts.run_at+duration-played
            due = received_at >= SCHEDULER.offscreen(
                deadline=finish,lead_beats=transport.visual_gap_beats,
                bpm=facts.bpm)
        if due or self.deferred:
            self.deferred.append(DeferredMidi(
                message.copy(), received_at, corrected_at,
                MidiArrival(facts.device, facts.fingerprint,
                            facts.score_revision, facts.stage_key, facts.hand,
                            facts.transport_id, facts.cancellation_generation,
                            transport.automatic)))
            return True
        return False

    def deliver(self,message,*,facts,received_at,corrected_at,musical_at,recorder,teaching,feedback_take):
        if message.type not in ("note_on","note_off"):
            return
        is_on = message.type == "note_on" and message.velocity > 0
        recorded = None
        if facts.running and recorder and facts.mode not in ("learn", "listen"):
            spb = SCHEDULER.seconds_per_beat(
                facts.tempo_map.bpm_at(facts.from_beat)
                if facts.tempo_map is not None else facts.bpm)
            if not is_on or not facts.paused and musical_at >= -onset_tolerance(spb):
                recorded = recorder.add(message.note,is_on,musical_at)
        judgement = None
        if (recorded is not None and facts.phrase is not None
                and not facts.paused and not facts.preview):
            assessment = live_assessment(
                facts.phrase,facts.hand,facts.bpm,recorder.presses,
                from_beat=facts.from_beat,elapsed_seconds=musical_at,
                tempo=facts.tempo_map)
            judgement = next((entry for entry in assessment.notes
                if entry.observation is not None
                and entry.observation.press_id == recorded.press_id),None)
        live_event = self.live.receive(pitch=message.note,is_on=is_on,now=corrected_at,
            phrase=facts.phrase,hand=facts.hand,bpm=facts.bpm,from_beat=facts.from_beat,
            run_at=facts.run_at,running=facts.running,paused=facts.paused,preview=facts.preview,
            mode=facts.mode,transport_id=facts.transport_id,tempo_map=facts.tempo_map,
            at=musical_at,judgement=judgement)
        if live_event is not None:
            self.feedback_events.publish({**live_event,**feedback_take})
        if facts.mode == "learn":
            if teaching is not None and self.midi.connected:
                teaching.receive(pitch=message.note,is_on=is_on,
                    channel=getattr(message,"channel",0),at=received_at)
                if self.capture.attempt_id is not None:
                    self.capture.guided.add(message.note,is_on,
                        received_at-self.capture.origin-self.capture.context["monotonic_start"])
            return
        if facts.mode == "listen":
            return
