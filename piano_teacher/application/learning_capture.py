"""Sealed learning evidence for the existing locked application transitions.

This owner receives explicit source/timing facts. It has no engine access and
does not match notes, schedule music, or award progress. MIDI capture stays in
memory; callers persist at the existing transition/savepoint boundaries.
"""
from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import uuid

from ..practice import Recorder
from ..sqlite_transaction import sqlite_atomic
from ..clock import Clock, monotonic


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier() -> str:
    return str(uuid.uuid4())


class LearningCapture:
    def __init__(self, ledger, *, clock: Clock = monotonic):
        self._clock = clock
        self.ledger = ledger
        ledger.recover_open_sessions()
        self.run_id = identifier()
        self.session_id = identifier()
        self.origin = self._clock()
        ledger.start_session(self.session_id, self.run_id, utc_now(),
                             str(datetime.now().astimezone().tzinfo))
        self.attempt_id: str | None = None
        self.context: dict | None = None
        self.sealed: dict | None = None
        self.decisions: list[tuple[str, dict]] = []
        self.waiting_decision: str | None = None
        self.parent_decision: str | None = None
        self.episode: dict | None = None
        self.verification_episode: dict | None = None
        self.guided = Recorder()
        self.phase = "idle"
        self.phase_at = self.origin
        self.intervals: list[dict] = []
        self.closed = False
        self.assistance_used = False
        self.guidance_state = None

    @contextmanager
    def atomic(self):
        """Restore sealed IDs and episode/phase RAM if the shared savepoint fails."""
        before = deepcopy({k: v for k, v in vars(self).items() if k != "ledger"})
        try:
            with sqlite_atomic(self.ledger.db):
                yield
        except BaseException:
            for key, value in before.items():
                setattr(self, key, value)
            raise

    def phase_changed(self, phase: str, now: float) -> None:
        if phase == self.phase:
            return
        now = max(self.origin, self.phase_at, now)
        self.intervals.append({"phase": self.phase,
                               "start": self.phase_at-self.origin,
                               "end": max(self.phase_at, now)-self.origin})
        self.phase, self.phase_at = phase, now

    def event(self, kind: str, data: dict, *, key: str | None = None) -> str:
        return self.ledger.record_event(
            self.session_id, kind,
            {**data, "run_id": self.run_id,
             "monotonic_offset": self._clock()-self.origin,
             "utc": utc_now()}, attempt_id=self.attempt_id,
            event_id=key)

    def begin(self, context: dict) -> None:
        if self.attempt_id is not None:
            raise RuntimeError("Seal the previous learning exposure before starting another")
        if self.episode and any(self.episode[key] != context[key] for key in
                                ("fingerprint", "stage_key", "hand", "target_bpm")):
            with self.atomic():
                self.censor("exposure_context_changed")
        self.attempt_id = identifier()
        self.parent_decision = self.waiting_decision
        self.waiting_decision = None
        self.context = deepcopy({**context, "run_id": self.run_id,
                                 "started_utc": utc_now(),
                                 "monotonic_start": self._clock()-self.origin,
                                 "parent_decision_id": self.parent_decision})
        self.verification_episode = (deepcopy(self.episode) if self.episode and
            context["scope"] == "full" and
            context["performed_bpm"] == self.episode["target_bpm"] and
            context["stage_key"] == self.episode["stage_key"] and
            not context.get("assistance") else None)
        try:
            self.ledger.start_attempt(self.attempt_id, self.session_id, self.context)
        except Exception:
            self.waiting_decision = self.parent_decision
            self.attempt_id = self.context = self.parent_decision = None
            raise
        self.guided = Recorder()
        self.assistance_used = bool(context.get("assistance"))
        self.sealed = None
        self.decisions = []
        self.guidance_state = None

    def observe_guidance(self, snapshot: dict) -> None:
        if self.attempt_id is None:
            return
        facts = {key: snapshot.get(key) for key in
                 ("phase", "target_index", "target_count", "assisted_count", "hint_visible", "hint_reason")}
        facts["expected_source_ids"] = [note.get("source_id") for note in snapshot.get("expected_notes", [])]
        if facts != self.guidance_state:
            with self.atomic():
                self.event("guidance_state", {**facts, "coverage": "worker_transition_samples"})
                self.checkpoint(self.guided.presses, boundary=snapshot.get("target_index", 0))
            self.guidance_state = facts

    def checkpoint(self, played, *, boundary: float) -> None:
        if self.attempt_id is not None and self.sealed is None:
            with self.atomic():
                self.ledger.checkpoint(self.attempt_id, {
                    "boundary": boundary,
                    "boundary_unit": "target_index" if self.context["scope"] == "guided" else "source_beat",
                    "monotonic_offset": self._clock()-self.origin,
                    "played": [asdict(n) for n in played], "coverage": "checkpointed_prefix"})
                self.flush_intervals(self._clock(), keep_phase=True)

    def seal(self, played, *, state: str, reason: str, result=None,
             eligible: bool = False, extra: dict | None = None) -> None:
        if self.attempt_id is None or self.sealed is not None:
            return
        assessment = None
        observations = []
        if result is not None and result.notes:
            assessment = {
                "grader_version": "nearest-onset-v1", "rule_version": "accepted-full-target-v1",
                "bpm": self.context["performed_bpm"],
                "statuses": [n.status for n in result.notes],
                "extra_notes": result.extra_notes, "note_count": len(result.notes),
                "onset_count": result.total_attacks, "warning_onsets": result.yellow_attacks,
                "clean": result.clean, "passed": result.passed,
                "mastery_eligible": eligible,
                "eligibility_reason": "full_timed_practice" if eligible else reason,
                "unmatched_played": [asdict(n) for n in result.unmatched_played]}
            for entry in result.notes:
                observations.append({
                    "source_id": entry.note.source_id,
                    "onset_group_id": f"{self.context['stage_key']}:{entry.note.start:.6f}",
                    "expected_pitch": entry.note.pitch, "authored_hand": entry.note.hand,
                    "source_beat": entry.note.start,
                    "source_measure": bisect_right(self.context["bar_boundaries"], entry.note.start),
                    "omitted": entry.status == "missed",
                    "expected_duration_truncated": entry.note.end > (
                        self.context["phrase_start"] + (extra or {}).get("assessed_end_beat", self.context["end_beat"])) + 1e-7,
                    "status": entry.status,
                    **(asdict(entry.observation) if getattr(entry, "observation", None) is not None else
                       {"missingness": "grader_detail_unavailable"})})
        self.sealed = {
            "state": state, "reason": reason, "ended_utc": utc_now(),
            "monotonic_end": self._clock()-self.origin,
            "assessment": assessment, "observations": observations,
            "played": [asdict(n) for n in played],
            "capture_complete": state == "completed",
            "unknown_suffix": False, "assistance_used": self.assistance_used, **(extra or {})}
        if result is not None and not result.notes:
            self.sealed.update({"unscored_reason": "no_source_obligations",
                                "extra_notes": result.extra_notes})

    def decision(self, data: dict) -> str | None:
        if self.attempt_id is None:
            return None
        decision_id = identifier()
        data = deepcopy(data)
        if self._verification_ready():
            self.episode = None
        if self.episode is None:
            self.episode = {"id": identifier(), "fingerprint": self.context["fingerprint"],
                            "stage_key": self.context["stage_key"],
                            "hand": self.context["hand"],
                            "target_bpm": self.context["target_bpm"],
                            "first_decision": decision_id}
        data["episode_id"] = self.episode["id"]
        self.decisions.append((decision_id, data))
        return decision_id

    def persist(self) -> None:
        """Idempotent SQL effects; finish() publishes RAM only after outer commit."""
        if self.attempt_id is None or self.sealed is None:
            return
        self.ledger.settle_attempt(self.attempt_id, self.sealed)
        for decision_id, data in self.decisions:
            self.ledger.add_decision(decision_id, self.session_id, self.attempt_id, data)
        if self.parent_decision is not None:
            assessment = self.sealed.get("assessment") or {}
            trigger = self.ledger.db.execute("""SELECT t.context_json,t.summary_json
                FROM learning_decisions d JOIN learning_attempts t ON t.attempt_id=d.attempt_id
                WHERE d.decision_id=?""", (self.parent_decision,)).fetchone()
            before = ({} if trigger is None else json.loads(trigger[0] or trigger[1]))
            comparability = {
                "source_and_stage": all(before.get(k) == self.context.get(k)
                                        for k in ("fingerprint", "stage_key", "hand")),
                "tempo": before.get("performed_bpm") == self.context["performed_bpm"],
                "scope": all(before.get(k) == self.context.get(k)
                             for k in ("scope", "from_beat", "end_beat")),
                "support": bool(before.get("assistance")) == self.assistance_used}
            self.ledger.record_outcome(
                f"{self.parent_decision}:proximal", self.parent_decision, self.attempt_id,
                {"kind": "proximal", "state": self.sealed["state"],
                 "passed": assessment.get("passed"), "clean": assessment.get("clean"),
                 "scope": self.context["scope"], "bpm": self.context["performed_bpm"],
                 "guided": self.context["scope"] == "guided",
                 "comparability": comparability,
                 "focused_success": bool(assessment.get("passed")) and self.context["scope"] != "full",
                 "causal_comparison": False})
        episode = self.verification_episode
        if self._verification_ready():
            self.ledger.record_outcome(
                f"{episode['id']}:verification", episode["first_decision"], self.attempt_id,
                {"kind": "episode_verification", "episode_id": episode["id"],
                 "state": "censored" if self.assistance_used else self.sealed["state"],
                 "reason": "assistance_used" if self.assistance_used else "original_target_test",
                 "unsupported": not self.assistance_used,
                 "passed": self.sealed["assessment"]["passed"],
                 "clean": self.sealed["assessment"]["clean"],
                 "causal_comparison": False})
        self.flush_intervals(self._clock(), keep_phase=True)

    def _verification_ready(self) -> bool:
        return bool(self.verification_episode and self.sealed and
                    self.sealed["state"] == "completed" and self.sealed.get("assessment"))

    def finish(self) -> None:
        if self.decisions:
            self.waiting_decision = self.decisions[-1][0]
        if (self.episode and self._verification_ready() and
                self.episode["id"] == self.verification_episode["id"]):
            self.episode = None
        self.attempt_id = self.context = self.sealed = self.parent_decision = None
        self.decisions = []
        self.verification_episode = None

    def interrupt(self, reason: str, played=(), *, censor: bool = True, extra=None) -> None:
        # Restart/resume callers can interrupt directly, without an enclosing
        # engine savepoint. Keep the exposure, linked outcomes and capture RAM
        # together until every write (including episode censorship) succeeds.
        with self.atomic():
            if self.attempt_id is not None:
                self.seal(played, state="aborted", reason=reason, extra=extra)
                if self.sealed.get("assessment"):
                    self.sealed["assessment"]["mastery_eligible"] = False
                    self.sealed["assessment"]["eligibility_reason"] = reason
                self.persist()
                self.finish()
            if censor:
                self.censor(reason)

    def censor(self, reason: str) -> None:
        if self.waiting_decision:
            self.ledger.record_outcome(
                f"{self.waiting_decision}:proximal", self.waiting_decision, None,
                {"kind": "proximal", "state": "censored", "reason": reason})
        if self.episode:
            self.ledger.record_outcome(
                f"{self.episode['id']}:verification", self.episode["first_decision"], None,
                {"kind": "episode_verification", "episode_id": self.episode["id"],
                 "state": "censored", "reason": reason})
            self.event("episode_censored", {**self.episode, "reason": reason})
        self.waiting_decision = self.episode = None

    def discard_deleted(self) -> None:
        """Publish an authorized deletion without writing evidence being erased."""
        self.attempt_id = self.context = self.sealed = self.parent_decision = None
        self.decisions = []
        self.waiting_decision = self.episode = self.verification_episode = None
        self.guided = Recorder()
        self.intervals = []
        self.phase, self.phase_at = "idle", self._clock()

    def flush_intervals(self, now: float, *, keep_phase: bool = False) -> None:
        previous_phase = self.phase
        self.phase_changed("idle", now)
        if self.intervals:
            self.event("phase_intervals", {"intervals": self.intervals,
                                           "units": "monotonic_seconds", "coverage": "transition_samples"})
            self.intervals = []
        if keep_phase:
            self.phase, self.phase_at = previous_phase, max(self.origin, self.phase_at, now)

    def close(self, reason: str = "shutdown") -> None:
        if self.closed:
            return
        self.interrupt(reason, self.guided.presses)
        self.flush_intervals(self._clock())
        self.ledger.close_session(self.session_id, reason)
        self.closed = True
