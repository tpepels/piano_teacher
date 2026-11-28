"""Only authority for graphical playback admission and take authorization.

The embedded desktop app requires a physical score-admission receipt for every
timed start (including MIDI shortcuts, automatic continuation, Listen and
resume). Headless engines explicitly use the independent no-presentation
adapter; they do not pretend a score was drawn.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from .playback_facts import PlaybackRuntimeFacts
from enum import Enum
import math

from .musical_scheduler import SCHEDULER
from .playback_transitions import CountInPlan, PlaybackTransition


# A requested take waits at most this long (e.g. while paused) before the
# session reports that it could not start.
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


class PlaybackCoordinator:
    """The sole gate between a chosen exposure and executable musical time.

    No callback waits for the GUI. The engine publishes an intent; Godot
    prepares/arms immutable ink and performs reserve -> present through the
    existing in-process worker. Presentation is acknowledged before grading
    begins. The intent remains retryable when a reservation expires.
    """

    def __init__(self):
        self.state = PlaybackState.IDLE
        self.generation = 0
        self.sequence = 0
        self.intent: PlaybackIntent | None = None
        self.receipt: ScoreReceipt | None = None
        # The single retained suspended offer belongs to the admission owner.
        self._suspended: tuple[PlaybackIntent, int] | None = None
        self.active_take_id = ""
        self.active_segment_id = ""
        self.active_deadline_ms = 0.0
        self.active_segment: dict = {}
        self.require_presentation = False
        self.presented_segment_id = ""
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

    def invalidate(self, reason: str) -> None:
        # New, explicitly selected exposure/score revision permits a fresh
        # automatic Listen/Tempo admission, not a new attempt on old ink.
        self._terminal_automatic_source = None
        self.generation += 1
        self.intent = None
        self.receipt = None
        self._suspended = None
        self.state = PlaybackState.IDLE
        self._clear_active_segment()
        # A cancelled or replaced exposure is not a failure.
        self.failure = ""

    def _clear_active_segment(self) -> None:
        self.active_take_id = ""
        self.active_segment_id = ""
        self.active_deadline_ms = 0.0
        self.active_segment = {}
        self.presented_segment_id = ""

    @property
    def presentation_confirmed(self) -> bool:
        return (not self.require_presentation or
                bool(self.active_segment_id and
                     self.presented_segment_id == self.active_segment_id))

    def confirm_presentation(self, segment_id: str, *, now: float) -> bool:
        """Accept the exact bound segment before its authoritative downbeat."""
        if (not segment_id or segment_id != self.active_segment_id
                or self.state == PlaybackState.FAILED):
            return False
        if self.presented_segment_id == segment_id:
            return True
        if now * 1000.0 >= self.active_deadline_ms:
            return False
        self.presented_segment_id = segment_id
        return True

    def _fail_terminally(self, intent, message: str) -> None:
        """No further admission attempt for this exact automatic source."""
        self._terminal_automatic_source = (
            intent.fingerprint, intent.stage_key, intent.revision,
            intent.hand, intent.end_beat, intent.bpm,
            intent.mode, round(intent.from_beat, 7))
        self.intent = None
        self.receipt = None
        self.state = PlaybackState.FAILED
        self.failure = message

    def cancel_pending(self, reason: str) -> None:
        """Cancel only the unpresented successor, preserving an older take."""
        if self.intent is None:
            return
        self.generation += 1
        self.intent = None
        self.receipt = None
        self.failure = ""
        self.state = (PlaybackState.PAUSED if self.active_take_id
                      else PlaybackState.IDLE)

    def suspend_pending(self, facts: PlaybackRuntimeFacts) -> bool:
        """Cancel unarmed ink while retaining only its source-bound Resume offer."""
        intent = self.intent
        if intent is None:
            return False
        self._suspended = ((intent, facts.transport_id)
                           if not facts.running else None)
        self.cancel_pending("paused_before_admission")
        return True

    def take_suspended(self, facts: PlaybackRuntimeFacts) -> PlaybackIntent | None:
        """Consume a paused admission only under the same transport and source."""
        stored = self._suspended
        self._suspended = None
        if stored is None:
            return None
        intent, transport_id = stored
        source = facts.source
        if (facts.running or source is None
                or transport_id != facts.transport_id
                or source.fingerprint != intent.fingerprint
                or source.stage_key != intent.stage_key
                or source.revision != intent.revision
                or source.hand != intent.hand
                or abs(source.bpm-intent.bpm) > 1e-7
                or abs(source.end_beat-intent.end_beat) > 1e-7
                or tuple(source.tempo_segments) != intent.tempo_segments):
            # Do not silently drop into the generic resting Resume path.
            # A canceled pending score is an exact source-bound operation,
            # and stale course/source changes require explicit new Start.
            raise ValueError("Suspended playback source changed before Resume")
        return intent

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
                from_beat: float, count_in_beats: float | None = None,
                transition: PlaybackTransition | None = None) -> PlaybackIntent:
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
        if action in ("listen", "score_ready", "auto") and self._running_matches(
                facts, mode=mode, from_beat=from_beat):
            # A repeated readiness callback confirms the take already
            # running on the timeline; it never starts a second one.
            return None
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
        if action in ("start", "restart", "resume"):
            # Clear the terminal latch ONLY after all source, transition,
            # meter and countdown inputs have been validated. A malformed
            # manual request must not unlock another automatic retry.
            self._terminal_automatic_source = None
        self._suspended = None
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
            requested_at=now,
            transition=transition)
        self.receipt = None
        self.state = PlaybackState.AWAITING_ADMISSION
        self.failure = ""
        return self.intent

    def _running_matches(self, facts: PlaybackRuntimeFacts, *, mode: str,
                         from_beat: float) -> bool:
        active, source = self.active_segment, facts.source
        installed = active.get("source", {})
        return (facts.running and bool(self.active_take_id) and source is not None
                and active.get("mode") == mode
                and installed.get("fingerprint") == source.fingerprint
                and installed.get("stage_key") == source.stage_key
                and installed.get("revision") == source.revision
                and installed.get("hand") == source.hand
                and abs(float(installed.get("from_beat", -1.0)) - float(from_beat)) < 1e-7)


    def authorize(self, facts: PlaybackRuntimeFacts, *, deadline: float,
                  world_origin: float, segment_id: str, commit: Callable,
                  capture: Callable[[], PlaybackRuntimeFacts],
                  abort: Callable[[str], None]) -> dict:
        """Start the pending intent at the downbeat the musical timeline
        placed it on. Godot draws it from the timeline; nothing is negotiated."""
        intent = self.intent
        if intent is None or not self._valid_source(facts, intent):
            raise ValueError("Stale or cancelled playback intent")
        receipt = ScoreReceipt(
            intent_id=intent.intent_id, attempt=intent.attempt,
            take_id=intent.take_id, fingerprint=intent.fingerprint,
            stage_key=intent.stage_key, revision=intent.revision,
            hand=intent.hand, source_from_beat=intent.from_beat,
            source_end_beat=intent.end_beat,
            segment_id=segment_id,
            deadline_ms=float(deadline)*1000.0, world_origin=float(world_origin))
        self.receipt = receipt
        return self._commit(intent, receipt, commit=commit, capture=capture,
                            abort=abort)

    def intent_matches(self, facts: PlaybackRuntimeFacts) -> bool:
        return self.intent is not None and self._valid_source(facts, self.intent)

    def segment_id_for(self, intent: PlaybackIntent) -> str:
        return f"{intent.intent_id}:segment:{intent.attempt}"

    def _commit(self, intent, receipt, *, commit, capture, abort) -> dict:
        attempt, segment_id = receipt.attempt, receipt.segment_id
        intent_id = receipt.intent_id
        # No graded/audio transport mutation happened before this point.
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
                self._clear_active_segment()
                self.failure = "The admitted score did not match the musical transport"
                self.state = PlaybackState.FAILED
            raise
        self.active_take_id = receipt.take_id
        self.active_segment_id = receipt.segment_id
        self.presented_segment_id = ""
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
            "graded": intent.mode in ("practice", "perform"),
            "bpm": intent.bpm,
            "count_in_beats": intent.count_in_beats,
            "count_in_meter": list(intent.count_in_meter),
            "count_in_plan": intent.count_in.snapshot(),
            "tempo_segments":[{"start_beat":start,"end_beat":end,"bpm":rate}
                for start,end,rate in intent.tempo_segments],
            "deadline_ms": receipt.deadline_ms,
            "world_origin": receipt.world_origin,
            "transport_id": post.transport_id,
            # Resume may admit a future source beat while retaining the
            # original graded transport origin and frozen musical clock.
            "transport_origin_beat": post.play_from_beat,
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
        return result

    def fail(self, *, take_id: str, segment_id: str, reason: str,
             notify_failure: Callable[[str], None]) -> None:
        if self.active_take_id != take_id or self.active_segment_id != segment_id:
            raise ValueError("Stale playback failure")
        # Revoke authorization before storage/device cleanup. If that
        # cleanup raises, an old graded take must not appear authorized.
        message = "The score stopped displaying correctly"
        self.state = PlaybackState.FAILED
        self.failure = message
        try:
            notify_failure(reason)
        finally:
            self.state = PlaybackState.FAILED
            self.failure = message

    def clear_failure(self) -> None:
        """The failed take is being placed again; nothing is failed now."""
        self.state = PlaybackState.IDLE
        self.failure = ""
        self._clear_active_segment()

    def advance(self, facts: PlaybackRuntimeFacts) -> None:
        if self.state == PlaybackState.FAILED:
            return
        if self.intent is not None:
            if not self._valid_source(facts, self.intent):
                self.invalidate("Source changed before notation admission")
            elif facts.paused:
                # A take requested at a Pause starts on Resume; waiting
                # paused is normal and never times out.
                return
            elif facts.now - self.intent.requested_at > MAX_ADMISSION_WAIT_SECONDS:
                # Includes silent physical preflight failures and unavailable
                # engraving. A dead/admitting UI is not a valid steady state.
                self._fail_terminally(
                    self.intent,
                    "The score could not be prepared for playback; retry the lesson")
            return
        # Live play/pause/count-in/completion are derived at read time from
        # PlaybackSession and its musical timeline. This protocol owner
        # only mutates physical admission, terminal failure and receipts.

    def observed_state(self, facts: PlaybackRuntimeFacts) -> PlaybackState:
        """Read the live take state without an independently ticking phase."""
        if (self.state in (PlaybackState.FAILED, PlaybackState.IDLE)
                or self.intent is not None or not self.active_take_id):
            return self.state
        if facts.running:
            # An already authorized segment may keep painting retained ink
            # while a successor is prepared. It must never authorize the
            # new source's grading, motion or audio under the old segment.
            active = self.active_segment
            installed = active.get("source", {})
            source = facts.source
            if (source is None
                    or facts.transport_id != active.get("transport_id")
                    or facts.mode != active.get("mode")
                    or source.fingerprint != installed.get("fingerprint")
                    or source.stage_key != installed.get("stage_key")
                    or source.revision != installed.get("revision")
                    or source.hand != installed.get("hand")
                    or abs(source.end_beat - installed.get("end_beat", -1)) > 1e-7
                    or abs(source.bpm - active.get("bpm", -1)) > 1e-7
                    or tuple(source.tempo_segments) != tuple(
                        (x["start_beat"], x["end_beat"], x["bpm"])
                        for x in active.get("tempo_segments", ()))):
                return PlaybackState.FAILED
            if facts.paused:
                return PlaybackState.PAUSED
            activation = max(facts.run_at, facts.resume_grading_after)
            return (PlaybackState.COUNT_IN if facts.now < activation
                    else PlaybackState.PLAYING)
        return (PlaybackState.SETTLING if facts.pending_result
                else PlaybackState.COMPLETE)

    def status(self, facts: PlaybackRuntimeFacts) -> dict:
        """Read-only transaction reconciliation, including lost responses.

        The worker can complete an authorization after its Godot request
        times out. A client must query this state before rolling back ink.
        """
        intent = self.intent
        observed = self.observed_state(facts)
        return {
            "state": observed.value,
            "generation": self.generation,
            "intents_issued": self.sequence,
            "intent_id": intent.intent_id if intent else "",
            "attempt": intent.attempt if intent else -1,
            "active_segment_id": self.active_segment_id,
            "active_take_id": self.active_take_id,
            "active_deadline_ms": self.active_deadline_ms,
            # The native recovery reader must verify the original source
            # and tempo, not authorize from the opaque segment ID alone.
            "active": dict(self.active_segment) if self.active_segment else None,
        }

    def snapshot(self, facts: PlaybackRuntimeFacts) -> tuple[dict | None, dict]:
        observed = self.observed_state(facts)
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
            "status": observed.value,
        }
        timeline = {"state": observed.value, "take_id": self.active_take_id,
                    "segment_id": self.active_segment_id,
                    "deadline_ms": self.active_deadline_ms,
                    "current": dict(self.active_segment) if self.active_segment else None,
                    "failure": self.failure,
                    "presentation_confirmed": self.presentation_confirmed}
        return request, timeline
