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


# The backend owns the retry/timeout budget. A native renderer must never
# leave a session waiting for notation admission indefinitely.
MAX_ADMISSION_ATTEMPTS = 3
MAX_ADMISSION_WAIT_SECONDS = 120.0


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
        # Terminal automatic admission failures are scoped to the exact
        # source/exposure. A repeated score_ready or completed Listen-audio
        # notification cannot create infinitely many new intent IDs after
        # the documented three physical attempts have been exhausted.
        self._terminal_automatic_source: tuple | None = None

    @staticmethod
    def _automatic_source_key(facts: PlaybackRuntimeFacts, *,
                              mode: str, from_beat: float) -> tuple | None:
        source = facts.source
        if source is None:
            return None
        return (source.fingerprint, source.stage_key, source.revision,
                source.hand, source.end_beat, source.bpm, mode,
                round(float(from_beat), 7))

    def automatic_request_blocked(self, facts: PlaybackRuntimeFacts, *,
                                  action: str, mode: str,
                                  from_beat: float) -> bool:
        # Explicit Start/Restart/Resume are new user intents. Listen,
        # score_ready and auto are asynchronous reactions that must not
        # resurrect their own terminally failed physical admission.
        return (action in ("listen", "score_ready", "auto")
                and self._terminal_automatic_source is not None
                and self._terminal_automatic_source ==
                    self._automatic_source_key(
                        facts, mode=mode, from_beat=from_beat))

    def enable_presentation(self, facts: PlaybackRuntimeFacts) -> None:
        if facts.running or self.intent is not None:
            raise ValueError("Cannot enable score admission during a take")
        self.presentation_required = True

    def invalidate(self, reason: str) -> None:
        # New, explicitly selected exposure/score revision permits a fresh
        # automatic Listen/Tempo admission, not a new attempt on old ink.
        self._terminal_automatic_source = None
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
        if self.automatic_request_blocked(
                facts, action=action, mode=mode, from_beat=from_beat):
            raise ValueError(
                "Automatic score admission already failed for this source")
        if transition is not None and (
                transition.action != action
                or transition.exposure.mode != mode
                or abs(transition.exposure.from_beat-from_beat) > 1e-7
                or transition.exposure.stage_key != source.stage_key
                or transition.exposure.hand != source.hand):
            raise ValueError("Playback transition disagrees with its selected exposure")
        if self.intent is not None:
            existing = self.intent
            same_exposure = (
                self._valid_source(facts, existing)
                and existing.mode == mode
                and abs(existing.from_beat - from_beat) < 1e-7)
            if same_exposure and (
                    existing.action == action
                    or action in ("listen", "score_ready", "auto")):
                # An asynchronous readiness/audio/repeat callback may
                # arrive after an explicit Start, Retry or Resume already
                # selected this very source. It confirms availability;
                # it cannot silently cancel the stronger user choice,
                # reset a partial count-in or create a second deadline.
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
        if action in ("start", "restart", "resume"):
            # Clear the terminal latch ONLY after all source, transition,
            # meter and countdown inputs have been validated. A malformed
            # manual request must not unlock another automatic retry.
            self._terminal_automatic_source = None
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
        intent = self.intent
        # A pre-announced automatic repeat cannot have another deadline.
        # Retrying its expired world slot would silently add another bar.
        # Other physical failures have a bounded number of new attempts.
        if (intent.fixed_deadline_ms is not None or
                intent.attempt + 1 >= MAX_ADMISSION_ATTEMPTS):
            self._terminal_automatic_source = (
                intent.fingerprint, intent.stage_key, intent.revision,
                intent.hand, intent.end_beat, intent.bpm,
                intent.mode, round(intent.from_beat, 7))
            self.intent = None
            self.receipt = None
            self.state = PlaybackState.FAILED
            self.failure = message
            return
        from dataclasses import replace
        self.intent = replace(intent, attempt=intent.attempt + 1)
        self.receipt = None
        self.state = PlaybackState.AWAITING_ADMISSION
        self.failure = message

    def reserve(self, facts: PlaybackRuntimeFacts, *, intent_id: str, attempt: int,
                take_id: str, fingerprint: str, stage_key: str,
                revision: int, hand: str, source_from_beat: float,
                source_end_beat: float, sampled_at_ms: float, travel_ms: float,
                world_origin: float, queue_generation: int,
                renderer_generation: int) -> dict:
        """Reserve the backend-chosen musical deadline *before* ink is armed.

        This physical witness is a read-only earliest-feasible position.
        The renderer must arm the exact selected deadline on receipt,
        then attest its committed queue/world in playback.present.
        No grading, voice or Listen audio starts from this reservation.
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
                    and receipt.evidence_travel_ms == evidence.travel_ms):
                return self._receipt_response(receipt)
            raise ValueError("Conflicting score reservation for the same intent")
        deadline_ms = choose_admission_deadline(intent, facts, evidence)
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
            evidence_travel_ms=evidence.travel_ms)
        self.state = PlaybackState.RESERVED
        return self._receipt_response(self.receipt)

    @staticmethod
    def _receipt_response(receipt: ScoreReceipt) -> dict:
        """Immutable reservation identity and physical witness.

        Both the direct reserve reply and the read-only transaction ledger
        expose this same payload. A native client recovering a lost reply
        must prove it still holds exactly the source the backend reserved,
        including its physical queue generation and original measurement.
        """
        return {
            "intent_id": receipt.intent_id,
            "attempt": receipt.attempt,
            "segment_id": receipt.segment_id,
            "take_id": receipt.take_id,
            "deadline_ms": receipt.deadline_ms,
            "world_origin": receipt.world_origin,
            "queue_generation": receipt.queue_generation,
            "renderer_generation": receipt.renderer_generation,
            "sampled_at_ms": receipt.evidence_sampled_at_ms,
            "travel_ms": receipt.evidence_travel_ms,
            "reserved": True,
        }

    def present(self, facts: PlaybackRuntimeFacts, *, intent_id: str,
                attempt: int, segment_id: str, commit: Callable,
                capture: Callable[[], PlaybackRuntimeFacts],
                abort: Callable[[str], None],
                physical_world_origin: float | None = None,
                physical_sampled_at_ms: float | None = None,
                physical_travel_ms: float | None = None,
                physical_queue_generation: int | None = None,
                physical_renderer_generation: int | None = None) -> dict:
        for past_id, result in self._completed:
            if past_id == segment_id and result["intent_id"] == intent_id:
                # Idempotence applies only while the same authorization
                # remains the active source. A stale present retry must
                # never re-authorize notation from an earlier lesson/take.
                active_source = self.active_segment.get("source", {})
                source = facts.source
                if (result["attempt"] != attempt
                        or self.active_segment_id != segment_id
                        or self.active_take_id != result["take_id"]
                        or self.state in (PlaybackState.FAILED,
                                          PlaybackState.IDLE,
                                          PlaybackState.COMPLETE)
                        or source is None
                        or facts.mode != self.active_segment.get("mode")
                        or facts.transport_id != self.active_segment.get("transport_id")
                        or source.fingerprint != active_source.get("fingerprint")
                        or source.stage_key != active_source.get("stage_key")
                        or source.revision != active_source.get("revision")
                        or source.hand != active_source.get("hand")
                        or abs(source.end_beat - active_source.get("end_beat", -1)) > 1e-7):
                    raise ValueError("Playback authorization has been superseded")
                return dict(result)
        intent = self._require_intent(facts, intent_id, attempt)
        receipt = self.receipt
        if (receipt is None or receipt.segment_id != segment_id
                or receipt.intent_id != intent_id or receipt.attempt != attempt):
            raise ValueError("No matching score reservation to present")
        now = facts.now
        remaining = (0.0 if intent.fixed_deadline_ms is not None
                     else intent.count_in_beats)
        count_in_seconds = SCHEDULER.beats_seconds(remaining, intent.bpm)
        if receipt.deadline_ms / 1000.0 < now + count_in_seconds - 1e-4:
            self._expire(message="Score admission expired before its count-in")
            raise ValueError("Score reservation expired; admit the new attempt")
        # A reservation is only the backend's musical proposal. Physical
        # arming must have happened *after* it. Require a new authenticated
        # native measurement at the committed source/queue, and refuse
        # the authorization unless the ink reaches the downbeat exactly.
        if (physical_world_origin is None or
                physical_sampled_at_ms is None or
                physical_travel_ms is None or
                physical_queue_generation is None or
                physical_renderer_generation is None):
            raise ValueError("Physical score arm attestation required for playback")
        committed = PhysicalAdmissionEvidence(
            sampled_at_ms=float(physical_sampled_at_ms),
            travel_ms=float(physical_travel_ms),
            world_origin=float(physical_world_origin),
            queue_generation=physical_queue_generation,
            renderer_generation=physical_renderer_generation)
        arrived_ms = committed.physical_deadline(
            now_ms=facts.now * 1000.0, revision=intent.revision)
        # The preliminary world was measured BEFORE the native queue was
        # armed. During an authorized frozen canvas its hypothetical
        # future destination shrinks as real time advances, even though the
        # exact musical deadline does not move. Comparing the later world
        # coordinate against the earlier feasibility coordinate was
        # therefore invalid and rejected every genuinely correct native
        # Listen/Start admission. Physical arrival time, source revision,
        # queue generation and the native bound segment are the checks.
        if (abs(arrived_ms-receipt.deadline_ms) > 5.0
                or committed.queue_generation < receipt.queue_generation):
            raise ValueError("Physical score arm does not match reserved downbeat")
        from dataclasses import replace
        receipt = replace(
            receipt, world_origin=committed.world_origin,
            queue_generation=committed.queue_generation)
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
                "abandoned": self.intent is None,
                "next_attempt": self.intent.attempt if self.intent else None}

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
            elif facts.now - self.intent.requested_at > MAX_ADMISSION_WAIT_SECONDS:
                # Includes silent physical preflight failures and unavailable
                # engraving. A dead/admitting UI is not a valid steady state.
                intent = self.intent
                self._terminal_automatic_source = (
                    intent.fingerprint, intent.stage_key, intent.revision,
                    intent.hand, intent.end_beat, intent.bpm,
                    intent.mode, round(intent.from_beat, 7))
                self.intent = None
                self.receipt = None
                self.state = PlaybackState.FAILED
                self.failure = "The score could not be prepared for playback; retry the lesson"
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
            # Read-only recovery from a lost playback.reserve response.
            # Do not issue a second admission offer or infer one from state.
            "reservation": self._receipt_response(receipt) if receipt else None,
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
