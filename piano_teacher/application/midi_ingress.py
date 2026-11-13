"""Validated physical-note routing with one explicit musical timestamp.

The composition root owns the callback lock and commands; this owner handles
shortcut precedence, ungraded resume suppression and actual note consumers.
No handler receives an engine or discovers collaborators through a root.
"""
from collections import deque
from dataclasses import dataclass


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

    def deliver(self,message,*,facts,received_at,corrected_at,musical_at,recorder,teaching,feedback_take):
        if message.type not in ("note_on","note_off"):
            return
        is_on = message.type == "note_on" and message.velocity > 0
        live_event = self.live.receive(pitch=message.note,is_on=is_on,now=corrected_at,
            phrase=facts.phrase,hand=facts.hand,bpm=facts.bpm,from_beat=facts.from_beat,
            run_at=facts.run_at,running=facts.running,paused=facts.paused,preview=facts.preview,
            mode=facts.mode,transport_id=facts.transport_id,tempo_map=facts.tempo_map,at=musical_at)
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
        if facts.running and recorder:
            if is_on:
                if not facts.paused and received_at >= facts.run_at:
                    recorder.add(message.note,True,musical_at)
            else:
                recorder.add(message.note,False,musical_at)
