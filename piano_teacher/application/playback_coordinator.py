"""Only authority for graphical playback admission and take authorization.

The embedded desktop app requires a physical score-admission receipt for every
timed start (including MIDI shortcuts, automatic continuation, Listen and
resume). Headless engines explicitly use the independent no-presentation
adapter; they do not pretend a score was drawn.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable
from .playback_facts import PlaybackRuntimeFacts
from enum import Enum
import math

from .musical_scheduler import SCHEDULER, SNAPSHOT_LATENCY_SECONDS
from .physical_admission import PhysicalAdmissionEvidence, choose_admission_deadline
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
    tempo_segments: tuple[tuple[float, float, float], ...]
    count_in: CountInPlan
    resume_remaining_beats: float
    earliest_deadline_ms: float
    requested_at: float
    transition: PlaybackTransition | None = None
    fixed_deadline_ms: float | None = None

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
    evidence_sampled_at_ms: float
    evidence_travel_ms: float
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

    def enable_presentation(self, facts: PlaybackRuntimeFacts) -> None:
        if facts.running or self.intent is not None:
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

    def _valid_source(self, facts: PlaybackRuntimeFacts,
                      intent: PlaybackIntent) -> bool:
        source = facts.source
        return (source is not None
                and source.fingerprint == intent.fingerprint
                and source.stage_key == intent.stage_key
                and source.revision == intent.revision
                and abs(source.end_beat-intent.end_beat) < 1e-7
                and source.hand == intent.hand
                and abs(source.bpm-intent.bpm) < 1e-7
                and intent.generation == self.generation)

    def request(self, facts: PlaybackRuntimeFacts, *, action: str, mode: str,
                from_beat: float, earliest_deadline: float | None = None,
                count_in_beats: float | None = None,
                transition: PlaybackTransition | None = None,
                fixed_deadline: float | None = None) -> PlaybackIntent:
        if not self.presentation_required:
            raise RuntimeError("A graphical admission request requires presentation mode")
        source = facts.source
        if source is None:
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
                or transition.exposure.stage_key != source.stage_key
                or transition.exposure.hand != source.hand):
            raise ValueError("Playback transition disagrees with its selected exposure")
        if self.intent is not None:
            existing = self.intent
            if (self._valid_source(facts, existing)
                    and existing.action == action and existing.mode == mode
                    and abs(existing.from_beat - from_beat) < 1e-7):
                return existing
            # A replacement intent may be prepared while the preceding
            # graded take is still settling. Superseding only withdraws
            # its provisional successor; it must not erase the authoritative
            # identity of the currently playing take.
            self.cancel_pending("superseded")
        bar, meter = source.count_in_bar_beats, source.count_in_meter
        count_in = (SCHEDULER.count_in_beats(bar, source.bpm)
                    if count_in_beats is None else float(count_in_beats))
        if count_in < 0 or not math.isfinite(count_in):
            raise ValueError("Invalid count-in duration")
        now = facts.now
        bpm = source.bpm
        count_plan = CountInPlan.create(bar_beats=bar,meter=meter,bpm=bpm,beats=count_in)
        source_segments = source.tempo_segments
        resume_remaining = 0.0
        if (action == "resume" and facts.pause_context == "count_in"
                and facts.running and facts.paused
                and facts.run_at >
                    facts.paused_at):
            resume_remaining = min(count_in, SCHEDULER.seconds_beats(
                facts.run_at -
                facts.paused_at, bpm))
        # Admission must complete before the ENTIRE last bar begins. A
        # longer preceding silent runway is allowed, never an extra bar.
        earliest = max(
            now + SCHEDULER.beats_seconds(count_in, bpm)
            + SNAPSHOT_LATENCY_SECONDS,
            earliest_deadline if earliest_deadline is not None else 0.0)
        if fixed_deadline is not None:
            if action != "auto" or not math.isfinite(fixed_deadline) or fixed_deadline <= now:
                raise ValueError("An automatic continuation requires its future exact deadline")
            earliest = fixed_deadline
        self.sequence += 1
        attempt = 0
        take_id = (self.active_take_id if action == "resume"
                   and self.active_take_id
                   else f"{source.fingerprint}:{source.revision}:take:{self.sequence}")
        self.intent = PlaybackIntent(
            intent_id=f"{source.fingerprint}:{self.generation}:{self.sequence}",
            take_id=take_id, generation=self.generation,
            attempt=attempt, action=action,
            fingerprint=source.fingerprint, stage_key=source.stage_key,
            revision=source.revision,hand=source.hand,mode=mode,
            from_beat=float(from_beat),
            end_beat=float(source.end_beat), bpm=bpm,
            tempo_segments=source_segments,
            count_in=count_plan,
            resume_remaining_beats=resume_remaining,
            earliest_deadline_ms=earliest * 1000.0,
            requested_at=now,
            transition=transition,
            fixed_deadline_ms=None if fixed_deadline is None else fixed_deadline*1000.0)
        self.receipt = None
        self.state = PlaybackState.AWAITING_ADMISSION
        self.failure = ""
        return self.intent

    def _require_intent(self, facts: PlaybackRuntimeFacts, intent_id: str, attempt: int) -> PlaybackIntent:
        intent = self.intent
        if (intent is None or intent.intent_id != intent_id
                or intent.attempt != attempt
                or not self._valid_source(facts, intent)):
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

    def reserve(self, facts: PlaybackRuntimeFacts, *, intent_id: str, attempt: int,
                take_id: str, fingerprint: str, stage_key: str,
                revision: int, hand: str, source_from_beat: float,
                source_end_beat: float, sampled_at_ms: float, travel_ms: float,
                world_origin: float, queue_generation: int,
                renderer_generation: int, reused_count_in: bool = False) -> dict:
        """Authorize a musical deadline from an immutable physical witness.

        The native renderer supplies source placement/travel evidence,
        never an absolute musical deadline. Source identity, score
        revision, freshness, counting and tempo policy are validated
        within this one application transaction.
        """
        intent = self._require_intent(facts, intent_id, attempt)
        if (take_id != intent.take_id or fingerprint != intent.fingerprint
                or stage_key != intent.stage_key or revision != intent.revision
                or hand != intent.hand
                or abs(float(source_from_beat)-intent.from_beat) > 1e-7
                or abs(float(source_end_beat)-intent.end_beat) > 1e-7):
            raise ValueError("Score reservation has the wrong musical source")
        evidence = PhysicalAdmissionEvidence(
            sampled_at_ms=float(sampled_at_ms), travel_ms=float(travel_ms),
            world_origin=float(world_origin),
            queue_generation=queue_generation,
            renderer_generation=renderer_generation)
        if self.receipt is not None:
            # A lost native ACK may retransmit the identical physical
            # reservation after its measurement has aged out. The receipt
            # already binds this exact source/attempt/witness, so returning
            # it is safe. Different evidence must never replace ink under
            # the same intent or negotiate a second musical deadline.
            receipt = self.receipt
            if (receipt.intent_id == intent_id and receipt.attempt == attempt
                    and receipt.world_origin == evidence.world_origin
                    and receipt.queue_generation == evidence.queue_generation
                    and receipt.renderer_generation == evidence.renderer_generation
                    and receipt.evidence_sampled_at_ms == evidence.sampled_at_ms
                    and receipt.evidence_travel_ms == evidence.travel_ms
                    and receipt.reused_count_in == reused_count_in):
                return self._receipt_response(receipt)
            raise ValueError("Conflicting score reservation for the same intent")
        deadline_ms = choose_admission_deadline(
            intent, facts, evidence, reused_count_in=reused_count_in)
        self.receipt = ScoreReceipt(
            intent_id=intent_id, attempt=attempt, take_id=take_id,
            fingerprint=fingerprint, stage_key=stage_key, revision=revision,
            hand=hand,source_from_beat=intent.from_beat,
            source_end_beat=intent.end_beat,
            segment_id=f"{intent_id}:segment:{attempt}",
            deadline_ms=deadline_ms, world_origin=evidence.world_origin,
            queue_generation=evidence.queue_generation,
            renderer_generation=evidence.renderer_generation,
            evidence_sampled_at_ms=evidence.sampled_at_ms,
            evidence_travel_ms=evidence.travel_ms,
            reused_count_in=bool(reused_count_in))
        self.state = PlaybackState.RESERVED
        return self._receipt_response(self.receipt)

    @staticmethod
    def _receipt_response(receipt: ScoreReceipt) -> dict:
        return {"intent_id": receipt.intent_id, "attempt": receipt.attempt,
                "segment_id": receipt.segment_id, "take_id": receipt.take_id,
                "deadline_ms": receipt.deadline_ms, "reserved": True}

    def present(self, facts: PlaybackRuntimeFacts, *, intent_id: str,
                attempt: int, segment_id: str, commit: Callable,
                capture: Callable[[], PlaybackRuntimeFacts],
                abort: Callable[[str], None]) -> dict:
        for past_id, result in self._completed:
            if past_id == segment_id and result["intent_id"] == intent_id:
                return dict(result)
        intent = self._require_intent(facts, intent_id, attempt)
        receipt = self.receipt
        if (receipt is None or receipt.segment_id != segment_id
                or receipt.intent_id != intent_id or receipt.attempt != attempt):
            raise ValueError("No matching score reservation to present")
        now = facts.now
        remaining = (intent.resume_remaining_beats if receipt.reused_count_in
                     else 0.0 if intent.fixed_deadline_ms is not None else intent.count_in_beats)
        count_in_seconds = SCHEDULER.beats_seconds(remaining, intent.bpm)
        if receipt.deadline_ms / 1000.0 < now + count_in_seconds - 1e-4:
            self._expire(message="Score admission expired before its count-in")
            raise ValueError("Score reservation expired; admit the new attempt")
        # No graded/audio transport mutation happened in either prior step.
        # This is the single authorization boundary. An exception leaves
        # the intent retryable; a successful commit fixes the take's clock.
        self.state = PlaybackState.AUTHORIZED
        try:
            commit(intent, receipt)
            post = capture()
            # A successful command is not proof of a successful transaction.
            # Verify the ACTUAL transport mutation against the previously
            # admitted source and monotonic downbeat before publishing it.
            if not post.running or post.paused:
                raise RuntimeError("Playback commit did not activate a take")
            if post.mode != intent.mode or not self._valid_source(post, intent):
                raise RuntimeError("Playback commit changed the admitted source")
            if intent.action == "resume":
                if abs(post.resume_grading_after -
                       receipt.deadline_ms/1000.0) > 1e-5:
                    raise RuntimeError("Resume grading does not match admitted onset")
            elif (abs(post.play_from_beat-intent.from_beat) > 1e-5
                  or abs(post.run_at -
                         receipt.deadline_ms/1000.0) > 1e-5):
                raise RuntimeError("Playback origin differs from admitted score")
        except BaseException:
            # Partial start failures must never leave a graded transport
            # running without a matching authorized visual segment.
            try:
                abort("playback_authorization_failed")
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
                "end_beat": intent.end_beat,
                "hand": intent.hand,
            },
            "mode": intent.mode,
            "graded": intent.mode in ("practice", "perform")
                      and not post.preview_only,
            "bpm": intent.bpm,
            "count_in_beats": intent.count_in_beats,
            "count_in_meter": list(intent.count_in_meter),
            "count_in_plan": intent.count_in.snapshot(),
            "reused_count_in": receipt.reused_count_in,
            "tempo_segments":[{"start_beat":start,"end_beat":end,"bpm":rate}
                for start,end,rate in intent.tempo_segments],
            "deadline_ms": receipt.deadline_ms,
            "world_origin": receipt.world_origin,
            "transport_id": post.transport_id,
        }
        self.intent = None
        self.receipt = None
        activation = max(post.run_at,
                         post.resume_grading_after)
        self.state = (PlaybackState.COUNT_IN if post.running
                      and post.now < activation
                      else PlaybackState.PLAYING if post.running
                      else PlaybackState.AUTHORIZED)
        result = {
            "intent_id": intent_id, "attempt": attempt,
            "take_id": receipt.take_id, "segment_id": segment_id,
            "deadline_ms": receipt.deadline_ms,
            "transport_id": post.transport_id, "authorized": True}
        self._completed.append((segment_id, dict(result)))
        return result

    def withdraw(self, facts: PlaybackRuntimeFacts, *, intent_id: str, attempt: int,
                 reason: str) -> dict:
        self._require_intent(facts, intent_id, attempt)
        self._expire(message=reason)
        return {"withdrawn": True, "intent_id": intent_id,
                "next_attempt": self.intent.attempt}

    def fail(self, *, take_id: str, segment_id: str, reason: str,
             notify_failure: Callable[[str], None]) -> None:
        if self.active_take_id != take_id or self.active_segment_id != segment_id:
            raise ValueError("Stale playback failure")
        notify_failure("score_presentation_failed")
        self.state = PlaybackState.FAILED
        self.failure = reason

    def advance(self, facts: PlaybackRuntimeFacts) -> None:
        if not self.presentation_required:
            return
        if self.intent is not None:
            if not self._valid_source(facts, self.intent):
                self.invalidate("Source changed before notation admission")
            return
        if not self.active_take_id:
            return
        if facts.paused:
            self.state = PlaybackState.PAUSED
        elif facts.running:
            activation = max(facts.run_at,
                             facts.resume_grading_after)
            self.state = (PlaybackState.COUNT_IN if facts.now < activation
                          else PlaybackState.PLAYING)
        elif facts.pending_result:
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
            "tempo_segments":[{"start_beat":start,"end_beat":end,"bpm":rate}
                for start,end,rate in intent.tempo_segments],
            "count_in_beats": intent.count_in_beats,
            "count_in_meter": list(intent.count_in_meter),
            "count_in_plan": intent.count_in.snapshot(),
            "resume_remaining_beats":intent.resume_remaining_beats,
            "earliest_deadline_ms": intent.earliest_deadline_ms,
            "fixed_deadline_ms": intent.fixed_deadline_ms,
            "status": self.state.value,
        }
        timeline = {"state": self.state.value, "take_id": self.active_take_id,
                    "segment_id": self.active_segment_id,
                    "deadline_ms": self.active_deadline_ms,
                    "current": dict(self.active_segment) if self.active_segment else None,
                    "failure": self.failure}
        return request, timeline
