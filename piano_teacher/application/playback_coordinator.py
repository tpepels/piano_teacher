"""Only authority for graphical playback admission and take authorization.

The embedded desktop app requires a physical score-admission receipt for every
timed start (including MIDI shortcuts, automatic continuation, Listen and
resume). Headless engines explicitly use the independent no-presentation
adapter; they do not pretend a score was drawn.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math

from .musical_scheduler import SCHEDULER, SNAPSHOT_LATENCY_SECONDS
from .playback_transitions import CountInPlan, PlaybackTransition


class PlaybackState(str, Enum):
    IDLE = "idle"
    AWAITING_ADMISSION = "awaiting_admission"
    RESERVED = "reserved"
    AUTHORIZED = "authorized"
    COUNT_IN = "count_in"
    PLAYING = "playing"
    PAUSED = "paused"
    SETTLING = "settling"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PlaybackIntent:
    intent_id: str
    take_id: str
    generation: int
    attempt: int
    action: str
    fingerprint: str
    stage_key: str
    revision: int
    hand: str
    mode: str
    from_beat: float
    end_beat: float
    bpm: float
    count_in: CountInPlan
    resume_remaining_beats: float
    earliest_deadline_ms: float
    requested_at: float
    transition: PlaybackTransition | None = None

    @property
    def count_in_beats(self) -> float:
        return self.count_in.beats

    @property
    def count_in_meter(self) -> tuple[int, int]:
        return self.count_in.meter


@dataclass(frozen=True, slots=True)
class ScoreReceipt:
    intent_id: str
    attempt: int
    take_id: str
    fingerprint: str
    stage_key: str
    revision: int
    hand: str
    source_from_beat: float
    source_end_beat: float
    segment_id: str
    deadline_ms: float
    world_origin: float
    queue_generation: int
    renderer_generation: int
    reused_count_in: bool


class PlaybackCoordinator:
    """The sole gate between a chosen exposure and executable musical time.

    No callback waits for the GUI. The engine publishes an intent; Godot
    prepares/arms immutable ink and performs reserve -> present through the
    existing in-process worker. Presentation is acknowledged before grading
    begins. The intent remains retryable when a reservation expires.
    """

    def __init__(self, *, presentation_required: bool = False):
        self.presentation_required = presentation_required
        self.state = PlaybackState.IDLE
        self.generation = 0
        self.sequence = 0
        self.intent: PlaybackIntent | None = None
        self.receipt: ScoreReceipt | None = None
        self.active_take_id = ""
        self.active_segment_id = ""
        self.active_deadline_ms = 0.0
        self.active_segment: dict = {}
        self._completed: deque[tuple[str, dict]] = deque(maxlen=16)
        self.failure = ""

    def enable_presentation(self, engine) -> None:
        if engine.running or self.intent is not None:
            raise ValueError("Cannot enable score admission during a take")
        self.presentation_required = True

    def invalidate(self, reason: str) -> None:
        self.generation += 1
        self.intent = None
        self.receipt = None
        self.state = PlaybackState.IDLE
        self.active_take_id = ""
        self.active_segment_id = ""
        self.active_deadline_ms = 0.0
        self.active_segment = {}
        self.failure = reason

    def cancel_pending(self, reason: str) -> None:
        """Cancel only the unpresented successor, preserving an older take."""
        if self.intent is None:
            return
        self.generation += 1
        self.intent = None
        self.receipt = None
        self.failure = reason
        self.state = (PlaybackState.PAUSED if self.active_take_id
                      else PlaybackState.IDLE)

    def _valid_source(self, engine, intent: PlaybackIntent) -> bool:
        return (engine.plan is not None
                and engine.fingerprint == intent.fingerprint
                and engine.plan.identity == intent.stage_key
                and engine.score_revision == intent.revision
                and abs(engine.plan.active_phrase.end-engine.plan.active_phrase.start-intent.end_beat) < 1e-7
                and engine.plan.hand == intent.hand
                and abs(float(engine.plan.bpm)-intent.bpm) < 1e-7
                and intent.generation == self.generation)

    def request(self, engine, *, action: str, mode: str,
                from_beat: float, earliest_deadline: float | None = None,
                count_in_beats: float | None = None,
                transition: PlaybackTransition | None = None) -> PlaybackIntent:
        if not self.presentation_required:
            raise RuntimeError("A graphical admission request requires presentation mode")
        if engine.plan is None:
            raise ValueError("Open a piece before starting")
        if action not in {"start", "restart", "resume", "auto", "score_ready",
                          "listen"}:
            raise ValueError("Unsupported playback intent")
        if mode not in {"practice", "perform", "listen"}:
            raise ValueError("Untimed lessons do not authorize graded playback")
        if transition is not None and (
                transition.action != action
                or transition.exposure.mode != mode
                or abs(transition.exposure.from_beat-from_beat) > 1e-7
                or transition.exposure.stage_key != engine.plan.identity
                or transition.exposure.hand != engine.plan.hand):
            raise ValueError("Playback transition disagrees with its selected exposure")
        if self.intent is not None:
            existing = self.intent
            if (self._valid_source(engine, existing)
                    and existing.action == action and existing.mode == mode
                    and abs(existing.from_beat - from_beat) < 1e-7):
                return existing
            # A replacement intent may be prepared while the preceding
            # graded take is still settling. Superseding only withdraws
            # its provisional successor; it must not erase the authoritative
            # identity of the currently playing take.
            self.cancel_pending("superseded")
        bar, meter = engine.attempt_progression.count_in_bar(
            phrase=engine.plan.active_phrase,
            boundaries=engine.plan.piece.bar_boundaries,
            time_signatures=engine.plan.piece.time_signatures,
            position=from_beat)[1:]
        count_in = (SCHEDULER.count_in_beats(bar, engine.plan.bpm)
                    if count_in_beats is None else float(count_in_beats))
        if count_in < 0 or not math.isfinite(count_in):
            raise ValueError("Invalid count-in duration")
        now = engine.now()
        bpm = float(engine.plan.bpm)
        count_plan = CountInPlan.create(
            bar_beats=bar,meter=tuple(meter),bpm=bpm,beats=count_in)
        resume_remaining = 0.0
        if (action == "resume" and engine.pause_context == "count_in"
                and engine.running and engine.visual_transport.paused
                and engine.visual_transport.run_at >
                    engine.visual_transport.paused_at):
            resume_remaining = min(count_in, SCHEDULER.seconds_beats(
                engine.visual_transport.run_at -
                engine.visual_transport.paused_at, bpm))
        # Admission must complete before the ENTIRE last bar begins. A
        # longer preceding silent runway is allowed, never an extra bar.
        earliest = max(
            now + SCHEDULER.beats_seconds(count_in, bpm)
            + SNAPSHOT_LATENCY_SECONDS,
            earliest_deadline if earliest_deadline is not None else 0.0)
        self.sequence += 1
        attempt = 0
        take_id = (self.active_take_id if action == "resume"
                   and self.active_take_id
                   else f"{engine.fingerprint}:{engine.score_revision}:take:{self.sequence}")
        self.intent = PlaybackIntent(
            intent_id=f"{engine.fingerprint}:{self.generation}:{self.sequence}",
            take_id=take_id, generation=self.generation,
            attempt=attempt, action=action,
            fingerprint=engine.fingerprint, stage_key=engine.plan.identity,
            revision=engine.score_revision,hand=engine.plan.hand,mode=mode,
            from_beat=float(from_beat),
            end_beat=float(engine.plan.active_phrase.end-engine.plan.active_phrase.start), bpm=bpm,
            count_in=count_plan,
            resume_remaining_beats=resume_remaining,
            earliest_deadline_ms=earliest * 1000.0,
            requested_at=now,
            transition=transition)
        self.receipt = None
        self.state = PlaybackState.AWAITING_ADMISSION
        self.failure = ""
        return self.intent

    def _require_intent(self, engine, intent_id: str, attempt: int) -> PlaybackIntent:
        intent = self.intent
        if (intent is None or intent.intent_id != intent_id
                or intent.attempt != attempt
                or not self._valid_source(engine, intent)):
            raise ValueError("Stale or cancelled playback intent")
        return intent

    def _expire(self, *, message: str) -> None:
        if self.intent is None:
            return
        from dataclasses import replace
        self.intent = replace(self.intent, attempt=self.intent.attempt + 1)
        self.receipt = None
        self.state = PlaybackState.AWAITING_ADMISSION
        self.failure = message

    def reserve(self, engine, *, intent_id: str, attempt: int,
                take_id: str, fingerprint: str, stage_key: str,
                revision: int, hand: str, source_from_beat: float,
                source_end_beat: float,
                deadline_ms: float, world_origin: float, queue_generation: int,
                renderer_generation: int, reused_count_in: bool = False) -> dict:
        intent = self._require_intent(engine, intent_id, attempt)
        if (take_id != intent.take_id or fingerprint != intent.fingerprint
                or stage_key != intent.stage_key or revision != intent.revision
                or hand != intent.hand
                or abs(float(source_from_beat)-intent.from_beat) > 1e-7
                or abs(float(source_end_beat)-intent.end_beat) > 1e-7):
            raise ValueError("Score reservation has the wrong musical source")
        if (not math.isfinite(float(deadline_ms))
                or not math.isfinite(float(world_origin))):
            raise ValueError("Score reservation has invalid physical coordinates")
        if reused_count_in and not (
                intent.action == "resume" and intent.resume_remaining_beats > 0):
            raise ValueError("Only a paused count-in can reuse its spoken beats")
        earliest = intent.earliest_deadline_ms
        if reused_count_in:
            earliest = (intent.requested_at + SNAPSHOT_LATENCY_SECONDS
                        + SCHEDULER.beats_seconds(
                            intent.resume_remaining_beats,intent.bpm)) * 1000.0
        chosen = SCHEDULER.resolve(
            intent.action,now=engine.now(),bpm=intent.bpm,
            count_in_beats=(intent.resume_remaining_beats
                if reused_count_in else intent.count_in_beats),
            latency=0.0,
            physical_at=deadline_ms/1000.0,
            earliest_at=earliest/1000.0)
        if chosen.run_at > deadline_ms/1000.0 + 1e-5:
            raise ValueError(
                "Score admission is earlier than the authoritative musical schedule")
        if self.receipt is not None:
            receipt = self.receipt
            if (receipt.intent_id == intent_id and receipt.attempt == attempt
                    and receipt.deadline_ms == deadline_ms
                    and receipt.world_origin == world_origin):
                return self._receipt_response(receipt)
            raise ValueError("Conflicting score reservation for the same intent")
        self.receipt = ScoreReceipt(
            intent_id=intent_id, attempt=attempt, take_id=take_id,
            fingerprint=fingerprint, stage_key=stage_key, revision=revision,
            hand=hand,source_from_beat=intent.from_beat,
            source_end_beat=intent.end_beat,
            segment_id=f"{intent_id}:segment:{attempt}",
            deadline_ms=float(deadline_ms), world_origin=float(world_origin),
            queue_generation=int(queue_generation),
            renderer_generation=int(renderer_generation),
            reused_count_in=bool(reused_count_in))
        self.state = PlaybackState.RESERVED
        return self._receipt_response(self.receipt)

    @staticmethod
    def _receipt_response(receipt: ScoreReceipt) -> dict:
        return {"intent_id": receipt.intent_id, "attempt": receipt.attempt,
                "segment_id": receipt.segment_id, "take_id": receipt.take_id,
                "deadline_ms": receipt.deadline_ms, "reserved": True}

    def present(self, engine, *, intent_id: str, attempt: int,
                segment_id: str) -> dict:
        for past_id, result in self._completed:
            if past_id == segment_id and result["intent_id"] == intent_id:
                return dict(result)
        intent = self._require_intent(engine, intent_id, attempt)
        receipt = self.receipt
        if (receipt is None or receipt.segment_id != segment_id
                or receipt.intent_id != intent_id or receipt.attempt != attempt):
            raise ValueError("No matching score reservation to present")
        now = engine.now()
        remaining = (intent.resume_remaining_beats if receipt.reused_count_in
                     else intent.count_in_beats)
        count_in_seconds = SCHEDULER.beats_seconds(remaining, intent.bpm)
        if receipt.deadline_ms / 1000.0 < now + count_in_seconds - 1e-4:
            self._expire(message="Score admission expired before its count-in")
            raise ValueError("Score reservation expired; admit the new attempt")
        # No graded/audio transport mutation happened in either prior step.
        # This is the single authorization boundary. An exception leaves
        # the intent retryable; a successful commit fixes the take's clock.
        self.state = PlaybackState.AUTHORIZED
        try:
            engine._commit_playback_intent(intent, receipt)
            # A successful command is not proof of a successful transaction.
            # Verify the ACTUAL transport mutation against the previously
            # admitted source and monotonic downbeat before publishing it.
            if not engine.running or engine.visual_transport.paused:
                raise RuntimeError("Playback commit did not activate a take")
            if engine.mode != intent.mode or not self._valid_source(engine, intent):
                raise RuntimeError("Playback commit changed the admitted source")
            if intent.action == "resume":
                if abs(engine.midi_ingress.resume_grading_after -
                       receipt.deadline_ms/1000.0) > 1e-5:
                    raise RuntimeError("Resume grading does not match admitted onset")
            elif (abs(engine.visual_transport.play_from_beat-intent.from_beat) > 1e-5
                  or abs(engine.visual_transport.run_at -
                         receipt.deadline_ms/1000.0) > 1e-5):
                raise RuntimeError("Playback origin differs from admitted score")
        except BaseException:
            # Partial start failures must never leave a graded transport
            # running without a matching authorized visual segment.
            try:
                engine._stop(reason="playback_authorization_failed")
            finally:
                self.intent = None
                self.receipt = None
                self.active_take_id = ""
                self.active_segment_id = ""
                self.active_deadline_ms = 0.0
                self.active_segment = {}
                self.failure = "The admitted score did not match the musical transport"
                self.state = PlaybackState.FAILED
            raise
        self.active_take_id = receipt.take_id
        self.active_segment_id = receipt.segment_id
        self.active_deadline_ms = receipt.deadline_ms
        self.active_segment = {
            "segment_id": receipt.segment_id,
            "take_id": receipt.take_id,
            "source": {
                "fingerprint": intent.fingerprint,
                "stage_key": intent.stage_key,
                "revision": intent.revision,
                "from_beat": intent.from_beat,
                "end_beat": engine.plan.active_phrase.end -
                            engine.plan.active_phrase.start,
                "hand": engine.plan.hand,
            },
            "mode": intent.mode,
            "graded": intent.mode in ("practice", "perform")
                      and not engine.preview_only,
            "bpm": intent.bpm,
            "count_in_beats": intent.count_in_beats,
            "count_in_meter": list(intent.count_in_meter),
            "count_in_plan": intent.count_in.snapshot(),
            "deadline_ms": receipt.deadline_ms,
            "world_origin": receipt.world_origin,
            "transport_id": engine.transport_id,
        }
        self.intent = None
        self.receipt = None
        activation = max(engine.visual_transport.run_at,
                         engine.midi_ingress.resume_grading_after)
        self.state = (PlaybackState.COUNT_IN if engine.running
                      and engine.now() < activation
                      else PlaybackState.PLAYING if engine.running
                      else PlaybackState.AUTHORIZED)
        result = {
            "intent_id": intent_id, "attempt": attempt,
            "take_id": receipt.take_id, "segment_id": segment_id,
            "deadline_ms": receipt.deadline_ms,
            "transport_id": engine.transport_id, "authorized": True}
        self._completed.append((segment_id, dict(result)))
        return result

    def withdraw(self, engine, *, intent_id: str, attempt: int,
                 reason: str) -> dict:
        self._require_intent(engine, intent_id, attempt)
        self._expire(message=reason)
        return {"withdrawn": True, "intent_id": intent_id,
                "next_attempt": self.intent.attempt}

    def fail(self, engine, *, take_id: str, segment_id: str,
             reason: str) -> None:
        if self.active_take_id != take_id or self.active_segment_id != segment_id:
            raise ValueError("Stale playback failure")
        if engine.running:
            engine._stop(reason="score_presentation_failed")
        self.state = PlaybackState.FAILED
        self.failure = reason
        engine.feedback = "The score stopped displaying correctly"
        engine.next_action = "Select this lesson again after checking the score."

    def advance(self, engine) -> None:
        if not self.presentation_required:
            return
        if self.intent is not None:
            if not self._valid_source(engine, self.intent):
                self.invalidate("Source changed before notation admission")
            return
        if not self.active_take_id:
            return
        if engine.visual_transport.paused:
            self.state = PlaybackState.PAUSED
        elif engine.running:
            activation = max(engine.visual_transport.run_at,
                             engine.midi_ingress.resume_grading_after)
            self.state = (PlaybackState.COUNT_IN if engine.now() < activation
                          else PlaybackState.PLAYING)
        elif engine.pending_result is not None:
            self.state = PlaybackState.SETTLING
        elif self.state not in (PlaybackState.FAILED, PlaybackState.IDLE):
            self.state = PlaybackState.COMPLETE

    def status(self) -> dict:
        """Read-only transaction reconciliation, including lost responses.

        The worker can complete an authorization after its Godot request
        times out. A client must query this state before rolling back ink.
        """
        intent = self.intent
        receipt = self.receipt
        return {
            "state": self.state.value,
            "generation": self.generation,
            "intent_id": intent.intent_id if intent else "",
            "attempt": intent.attempt if intent else -1,
            "reserved_segment_id": receipt.segment_id if receipt else "",
            "active_segment_id": self.active_segment_id,
            "active_take_id": self.active_take_id,
            "active_deadline_ms": self.active_deadline_ms,
        }

    def snapshot(self) -> tuple[dict | None, dict]:
        intent = self.intent
        request = None if intent is None else {
            "intent_id": intent.intent_id, "take_id": intent.take_id,
            "generation": intent.generation, "attempt": intent.attempt,
            "action": intent.action, "mode": intent.mode,
            "fingerprint": intent.fingerprint,
            "stage_key": intent.stage_key, "revision": intent.revision,
            "hand":intent.hand,
            "from_beat": intent.from_beat,
            "end_beat": intent.end_beat, "bpm": intent.bpm,
            "count_in_beats": intent.count_in_beats,
            "count_in_meter": list(intent.count_in_meter),
            "count_in_plan": intent.count_in.snapshot(),
            "resume_remaining_beats":intent.resume_remaining_beats,
            "earliest_deadline_ms": intent.earliest_deadline_ms,
            "status": self.state.value,
        }
        timeline = {"state": self.state.value, "take_id": self.active_take_id,
                    "segment_id": self.active_segment_id,
                    "deadline_ms": self.active_deadline_ms,
                    "current": dict(self.active_segment) if self.active_segment else None,
                    "failure": self.failure}
        return request, timeline
