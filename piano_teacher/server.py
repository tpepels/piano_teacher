"""Piano practice engine embedded directly into the Godot process.

Owns the MIDI, grading, lessons, notation and persistent library state.
Communication with Godot uses an in-memory native command queue.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from collections import deque
import logging
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import math

from .learning import LearningPlan
from .teaching_course import steps as teaching_steps, manual_progress
from .teaching_manual import ManualFacts
from .teaching_decisions import (TeachingBinding, TeachingState, TeachingRouteFacts, TeachingEvent,
    source_safe_response)
from .diagnosis_policies import LearnerSnapshot
from .application.attempt_settlement import AttemptSettlement
from .application.session_commands import SessionCommands
from .application.teaching_continuation import TeachingContinuation, ContinuationReadiness, UnpreparedNextStage
from .lesson_timing import lead_in_beats

# Poll/frame latency allowed between announcing a short-rest continuation
# (sampled when it is announced, after the take-end work) and Godot
# admitting it; the ink still opens a full count-in bar ahead.
SHORT_REST_LATENCY_SECONDS = 0.4
from .sqlite_transaction import sqlite_atomic
from .application.score_artifacts import ScoreArtifacts, ScoreSelection
from .application.future_score import FutureScore
from .application.midi_connection import MidiConnection, MidiNotice
from .application.midi_key_shortcuts import MidiKeyShortcuts
from .application.midi_ingress import MidiIngress, MidiInputFacts
from .application.listen_session import ListenSelection, ListenSession
from .practice import Recorder
from .importing.pieces import import_piece
from .engraving.engraving import EngravedScore
from .fingering import FingeringService
from .library import ScoreLibrary
from .preprocessing_cache import PreprocessingCache
from .library_health import LibraryHealth
from .warmups import is_warmup
from .application.mistake_responses import resolve_mistake_policy, mistake_policy_facts
from .music import Phrase
from .measure_grid import phrase_grid
from .course_navigation import choose_source_opening
from .state_projection import (
    PhaseSnapshot, SessionSnapshot, project_phase, project_session_state,
)
from .assessment_service import AssessmentService
from .application.practice_assessment import PracticeAssessmentPolicies
from .application.control_dispatch import ControlDispatcher
from .application.score_ack import ScoreAckState, choose_score_ack_action
from .application.transport_commands import (
    require_pausable, resume_timeline,
    scheduled_offscreen_start, planned_retry_reverse_seconds,
)
from .application.stage_change import prepare_stage_change
from .application.practice_transitions import TransitionContext, decide_transition
from .application.attempt_progression import AttemptProgression, AttemptTick, repeat_deadline, SETTLEMENT_SECONDS
from .application.assessment_settlement import assess_completed_take
from .application.guided_session import GuidedSession, GuidedFragment
from .application.tempo_map_cache import TempoMapCache
from .application.session_snapshot_builder import (
    SnapshotValues, SnapshotReadPorts, capture as capture_session_snapshot,
)
from .completion_route import completion_route
from .visual_transport import VisualTransport
from .midi_calibration import MidiTapCalibration
from . import state_contract
from .clock import Clock, monotonic
from .feedback_events import FeedbackEventLog
from .live_assessment_publisher import LiveAssessmentPublisher
from .runtime_timings import RuntimeTimings
from .live_input_view import LiveInputView
from .learner_state import guided_units
from .progress_repository import ProgressRepository
from .application.learner_progress import LearnerProgress
from .lesson_settings import SETTINGS
from .teaching import TeachingConfig
from .application.learning_capture import LearningCapture, identifier

from .practice_history import PracticePolicyService
from .fukuda_mistake_store import FukudaMistakeStore
from .remediation import RemedialAssignment, plan_timed_remedial_review


class PracticeEngine:
    # Existing public attributes delegate to one actual transport-state owner.

    @property
    def teaching(self):
        return self.guided_session.controller

    @teaching.setter
    def teaching(self, controller):
        if controller is None:
            self.guided_session.clear_selection()
        else:
            self.guided_session.controller = controller

    @property
    def persistent_hints(self) -> bool:
        return self.guided_session.persistent_hints

    @persistent_hints.setter
    def persistent_hints(self, enabled: bool) -> None:
        self.guided_session.persistent_hints = bool(enabled)

    @property
    def _guided_prepared(self) -> bool:
        return self.guided_session.prepared

    @_guided_prepared.setter
    def _guided_prepared(self, prepared: bool) -> None:
        self.guided_session.prepared = prepared

    @property
    def _guided_return(self):
        return self.guided_session.return_context

    @_guided_return.setter
    def _guided_return(self, context):
        self.guided_session.return_context = context

    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True,
                 feedback_events: FeedbackEventLog | None = None,
                 clock: Clock | None = None):
        # The one monotonic clock of this session; collaborators receive it.
        self.now: Clock = clock if clock is not None else monotonic
        self.lock = threading.RLock()
        # Whole-source inference must never block MIDI or state polling.
        # Serialize source loads and durable corrections separately instead.
        self._fingering_lock = threading.Lock()
        self._piece_generation = 0
        self.guided_session = GuidedSession(clock=self.now)
        self.plan: LearningPlan | None = None
        self.score = None
        self.source = None
        self.is_builtin_warmup = False
        self.fingerprint = ""
        self.recorder: Recorder | None = None
        self.visual_transport = VisualTransport(
            _visual_rewind_seconds=SETTINGS.feedback_seconds)
        self.tempo_map_cache = TempoMapCache()
        self.attempt_progression = AttemptProgression()
        self.open_from_beat = 0.0  # Explicit opening measure; never an inferred clock
        self.next_boundary_beat = 0.0
        self.feedback_seconds = SETTINGS.feedback_seconds
        self.midi_calibration = MidiTapCalibration()
        # The single acknowledged note-feedback channel to the score: provisional
        # attack/release events and authoritative per-note assessments.
        self.feedback_events = (feedback_events if feedback_events is not None
                                else FeedbackEventLog())
        self.live_assessment = LiveAssessmentPublisher(self.feedback_events)
        self.runtime_timings = RuntimeTimings()
        self.recovery_notice: dict | None = None
        self.pause_context: str | None = None
        # Musical clock resumes at its previous beat after a reading lead-in.
        # No MIDI attack during that lead-in can alter a graded attempt.
        # Graded musical position (seconds since run_at) at the Pause moment.
        # The graded timeline stands still there until grading resumes after
        # Resume's lead; see _musical_seconds (R1 F2).
        self._pause_floor: float | None = None
        self._deferred_score_ack: int | None = None
        self.next_action = "Open a MIDI file."
        self.retry_range: dict | None = None
        # Persistent trouble means two boundary failures in consecutive takes
        # at the same stage and source two-bar chunk. Only a clean full take
        # or explicit stage navigation resets the history.
        self._trouble_key: tuple | None = None
        self._trouble_count = 0
        self._guided_recovery_pending = False
        self._guided_return: tuple[str, float] | None = None
        self.performance_summary: dict | None = None
        self.review_stage_identity: str | None = None
        self.review_end_beat: float | None = None
        # Automatic remedial sections are timed source reviews, never an
        # input-blocking lesson. A partial review never awards mastery.
        self._automatic_remedial_review = False
        self.review_session_complete = False
        self.course_guided = False
        self._guided_prepared = False
        self.transport_id = 0
        self.mode = "practice"
        self.teaching = None
        self.guided_range: tuple[float, float] | None = None
        self.persistent_hints = False
        self.running = False
        self.auto = False
        self.preview_only = False
        self.count_in_beats = 0
        self.count_in_bar_beats = 4.0
        self.count_in_meter = [4, 4]
        self.feedback = "Open a MIDI file"
        self.score_revision = 0
        self.awaiting_score_revision: int | None = None
        self.pending_result = None
        self._pending_assessed_bpm: float | None = None
        self.feedback_marks: list[dict] = []
        self.feedback_unmapped = 0
        self.midi = MidiConnection(enabled=enable_midi, clock=self.now)
        self.live_input = LiveInputView()
        self.assessment = AssessmentService()
        self.assessment_policies = PracticeAssessmentPolicies.defaults(self.assessment)
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        self.midi_key_shortcuts = MidiKeyShortcuts(self.library.settings["midi_key_ranges"])
        self.library_health = LibraryHealth(self.library)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir
        self.listen = ListenSession(data_dir / "demo-audio", lock=self.lock)
        self.fingering = FingeringService(data_dir / "fingering")
        self.preprocessing = PreprocessingCache(data_dir / "preprocessed")
        self.score_artifacts = ScoreArtifacts(self.preprocessing)
        future_score = FutureScore(data_dir / "preprocessed", clock=self.now)
        self.teaching_continuation = TeachingContinuation(future_score,self.visual_transport)
        self._future_stage_lead_beats = 0.0
        self._continuous_horizon_beats = 0.0
        # The untimed guided engine owns repeat presentation epochs; no
        # Godot-side guess about missed notes or lesson progression.
        self._guided_stream_deadline: float | None = None
        # Explicit backend-selected next take. Renderer may only enqueue this
        # source identity at this exact monotonic graded deadline.
        self._queue_scheduled_start = None
        # Godot's empty-strip geometry (clear, header beats); None = no
        # renderer has reported it, keep the offscreen reading horizon.
        self._short_rest: tuple[float, float] | None = None
        # (seconds, bpm) of the last finished take's end: the written rest
        # bar that follows it is printed from there at that tempo.
        self._rest_take_end: tuple[float, float] | None = None
        self._future_stage_clear_beats: float | None = None
        self._future_stage_short_rest: tuple[float, float] | None = None
        self._tempo_key = None
        self._tempo_epoch: float | None = None
        self._prepared_stage_published = False
        # Global musical origin of a delayed, pre-engraved next stage.
        # Pin the renderer-acknowledged source assets through settlement.
        # Final native renderer failures are tied to one exact future step.
        self._native_preload_failure: tuple[str, int, str, int, str] | None = None
        self.progress = ProgressRepository(data_dir / "progress.db")
        # Keep the public db handle for LearnerStateStore and existing clients.
        self.db = self.progress.db
        self.measurement = LearningCapture(self.progress.ledger, clock=self.now)
        self.progress.ledger.prune(days=self.library.settings["evidence_retention_days"],
                                   budget_mib=self.library.settings["evidence_budget_mib"])
        self._action_reason = "transition"
        self._pending_rolling = None
        self._settlement_failed = False
        self.fukuda_mistakes = FukudaMistakeStore(self.db)
        self.learner_store = self.progress.learner_store
        self.learner_progress = LearnerProgress(self.learner_store)
        self.practice_policy = PracticePolicyService(
            self.progress.ledger,
            diagnosis=self.library.settings["diagnosis_strategy"],
            learner=self.library.settings["learner_strategy"])
        self._remediation_pending: RemedialAssignment | None = None
        self._remediation_active: RemedialAssignment | None = None
        self.midi_ingress = MidiIngress(self.midi,self.midi_calibration,self.midi_key_shortcuts,
            self.live_input,self.measurement,self.feedback_events)
        self.session_commands = SessionCommands()
        self.attempt_settlement = AttemptSettlement(self.progress, self.measurement,
            self.fukuda_mistakes, self.learner_progress)

    @property
    def _future_stage_ready(self):
        return self.teaching_continuation.acknowledged

    @_future_stage_ready.setter
    def _future_stage_ready(self, identity):
        self.teaching_continuation.acknowledged = identity

    @property
    def future_score(self):
        return self.teaching_continuation.future_score

    @future_score.setter
    def future_score(self, owner):
        self.teaching_continuation.future_score = owner

    def _midi_lost(self, reason: str = "device_disconnected") -> None:
        """Cancel session state after detachment and before closing the input."""
        if self.plan is not None:
            self._prepare_teaching("interrupted", action=reason, store=False)
        with self.midi.disconnected(reason) as notice:
            self.midi_key_shortcuts.cancel_capture()
            self.live_input.clear_device()
            self._stop(reason=reason)
            if self.teaching is not None:
                self.teaching.set_connected(False, now=self.now())
        self.feedback = notice.feedback
        self.next_action = notice.next_action

    def _present_midi_notice(self, notice: MidiNotice | None) -> None:
        if notice is None:
            return
        if notice.connected is not None and self.teaching is not None:
            self.teaching.set_connected(notice.connected, now=(notice.sampled_at
                if notice.sampled_at is not None else self.now()))
        self.feedback = notice.feedback
        self.next_action = notice.next_action

    def ports(self) -> list[str]:
        if not self.midi.enabled:
            return []
        with self.lock:
            scan = self.midi.scan()
            if scan.lost:
                self._midi_lost()
            if scan.error is not None:
                self.feedback = scan.feedback
                raise RuntimeError(self.feedback) from scan.error
            self._present_midi_notice(self.midi.restore_preferred(
                scan.names, self.library.settings.get("midi_device", ""), callback=self._receive))
            return list(scan.names)

    def connect(self, name: str):
        with self.lock:
            try:
                with self.midi.selecting(name, callback=self._receive) as selected:
                    self.midi_key_shortcuts.cancel_capture()
                    self.live_input.clear_device()
                    self._stop(reason="device_changed")
            except RuntimeError as exc:
                self.feedback = str(exc)
                raise
            self._present_midi_notice(selected.notice)
            self.set_preferences(midi_device=name)

    def hardware_diagnostics(self) -> dict:
        with self.lock:
            return self.midi.diagnostics_snapshot()

    def hardware_diagnostics_action(self, action: str) -> dict:
        with self.lock:
            return self.midi.diagnostics_action(action, running=self.running)

    def library_listing(self) -> dict:
        with self.lock:
            return self.library.scan()

    def library_health_status(self) -> dict:
        return self.library_health.snapshot()

    def start_library_health(self) -> dict:
        return self.library_health.start()

    def midi_calibration_action(self, action: str) -> None:
        with self.lock:
            if action == "calibration_start":
                if not self.midi.connected:
                    raise ValueError("Connect the MIDI keyboard before calibrating")
                self._stop()
                self.midi_calibration.start(self.now())
                self.feedback = "Tap one key per click through five continuous rounds"
            elif action == "calibration_cancel":
                self.midi_calibration.cancel()
            elif action == "calibration_apply":
                result = self.midi_calibration.snapshot(self.now())["result"]
                if not result or not result.get("reliable"):
                    raise ValueError("Finish a consistent calibration before applying it")
                self.set_preferences(midi_offset_ms=max(0, min(250, result["estimate_ms"])))
            elif action == "calibration_reset":
                self.midi_calibration.cancel()
                self.midi_calibration.result = None
                self.set_preferences(midi_offset_ms=0)
            else:
                raise ValueError("Unsupported calibration command")

    def preferences(self) -> dict:
        with self.lock:
            return self.library.public_settings()

    def _learning_context(self, *, scope: str, start: float, end: float,
                          run_at: float | None = None) -> dict:
        p = self.plan
        phrase = p.active_phrase
        tempo = self._active_tempo_map()
        segments = (list(tempo.as_segments()) if tempo is not None else
                    [{"start_beat": 0.0, "end_beat": phrase.end-phrase.start,
                      "bpm": p.bpm}])
        rule = {"schema_version": 1, "grader": "nearest-onset-v1",
                "mastery": "accepted-full-target-v1", "lesson_settings": asdict(SETTINGS),
                "onset_formula": "max(grading_onset_tolerance_seconds,min(0.30,0.20*local_spb))",
                "hold_formula": "max(grading_duration_floor_seconds,duration*max(grading_duration_tolerance_fraction,min(0.75,grading_duration_tolerance_fraction+0.28*max(0,local_spb-0.5))))",
                "importer": "midi-source-v1", "generator": p.lesson_generator.name,
                "generator_version": p.route_version,
                "retry_version": resolve_mistake_policy(self.library.settings["mistake_response_strategy"]).version,
                "guided_config": {**asdict(self.teaching.config if self.teaching else TeachingConfig()),
                                  "persistent_hints": self.persistent_hints},
                "retry": mistake_policy_facts(resolve_mistake_policy(self.library.settings["mistake_response_strategy"]))}
        rule_id = self.progress.ledger.store_rules(rule)
        return {"fingerprint": self.fingerprint, "source_sha256": self.fingerprint,
                "stage_key": p.identity, "hand": p.hand, "scope": scope,
                "variant": p.active_variant.level, "generator": p.lesson_generator.name,
                "generator_version": p.route_version, "rule_id": rule_id,
                "source_note_ids": [n.source_id for n in phrase.notes],
                "variant_source_indices": list(p.active_variant.source_indices),
                "expected_notes": [asdict(n) for n in phrase.notes],
                "bar_boundaries": list(p.piece.bar_boundaries),
                "time_signatures": [list(signature) for signature in p.piece.time_signatures],
                "phrase_start": phrase.start, "phrase_end": phrase.end,
                "from_beat": start, "end_beat": end, "target_bpm": p.target_bpm,
                "source_bpm": p.piece.bpm,
                "performed_bpm": p.bpm, "tempo_map": segments,
                "tempo_map_hash": hashlib.sha256(json.dumps(segments, sort_keys=True).encode()).hexdigest(),
                "transport_id": self.transport_id, "score_revision": self.score_revision,
                "scheduled_origin": None if run_at is None else run_at-self.measurement.origin,
                "count_in_beats": self.count_in_beats,
                "count_in_meter": list(self.count_in_meter),
                "midi_available": self.midi.connected,
                "device_name": self.midi.device,
                "calibration_ms": self.library.settings["midi_offset_ms"],
                "calibration_result": self.midi_calibration.result,
                "calibration_applied_ms": (0 if scope in ("guided", "preview") else
                                            self.library.settings["midi_offset_ms"]),
                "assistance": self.persistent_hints or scope == "guided"}

    def learning_history_status(self) -> dict:
        with self.lock:
            status = self.progress.ledger.status()
            return {**status, "attempt_count": status["attempts"],
                    "detail_attempt_count": status["attempts"]-status["coverage"]["pruned_detail_attempts"]-status["coverage"]["legacy_bounded_attempts"],
                    "pruned_attempt_count": status["coverage"]["pruned_detail_attempts"],
                    "current_fingerprint": self.fingerprint,
                    "default_path": str(self._data_dir / "exports" / "learning-history.json"),
                    "evidence_retention_days": self.library.settings["evidence_retention_days"],
                    "evidence_budget_mib": self.library.settings["evidence_budget_mib"],
                    "summary": (f"{status['attempts']} recorded takes. "
                                "History stays on this computer. Reset Lesson preserves history.")}

    def learning_statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        """Read measured learning outcomes without advancing the musical clock."""
        from .learning_statistics import learning_statistics
        from .learning_statistics_query import capture_statistics, validate_query
        from contextlib import closing
        import sqlite3
        q = validate_query(query, fingerprint)
        # An independent read-only connection never waits for the engine lock.
        # Close the bounded snapshot before formatting, releasing SQLite's read
        # lock before any expensive dictionary/quantile projection.
        path = self.progress.db_path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(path, uri=True, timeout=.05)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            learner = db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()[0]
            snapshot = capture_statistics(db, learner, q)
            db.rollback()
            report = learning_statistics(None, query=q, snapshot=snapshot)
            # Deletion may commit while formatting. Never publish erased data
            # or a former learner's snapshot after that boundary.
            current = db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()
            ids = snapshot["query"]["attempt_ids"]
            slots = ",".join("?" for _ in ids) or "NULL"
            retained = db.execute(f"SELECT count(*) FROM learning_attempts WHERE attempt_id IN ({slots})", ids).fetchone()[0]
            if current != (learner,) or retained != len(ids):
                raise ValueError("Learning history changed during the report; refresh statistics")
            report["learner_id"] = learner
            return report

    def _retry_context(self, result, *, end_beat=None):
        """Use compatible, retained original grading evidence at retry boundaries."""
        from .application.mistake_responses import (
            AdaptiveAttempt, AdaptiveContext, adaptive_attempt_from_assessment)
        context = self.measurement.context or {}
        phrase = self.plan.active_phrase
        attempts = []
        rows = self.db.execute("""SELECT t.context_json,d.detail_json FROM learning_attempts t
            JOIN learning_attempt_details d USING(attempt_id)
            WHERE t.fingerprint=? AND t.stage_key=? AND t.state IN ('completed','interrupted')
            ORDER BY t.rowid DESC LIMIT 16""", (self.fingerprint, self.plan.identity)).fetchall()
        for encoded, detail_json in reversed(rows):
            if not encoded:
                continue
            previous, detail = json.loads(encoded), json.loads(detail_json)
            if any(previous.get(key) != context.get(key) for key in
                   ("hand", "rule_id", "target_bpm", "calibration_applied_ms")):
                continue
            assessment = detail.get("assessment")
            observations = detail.get("observations", [])
            if not assessment or not observations or previous.get("scope") in ("perform", "preview", "guided"):
                continue
            if any(item.get("missingness") for item in observations):
                continue
            selected = {}
            if previous.get("parent_decision_id"):
                row = self.db.execute("SELECT data_json FROM learning_decisions WHERE decision_id=?",
                                      (previous["parent_decision_id"],)).fetchone()
                if row and row[0]:
                    selected = json.loads(row[0]).get("selected", {})
            attempts.append(AdaptiveAttempt(
                identity=self.plan.identity, start_beat=previous["from_beat"],
                end_beat=detail.get("assessed_end_beat", previous["end_beat"]),
                bpm=previous["performed_bpm"],
                wrong_beats=tuple(n["source_beat"]-phrase.start for n in observations if n["status"] == "wrong"),
                missed_beats=tuple(n["source_beat"]-phrase.start for n in observations if n["status"] == "missed"),
                timing_errors=sum(bool(n.get("timing_error")) for n in observations),
                hold_errors=sum(bool(n.get("hold_error")) for n in observations),
                accepted=assessment["passed"], assisted=bool(detail.get("assistance_used")),
                action=selected.get("action", "repeat"), extra_errors=assessment.get("extra_notes", 0)))
        action = "repeat"
        parent = context.get("parent_decision_id")
        if parent:
            row = self.db.execute("SELECT data_json FROM learning_decisions WHERE decision_id=?", (parent,)).fetchone()
            if row and row[0]:
                action = json.loads(row[0]).get("selected", {}).get("action", "repeat")
        attempts.append(adaptive_attempt_from_assessment(result, identity=self.plan.identity,
            start_beat=self.visual_transport.play_from_beat,
            end_beat=end_beat if end_beat is not None else context.get("end_beat", phrase.end-phrase.start),
            bpm=context.get("performed_bpm", self.plan.bpm), phrase_start=phrase.start,
            assisted=self.measurement.assistance_used, action=action))
        episode = self.measurement.episode
        count, reference = 0, context.get("performed_bpm", self.plan.bpm)
        if episode:
            count = self.db.execute("SELECT count(*) FROM learning_decisions WHERE json_extract(summary_json,'$.episode_id')=?",
                                    (episode["id"],)).fetchone()[0]
            row = self.db.execute("""SELECT t.summary_json FROM learning_decisions d
                JOIN learning_attempts t ON t.attempt_id=d.attempt_id WHERE d.decision_id=?""",
                (episode["first_decision"],)).fetchone()
            if row:
                reference = json.loads(row[0]).get("performed_bpm", reference)
        onsets = {n.start for n in phrase.notes if self.plan.hand == "both" or n.hand == self.plan.hand}
        return AdaptiveContext(self.plan.identity, tuple(attempts), episode_action_count=count,
            original_start_beat=0., original_end_beat=phrase.end-phrase.start,
            source_attacks=len(onsets), attacks_per_beat=len(onsets)/(phrase.end-phrase.start),
            reference_bpm=reference)



    def _apply_policy_response(self, response, *, now: float, deadline: float | None = None,
                               visual_from: float | None = None):
        """Apply registered source-bound decisions through the existing transport."""
        phrase = self.plan.active_phrase
        full_end = phrase.end-phrase.start
        self.open_from_beat = response.restart_beat
        self.review_end_beat = response.end_beat if response.end_beat is not None and response.end_beat < full_end-1e-7 else None
        self.retry_range = ({"start_beat": response.restart_beat, "end_beat": response.end_beat,
                             "response": response.action} if self.review_end_beat is not None else None)
        instruction = {
            "repeat": f"Repeat this passage at {response.bpm} BPM.",
            "isolate": f"Practise the difficult measures at {response.bpm} BPM before reconnecting the passage.",
            "slow": f"Practise this passage more slowly at {response.bpm} BPM.",
            "guided": "Find the notes without timing pressure, then retry without hints.",
            "reintegrate": f"Reconnect the surrounding measures at {response.bpm} BPM before the full passage.",
            "pause": "Take a break or choose another retry strategy, then press Start when ready.",
        }.get(response.action, f"Continue at {response.bpm} BPM.")
        self.next_action = instruction
        if response.action == "pause":
            self.auto = False
            self.visual_transport.cancel_preparation()
            self.visual_transport.next_at = 0.
            self.feedback = "Practice paused after repeated automatic retries"
        elif response.guided:
            self._begin_learn(from_beat=response.restart_beat, recovery=True,
                exposure=self.attempt_settlement.pending.decision.next_exposure)
            self.next_action = instruction
        elif deadline is not None:
            self._continue_at(
                self._continuation_deadline(deadline, response.restart_beat),
                from_beat=response.restart_beat)
            self.next_action = instruction
        else:
            self._schedule_preparation(response.restart_beat, now=now,
                from_visual=self._visual_motion(now)[0] if visual_from is None else visual_from,
                reverse_seconds=self.feedback_seconds)
            self.next_action = instruction

    def export_learning_history(self, path: str, include_detail: bool = False) -> dict:
        if not isinstance(path, str) or not path.strip() or type(include_detail) is not bool:
            raise ValueError("Choose an export file and detail preference")
        with self.lock:
            return self.progress.ledger.export(Path(path).expanduser(), include_detail=include_detail)

    def delete_piece_history(self, fingerprint: str, confirm: bool = False) -> dict:
        with self.lock:
            if confirm is not True or not self.plan or fingerprint != self.fingerprint:
                raise ValueError("Confirm deletion for the currently loaded piece")
            replacement = LearningPlan(self.plan.piece, warmup=self.is_builtin_warmup,
                exercise_strategy=self.plan.exercise_strategy.name,
                fukuda_mistakes=frozenset(), feedback={})
            with self.measurement.atomic():
                self.progress.ledger.delete_piece(fingerprint)
            self.measurement.discard_deleted()
            self._stop(reason="delete_piece_history", persist_evidence=False)
            self.plan = replacement
            self._reset_trouble()
            self.open_from_beat = 0.0
            self.mode = "practice"
            self.teaching = None
            self.guided_range = None
            self.score_artifacts.invalidate()
            self.score_revision += 1
            self.feedback = "Piece history and learning progress deleted"
            self.course_guided = False
            self.persistent_hints = False
            return self.learning_history_status()

    def delete_learner_history(self, confirm: bool = False) -> dict:
        with self.lock:
            if confirm is not True:
                raise ValueError("Confirm deletion of all learning history and progress")
            replacement = (LearningPlan(self.plan.piece, warmup=self.is_builtin_warmup,
                exercise_strategy=self.plan.exercise_strategy.name,
                fukuda_mistakes=frozenset(), feedback={}) if self.plan else None)
            with self.measurement.atomic():
                self.progress.ledger.delete_learner()
            self.measurement.discard_deleted()
            self._stop(reason="delete_learner_history", persist_evidence=False)
            self.measurement = LearningCapture(self.progress.ledger, clock=self.now)
            self.plan = replacement
            self._reset_trouble()
            self.open_from_beat = 0.0
            self.mode = "practice"
            self.teaching = None
            self.guided_range = None
            self.score_artifacts.invalidate()
            self.score_revision += 1
            self.feedback = "All learning history and progress deleted"
            self.course_guided = False
            self.persistent_hints = False
            return self.learning_history_status()

    def close(self) -> None:
        with self.lock:
            if self.measurement.closed:
                return
            self._stop(reason="shutdown")
            self.measurement.close()
            with self.midi.selecting("", callback=self._receive):
                pass
            self.progress.close()

    def set_preferences(self, **changes) -> dict:
        with self.lock:
            # Validate the complete configuration before anything changes.
            # The one selectable exercise strategy never swaps the course.
            proposed = self.library.propose_update(**changes)
            before = self.library.settings["music_dir"]
            intent = identifier()
            self.measurement.event("settings_intent", {
                "intent_id": intent, "before": {key: self.library.settings[key] for key in changes},
                "after": {key: proposed[key] for key in changes}})
            if proposed["midi_offset_ms"] != self.library.settings["midi_offset_ms"]:
                self._stop(reason="calibration_changed")
                self.feedback = "MIDI timing correction changed"
                self.next_action = "Press Play to start a new attempt."
            if proposed["mistake_response_strategy"] != self.library.settings["mistake_response_strategy"]:
                self._stop(reason="policy_changed")
                self.feedback = "Retry strategy changed"
                self.next_action = "Press Play to start a new attempt."
            updated = self.library.update(**changes)
            if "midi_key_ranges" in changes:
                self.midi_key_shortcuts.configure(updated["midi_key_ranges"])
            self.measurement.event("settings_applied", {"intent_id": intent, "changes": changes})
            if {"evidence_retention_days", "evidence_budget_mib"} & changes.keys():
                if self.running and not self.visual_transport.paused:
                    self._pause_current_session()
                self.progress.ledger.prune(days=proposed["evidence_retention_days"],
                                           budget_mib=proposed["evidence_budget_mib"])
            if {"diagnosis_strategy", "learner_strategy"} & changes.keys():
                self.practice_policy = PracticePolicyService(
                    self.progress.ledger,
                    diagnosis=self.library.settings["diagnosis_strategy"],
                    learner=self.library.settings["learner_strategy"])
            if before != self.library.settings["music_dir"]:
                self.library_health.reset()
            return updated

    def _active_tempo_map(self):
        """Reuse an immutable authored tempo map until stage or BPM changes.

        This runs on the 20 ms worker as well as during state snapshots.
        ExerciseStage.tempo_map() may transform every note, so rebuilding it
        for every clock read creates work proportional to the full passage.
        """
        if self.plan is None or self.mode not in ("practice", "listen"):
            return None
        return self.tempo_map_cache.get(self.plan.active_stage, self.plan.bpm)

    def _elapsed_beat(self, elapsed_seconds: float) -> float:
        tempo = self._active_tempo_map()
        if tempo is not None and elapsed_seconds >= 0:
            origin = tempo.seconds_at(self.visual_transport.play_from_beat)
            return tempo.beat_at(origin+elapsed_seconds)-self.visual_transport.play_from_beat
        return elapsed_seconds * self.plan.bpm / 60.0

    def _elapsed_seconds(self, beat: float) -> float:
        tempo = self._active_tempo_map()
        if tempo is not None:
            return tempo.seconds_at(beat)
        return beat * 60.0 / self.plan.bpm

    def exercise_diagnostics(self) -> dict:
        with self.lock:
            if self.plan is None:
                return {"loaded": False,
                        "exercise_strategy": self.library.settings['exercise_strategy']}
            return {"loaded": True, "exercise_strategy": self.plan.exercise_strategy.name,
                    "tempo_segments": (self._active_tempo_map().as_segments()
                                       if self._active_tempo_map() is not None else ()),
                    "stage_key": self.plan.identity,
                    **self.practice_policy.inspect(self.fingerprint, self.plan.identity)}

    def load_library(self, identifier: str) -> None:
        with self.lock:
            path = self.library.resolve(identifier)
        # Preserve the ordinary loader path for imported music and its callers.
        if is_warmup(identifier):
            self.load(str(path), warmup=True)
        else:
            self.load(str(path))  # Parse before recording success.
        with self.lock:
            if is_warmup(identifier):
                # Restore this hand and its clean streak, starting at left
                # when the student has no prior progress on the warm-up.
                self.mode = 'practice'
                self.course_guided = False
                self.feedback = 'Warm-up ready - left, right, then both hands'
                self.next_action = 'Three clean passes unlock the next hand.'
                self._save()
            self.library.mark_opened(identifier)

    def performance_diagnostics(self) -> dict:
        return self.runtime_timings.snapshot()

    def _receive(self, message):
        began = time.perf_counter()
        try:
            self._receive_message(message)
        finally:
            self.runtime_timings.midi_ms.append(
                (time.perf_counter()-began)*1000.0)

    def _receive_message(self, message, *, received_at=None, corrected_at=None, deferred=False):
        # Timestamp in the hardware input callback, not on the rendering thread.
        now = self.now() if received_at is None else received_at
        with self.lock:
            facts = MidiInputFacts(self.fingerprint,self.score_revision,
                self.plan.identity if self.plan else "",self.plan.active_phrase if self.plan else None,
                self.plan.hand if self.plan else "both",self.plan.bpm if self.plan else 60.,
                self.mode,self.running,self.visual_transport.paused,self.preview_only,
                self.visual_transport.play_from_beat,self.visual_transport.run_at,self.transport_id,
                self._active_tempo_map(),self.running or (self.mode == "learn" and self.teaching is not None))
            effect = self.midi_ingress.classify(message,facts=facts,now=now,deferred=deferred)
            if effect.completed_range is not None:
                ranges = self.library.settings["midi_key_ranges"].copy()
                ranges[self.midi.device] = list(effect.completed_range)
                self.set_preferences(midi_key_ranges=ranges)
            if effect.action:
                self.control(effect.action)
            if effect.consumed:
                return
            corrected_at = (now - self.library.settings["midi_offset_ms"] / 1000.0
                            if corrected_at is None else corrected_at)
            # One graded musical clock for the Recorder and the live view.
            musical_at = self._musical_seconds(corrected_at)
            # A key can reach the next attempt's musical deadline before the
            # next frame-state snapshot, even if none observed the source ending.
            # Settle only a due handoff; retain the hardware timestamp above.
            if (message.type in ("note_on", "note_off") and self.plan is not None
                    and self.mode in ("practice", "perform")
                    and not self.visual_transport.paused and self.awaiting_score_revision is None):
                due = (not self.running and self.visual_transport.next_at and now >= self.visual_transport.next_at
                       and (self.visual_transport._preview_loop_pending
                            or (self.pending_result is not None and self.auto)
                            or self.visual_transport.pending_rewind is not None))
                if (self.running and self.mode == "practice"
                        and self.plan.exercise.kind != "perform"
                        and self.review_end_beat is None and (self.auto or self.preview_only)):
                    phrase = self.plan.active_phrase
                    source_end = self.visual_transport.run_at + (self._elapsed_seconds(phrase.end-phrase.start)
                        - self._elapsed_seconds(self.visual_transport.play_from_beat))
                    due = now >= source_end + self.visual_transport.visual_gap_beats*60/self.plan.bpm
                if not deferred and (due or self.midi_ingress.deferred):
                    self.midi_ingress.deferred.append((message.copy(), now, corrected_at,
                                                self.transport_id))
                    return
            self.midi_ingress.deliver(message,facts=facts,received_at=now,corrected_at=corrected_at,
                musical_at=musical_at,recorder=self.recorder,teaching=self.teaching,
                feedback_take=self._feedback_take())

    def load(self, path: str, *, warmup: bool = False):
        # A new plan: no previous take's written rest applies (M6).
        self._rest_take_end = None
        diagnostics = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = checkpoint = time.perf_counter()
        with self._fingering_lock:
            source = Path(path).expanduser().resolve()
            fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
            piece, score = self.preprocessing.load_import(
                source, fingerprint, importer=import_piece)
            if diagnostics:
                now = time.perf_counter()
                print("SCORE_LOAD_STAGE: import", round((now-checkpoint)*1000, 1),
                      "ms", source.name, flush=True)
                checkpoint = now
            piece = replace(piece, fingering_plan=self.fingering.prepare(piece, fingerprint))
            if diagnostics:
                now = time.perf_counter()
                print("SCORE_LOAD_STAGE: fingering", round((now-checkpoint)*1000, 1),
                      "ms", "status", piece.fingering_plan.status, flush=True)
                checkpoint = now
            with self.lock:
                # Construct and restore a complete candidate before changing
                # the current session. A generator failure must leave the
                # selected score, active MIDI take and source revision intact.
                candidate = LearningPlan(piece, warmup=warmup,
                    exercise_strategy=self.library.settings['exercise_strategy'],
                    fukuda_mistakes=self.fukuda_mistakes.problematic(fingerprint),
                    feedback=self.fukuda_mistakes.evidence(fingerprint))
                self.progress.restore(candidate, fingerprint)
                self._stop(reason="source_changed")
                self._reset_trouble()
                self.course_guided = False
                self.source = str(source)
                self.is_builtin_warmup = warmup
                self.open_from_beat = 0.0
                self.fingerprint = fingerprint
                self._piece_generation += 1
                self.score_artifacts.invalidate()
                self.plan = candidate
                if diagnostics:
                    now = time.perf_counter()
                    print("SCORE_LOAD_STAGE: curriculum", round((now-checkpoint)*1000, 1),
                          "ms", self.plan.lesson_generator.name, flush=True)
                    checkpoint = now
                self.mode = "practice"
                self.teaching = None
                self.guided_range = None
                self.score = score
                self.feedback = "Press Start to practice"
                self.next_action = "Press Start to practice."
                self.score_revision += 1
                self.pending_result = None
                self._pending_assessed_bpm = None
                self.feedback_marks = []
                self.feedback_unmapped = 0
            if diagnostics:
                print("SCORE_LOAD_STAGE: ready", round((time.perf_counter()-began)*1000, 1),
                      "ms total", source.name, flush=True)

    def fingering_status(self) -> dict:
        """Return the complete original-piece assignments, independent of stage."""
        with self.lock:
            plan = self.plan.piece.fingering_plan if self.plan is not None else None
            return {"summary": plan.summary() if plan is not None else None,
                    "assignments": {sid: asdict(assignment)
                                    for sid, assignment in plan.assignments.items()}
                    if plan is not None else {}}

    def correct_fingering(self, source_id: str, finger: int | None,
                         *, fingerprint: str | None = None) -> None:
        """Save a source correction without rebuilding learning or grading notes."""
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("Choose an original source note")
        if finger is not None and (type(finger) is not int or not 1 <= finger <= 5):
            raise ValueError("Finger must be an integer from 1 to 5, or null to remove a correction")
        with self.lock:
            self._apply_listen_failure()
            if self.plan is None:
                raise ValueError("Open a piece before correcting fingering")
            if fingerprint is not None and fingerprint != self.fingerprint:
                raise ValueError("The loaded piece changed; refresh the score before correcting fingering")
            generation = self._piece_generation
        with self._fingering_lock:
            with self.lock:
                if generation != self._piece_generation:
                    raise ValueError("The loaded piece changed; refresh the score before correcting fingering")
                piece, source_fingerprint = self.plan.piece, self.fingerprint
            plan = self.fingering.correct(piece, source_fingerprint, source_id, finger)
            with self.lock:
                # Navigation/reset may replace LearningPlan while inference is
                # running. Update its current Piece, never the captured plan.
                if (generation != self._piece_generation or self.plan is None
                        or self.fingerprint != source_fingerprint
                        or self.plan.piece.notes is not piece.notes):
                    raise ValueError("The loaded piece changed; refresh the score before correcting fingering")
                self._apply_listen_failure()
                self.plan.piece = replace(self.plan.piece, fingering_plan=plan)
                self.score_artifacts.invalidate()
                self.score_revision += 1
                if self.awaiting_score_revision is not None:
                    self.awaiting_score_revision = self.score_revision
                    self._deferred_score_ack = None
                    self.listen.retarget_score(self.score_revision)

    def _restore(self):
        self.progress.restore(self.plan, self.fingerprint)

    def _save(self):
        self.progress.save(self.plan, self.fingerprint)

    def _reset_current_path(self, *, fingerprint: str, confirm: bool) -> None:
        """Forget only the loaded piece's learning path and restart at step 1.

        A caller must identify the currently loaded source so a stale UI
        confirmation cannot erase a different piece after a library switch.
        Music files, shared preferences and other pieces remain untouched.
        """
        if self.plan is None or not self.fingerprint:
            raise ValueError("Open a piece before resetting its lesson path")
        if confirm is not True or fingerprint != self.fingerprint:
            raise ValueError("Confirm the reset for the currently loaded piece")
        piece = self.plan.piece
        warmup = self.is_builtin_warmup
        # Validate the reset course against cleared source feedback while the
        # current take and durable records are still intact. A reset rebuilds
        # the same course (the active plan's generator), never another one.
        replacement = LearningPlan(piece, warmup=warmup,
                    exercise_strategy=self.plan.exercise_strategy.name,
                    fukuda_mistakes=frozenset(), feedback={})
        # Publish all replacement records before stopping the current take.
        with self.measurement.atomic():
            self.measurement.interrupt("lesson_reset", self.recorder.presses if self.recorder else
                                       self.measurement.guided.presses)
            self.measurement.flush_intervals(self.now())
            self.progress.reset_piece(fingerprint)
            self.fukuda_mistakes.reset(fingerprint)
            self.progress.save(replacement, fingerprint)
            self.measurement.event("lesson_reset", {"fingerprint": fingerprint,
                                                    "preserves_history": True})
        self._stop(reason="lesson_reset", persist_evidence=False)
        self._reset_trouble()
        self.plan = replacement
        self.open_from_beat = 0.0
        self.course_guided = False
        self.mode = "practice"
        self.teaching = None
        self.guided_range = None
        self.score_artifacts.invalidate()
        self.score_revision += 1
        self.awaiting_score_revision = None
        self.feedback = "Lesson path reset to its first step"
        self.next_action = "Press Play when you are ready."

    def _stop(self, *, reason: str | None = None, preserve_episode: bool = False,
              persist_evidence: bool = True):
        reason = reason or self._action_reason
        played = (self.recorder.presses if self.recorder is not None else
                  self.measurement.guided.presses)
        if persist_evidence:
            with self.measurement.atomic():
                self.measurement.interrupt(reason, played, censor=not preserve_episode,
                    extra={"guidance": self.teaching.snapshot(now=self.now())}
                          if self.mode == "learn" and self.teaching is not None else None)
                self.measurement.flush_intervals(self.now())
        self.attempt_settlement.cancel(reason=reason, now=self.now())
        self.midi_ingress.deferred.clear()
        self.midi_ingress.resume_grading_after = 0.0
        self.midi_ingress.resume_ignored_pitches.clear()
        self._pause_floor = None
        # Stopping/restarting a take does not invalidate precompiled next
        # notation. Its stage-key + score revision remain authoritative:
        # navigation, library changes and generation mismatches fail that
        # identity check automatically at the next settlement.
        self._prepared_stage_published = False
        self.teaching_continuation.cancel()
        self._native_preload_failure = None
        self.guided_session.stop()
        self.visual_transport.reset_for_stop(
            rewind_seconds=SETTINGS.feedback_seconds)
        self.pause_context=None
        self._deferred_score_ack=None
        self.running=False
        self.auto=False
        self.preview_only=False
        self.count_in_beats=0
        self.awaiting_score_revision=None
        self.recorder=None
        self.pending_result=None
        self._pending_assessed_bpm = None
        self.feedback_marks=[]
        self.feedback_unmapped=0
        self.recovery_notice = None
        self.live_input.reset_attempt()
        self.retry_range=None
        self._guided_recovery_pending=False
        self._guided_return=None
        self.listen.cancel()
        self.performance_summary=None
        self.review_stage_identity=None
        self.review_end_beat=None
        self._automatic_remedial_review=False
        self.review_session_complete=False
        self._guided_prepared=False
        self._remediation_pending = None
        self._remediation_active = None
        self._pending_rolling = None
        self._settlement_failed = False


    def _learner_saved(self, stage_key: str | None = None) -> dict:
        return self.learner_progress.saved(
            self.plan, fingerprint=self.fingerprint, stage_key=stage_key)

    def _guided_unit(self) -> dict | None:
        return self.learner_progress.guided_unit(
            self.plan, mode=self.mode, guided_range=self.guided_range)

    def _save_guided_preparation(self):
        guidance = (self.teaching.snapshot(now=self.now()) if self.mode == "learn" and self.teaching else None)
        if not guidance or self.measurement.attempt_id is None:
            return
        if not guidance["completed"]:
            self.measurement.observe_guidance(guidance)
            return
        pending = self.attempt_settlement.pending
        if pending is None or pending.event.attempt_id != self.measurement.attempt_id:
            pending = self._prepare_teaching("guided_completed", completed=True,
                assisted_count=guidance.get("assisted_count",0))
        self.measurement.seal(self.measurement.guided.presses,state="completed",
            reason="guided_preparation",extra={"guidance":guidance})
        try:
            self.attempt_settlement.settle(pending,plan=self.plan,binding=self._teaching_binding(),now=self.now(),
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]))
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=self.now())
            self.feedback = "Could not save the guided preparation"
            self.next_action = "Check storage, then Resume to save this same exposure."
            raise
        self.guided_session.prepared = not pending.state.route.remediation_active
        if pending.decision.next_exposure is not None:
            self._enter_selected_exposure(pending.decision.next_exposure)


    def _learner_snapshot(self) -> dict:
        return self.learner_progress.snapshot(
            self.plan, fingerprint=self.fingerprint, mode=self.mode,
            guided_range=self.guided_range, course_guided=self.course_guided)

    def _enter_selected_exposure(self, selected):
        if selected is None:
            self.auto = False
            return
        if selected.mode == "learn":
            self._begin_learn(from_beat=selected.from_beat,exposure=selected)
        elif selected.mode == "perform":
            self._prepare_perform(exposure=selected)
        else:
            self._prepare_practice(exposure=selected)

    def _begin_course_stage(self, *, bump_revision: bool = True, explicit_learn: bool = False):
        effect = self._manual_effect("learn" if explicit_learn else "course_stage")
        selected = self._install_command(effect)
        if selected is None:
            return
        if selected.mode == "perform":
            self._prepare_perform(exposure=selected)
        elif selected.mode == "learn":
            self._begin_learn(from_beat=selected.from_beat, bump_revision=bump_revision, exposure=selected)
        else:
            self._prepare_practice(exposure=selected)


    def _skip_stage(self, reason):
        effect = self._manual_effect("skip_stage", values={"reason":reason})
        self.learner_progress.mark_skipped(fingerprint=self.fingerprint, stage_key=self.plan.identity, reason=reason)
        self._stop(reason="skip_stage")
        selected = self._install_command(effect)
        self._reset_trouble()
        self.course_guided = True
        self._enter_selected_exposure(selected)
        self._save()

    def _place_original(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        effect = self._manual_effect("place_original")
        key = effect.decision.next_exposure.stage_key
        candidate = next(step for step in self.plan.lesson_steps if step.key == key)
        self.learner_progress.mark_prior_steps_placed(self.plan, fingerprint=self.fingerprint, candidate=candidate)
        self._stop()
        selected = self._install_command(effect)
        self._reset_trouble()
        self.course_guided = True
        self._enter_selected_exposure(selected)
        self._save()

    def _valid_trouble_spots(self, *, stage_key: str | None = None) -> list[dict]:
        return self.learner_progress.valid_trouble_spots(
            self.plan, fingerprint=self.fingerprint, stage_key=stage_key)

    def _revisit_trouble(self, stage_key, start_beat):
        effect = self._manual_effect("revisit_trouble", from_beat=start_beat, values={"stage_key":stage_key})
        self._stop()
        selected = self._install_command(effect)
        self._reset_trouble()
        self.learner_progress.reactivate_trouble(fingerprint=self.fingerprint, stage_key=selected.stage_key)
        self.course_guided = True
        grid = phrase_grid(self.plan.active_phrase,self.plan.piece.bar_boundaries)
        self.retry_range = {"first_bar":self.plan.active_phrase.first_bar+grid.index(selected.from_beat),
            "last_bar":self.plan.active_phrase.first_bar+grid.index(selected.end_beat)-1,
            "start_beat":selected.from_beat,"end_beat":selected.end_beat}
        self._begin_learn(from_beat=selected.from_beat,recovery=True,exposure=selected)
        self._save()

    def _record_saved_trouble(self, phrase: Phrase, result, *, start: float, end: float, errors: int):
        if self.plan is not None:
            self.learner_progress.record_saved_trouble(
                self.plan, fingerprint=self.fingerprint,
                phrase_start=phrase.start, assessed_notes=result.notes,
                start=start, end=end, errors=errors)

    def _reset_trouble(self):
        self._trouble_key = None
        self._trouble_count = 0

    def display_phrase(self) -> Phrase:
        """One source-derived fragment in Learn; the exact full variant in time."""
        if self.plan is None:
            raise ValueError("Open a piece first")
        phrase = self.plan.active_phrase
        if self.mode != "learn" or self.guided_range is None:
            return phrase
        start, end = self.guided_range
        current = self.guided_session.fragment
        if (current is not None and current.beat_range == (start, end)
                and current.phrase.number == phrase.number
                and current.phrase.start >= phrase.start
                and current.phrase.end <= phrase.end):
            return current.phrase
        grid = phrase_grid(phrase, self.plan.piece.bar_boundaries)
        first = next(i for i, beat in enumerate(grid) if abs(beat-start) < 1e-6)
        last = next(i for i, beat in enumerate(grid) if abs(beat-end) < 1e-6)
        absolute_start, absolute_end = phrase.start+start, phrase.start+end
        return Phrase(phrase.number, phrase.first_bar+first, phrase.first_bar+last-1,
                      absolute_start, absolute_end,
                      tuple(n for n in phrase.notes if absolute_start-1e-7 <= n.start < absolute_end-1e-7))

    def _begin_learn(self, *, from_beat: float = 0.0, bump_revision: bool = True,
                     recovery: bool = False,
                     remediation: RemedialAssignment | None = None, exposure=None):
        if self.plan is None:
            raise ValueError("Open a piece first")
        selected = exposure or self._install_command(self._manual_effect("learn",from_beat=from_beat))
        start,end = selected.from_beat,selected.end_beat
        if end is None:
            end = self.plan.active_phrase.end-self.plan.active_phrase.start
        from .application.guided_session import materialize_fragment
        fragment = materialize_fragment(self.plan.active_variant,self.plan.piece.bar_boundaries,start=start,end=end)
        retry_range = self.retry_range if recovery else None
        self._stop(reason="guided_recovery" if recovery else "learn", preserve_episode=recovery)
        self._guided_stream_deadline = None
        self._remediation_active = remediation
        if recovery:
            self.retry_range = retry_range
            self._guided_return = (self.plan.identity, start)
        self.mode = "learn"
        self.guided_range = (start, end)
        unit = self._guided_unit()
        self.learner_progress.save_resume(
            fingerprint=self.fingerprint, stage_key=self.plan.identity, unit=unit)
        if bump_revision:
            self.score_revision += 1
        self._open_take()
        # Reuse the existing guided owner: one controller, held-key history,
        # fragment source and completion state for this teaching session.
        self.guided_session.bind(GuidedFragment(
            variant=(remediation.variant if remediation is not None
                     else self.plan.active_variant),
            start_beat=start, end_beat=end,
            phrase=fragment.phrase),
            stage_key=self.plan.identity, revision=self.score_revision,
            now=self.now(), connected=self.midi.connected,
            recovery=recovery)
        self.measurement.begin(self._learning_context(scope="guided", start=start, end=end))
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing a short idea to learn"
        self.next_action = (f"Learn the selected {remediation.focus} notes, then retry the original."
                            if remediation is not None else
                            f"Learn bars {fragment.phrase.first_bar}-{fragment.phrase.last_bar} "
                            "at your own pace, then retry the rhythm.")
        self._save()

    def _guided_marks(self, snapshot: dict) -> list[dict]:
        """Project current guided note identities through the owned fragment."""
        if self.plan is None:
            return []
        engraving = self.score_artifacts.cached_layout(self._score_selection())
        return (self.guided_session.marks(snapshot, engraving.layout)
                if engraving is not None else [])


    def _prepare_practice(self, *, exposure=None):
        if self.plan is None:
            raise ValueError("Open a piece first")
        effect = None if exposure is not None else self._manual_effect("practice")
        selected = exposure or self._install_command(effect)
        return_context = self._guided_return
        retry_range = self.retry_range
        self._stop(reason="reintegration", preserve_episode=return_context is not None)
        self.visual_transport.play_from_beat = selected.from_beat
        self.open_from_beat = selected.from_beat
        self.review_end_beat = selected.end_beat
        if return_context is not None:
            self.visual_transport.pending_rewind = selected.from_beat
            self.retry_range = retry_range
            self._guided_return = return_context
        self.mode = "practice"
        self.teaching = None
        self.guided_range = None
        self.score_revision += 1
        # Warm-ups must return from Listen to an idle, rendered exercise.
        # The student starts when ready with a fresh piano key, not because
        # a score download completed.
        self.awaiting_score_revision = None if self.is_builtin_warmup else self.score_revision
        self.feedback = "Warm-up ready" if self.is_builtin_warmup else "Preparing rhythm practice"
        self.next_action = ("Play a piano key to start the count-in."
                            if self.is_builtin_warmup else
                            "Get ready to retry the rhythm." if return_context else "Get ready to play in time.")

    def _apply_listen_failure(self) -> None:
        failure = self.listen.take_failure()
        if failure is not None:
            self.awaiting_score_revision = None
            self.feedback = failure
            self.next_action = failure

    def _prepare_listen(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        selected = self._install_command(self._manual_effect("listen"))
        self._stop()
        self.visual_transport.play_from_beat = 0.0
        self.mode = "listen"
        self.teaching = None
        self.guided_range = None
        self.score_revision += 1
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing an audible example"
        self.next_action = "Listen to the notes, then choose Learn or Practice."
        self.listen.prepare(ListenSelection(
            variant=self.plan.active_variant, bpm=self.plan.bpm,
            stage_key=self.plan.identity, revision=self.score_revision,
            bar_boundaries=self.plan.piece.bar_boundaries,
            time_signatures=self.plan.piece.time_signatures,
            tempo_map=self._active_tempo_map()))

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            return self.listen.audio_path(token)

    def _start_listen_if_ready(self):
        self._apply_listen_failure()
        if (self.mode != "listen" or self.visual_transport.paused or self.running
                or self.awaiting_score_revision != self.score_revision):
            return
        start = self.listen.begin_playback(self.score_revision)
        if start is None:
            return
        self.awaiting_score_revision = None
        self._open_take()
        self.running = True
        self.count_in_bar_beats = start.count_in_bar_beats
        self.count_in_meter = list(start.count_in_meter)
        self.count_in_beats = start.count_in_beats
        self.visual_transport.run_at = self.now()+start.delay_seconds
        self.feedback = "Count in, then listen"

    def _prepare_perform(self, *, scope: str = "current", exposure=None):
        if self.plan is None:
            raise ValueError("Open a piece first")
        effect = None if exposure is not None else self._manual_effect("perform",values={"scope":scope})
        selected = exposure or self._install_command(effect)
        self._stop()
        self.open_from_beat = selected.from_beat
        self.review_end_beat = selected.end_beat
        self.mode = "perform"
        self.teaching = None
        self.guided_range = None
        self.score_revision += 1
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing your performance"
        self.next_action = "Keep playing through the passage. Review comes at the end."

    def _performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self._active_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.visual_transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.plan.piece.bar_boundaries,
            played_from_beat=self.visual_transport.play_from_beat, bpm=self.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

    def _review_retry(self, first_bar, last_bar):
        effect = self._manual_effect("review_retry",values={"first_bar":first_bar,"last_bar":last_bar})
        selected = self._install_command(effect)
        self._prepare_practice(exposure=selected)
        self.open_from_beat = selected.from_beat
        self.review_end_beat = selected.end_beat or self.plan.active_phrase.end-self.plan.active_phrase.start
        self.retry_range = {"first_bar":first_bar,"last_bar":last_bar,
            "start_beat":self.open_from_beat,"end_beat":self.review_end_beat}
        self.awaiting_score_revision = None
        self.auto = False
        self.feedback = f"Ready to repeat measures {first_bar}-{last_bar}"
        self.next_action = "Press Start to practise this section; no mastery is awarded for a partial attempt."

    def _practice_weak(self):
        effect = self._manual_effect("practice_weak")
        selected = self._install_command(effect)
        self._prepare_practice(exposure=selected)
        self.open_from_beat = selected.from_beat
        self.review_end_beat = selected.end_beat or self.plan.active_phrase.end-self.plan.active_phrase.start
        # _prepare_practice resets a previous retry range. Re-publish the
        # bounded, source-selected weak passage after preparing the new take,
        # exactly as the explicit review_retry command does. The frontend
        # and review completion must agree on this one graded interval.
        self.retry_range = {"start_beat": self.open_from_beat,
                            "end_beat": self.review_end_beat}
        self.awaiting_score_revision = None
        self.auto = False
        self.next_action = "Press Start to practise this section; no mastery is awarded for a partial attempt."

    def _seek_grid(self) -> tuple[float, ...] | None:
        if (self.plan is None or self.mode not in ("learn", "practice", "perform")
                or not self.plan.piece.bar_boundaries):
            return None
        try:
            return phrase_grid(self.plan.active_phrase, self.plan.piece.bar_boundaries)
        except ValueError:
            return None

    def _seek(self, bar):
        # A seek must never guess a measure from synthetic/fallback bar
        # numbering. Validate original source boundaries *before* preparing
        # any command or cancelling a paused transport.
        if self._seek_grid() is None:
            raise ValueError("Seeking requires the original source measure grid")
        effect = self._manual_effect("seek",values={"bar":bar})
        selected = self._install_command(effect)
        if selected.mode == "learn":
            self._begin_learn(from_beat=selected.from_beat,exposure=selected)
        else:
            self._prepare_practice(exposure=selected)
            self.visual_transport.pending_rewind = selected.from_beat
            self.retry_range = {"first_bar":bar,"last_bar":self.plan.active_phrase.last_bar,
                "start_beat":selected.from_beat,"end_beat":self.plan.active_phrase.end-self.plan.active_phrase.start}
            self.next_action = f"Get ready to play from bar {bar} at {selected.bpm} BPM."


    def _teaching_binding(self):
        owner = self.attempt_settlement
        return TeachingBinding(self.measurement.run_id, self.measurement.session_id,
            self.fingerprint, self.plan.identity, owner.course_revision,
            owner.authority_revision, self.transport_id, owner.cancellation_generation)

    def _prepare_teaching(self, kind, result=None, *, rolling=None, manual=None, action=None,
                          from_beat=None, end_beat=None, store=True, values=None, completed=False, assisted_count=0):
        p = self.plan
        values = values or {}
        event = TeachingEvent(1, (identifier() if kind in ("manual","interrupted","source_feedback_changed") else self.measurement.attempt_id or identifier())+":"+kind+(":"+str(end_beat) if kind == "rolling_result" else ""), kind,
            self.measurement.attempt_id, result, rolling, manual, action, from_beat, end_beat,
            assisted_count=assisted_count, completed=completed, reason=values.get("reason"),
            bar=values.get("bar"), first_bar=values.get("first_bar"), last_bar=values.get("last_bar"),
            scope=values.get("scope"), requested_stage=values.get("stage_key"), requested_mode=values.get("mode"))
        scope = completion_route(self.mode, self.review_end_beat, self.visual_transport.play_from_beat)
        if self._automatic_remedial_review and scope == "section_review":
            scope = "partial_recovery"
        policy = resolve_mistake_policy(self.library.settings["mistake_response_strategy"])
        history = (self.practice_policy.store.recent(self.fingerprint, p.identity)
                   if self.fingerprint else LearnerSnapshot(p.identity, ()))
        state = TeachingState(1, self._teaching_binding(), p.course_state(), policy,
            tuple(sorted(self.fukuda_mistakes.evidence(self.fingerprint).items())) if self.fingerprint else (),
            history, self._retry_context(result, end_beat=end_beat) if result is not None and (policy.whole_handler is not None or policy.rolling_handler is not None) else None,
            TeachingRouteFacts(mode=self.mode, automatic=self.auto, warmup=self.is_builtin_warmup,
                preview_only=self.preview_only, assistance_used=self.measurement.assistance_used,
                scope=scope, performed_bpm=self._pending_assessed_bpm or p.bpm,
                from_beat=self.visual_transport.play_from_beat,
                end_beat=end_beat if end_beat is not None else p.active_phrase.end-p.active_phrase.start,
                course_guided=self.course_guided, guided_return=self._guided_return,
                guided_range=self.guided_range, review_end_beat=self.review_end_beat,
                remediation_active=self._remediation_active is not None,
                trouble_key=self._trouble_key, trouble_count=self._trouble_count,
                parent_decision_id=self.measurement.parent_decision),
            self.practice_policy.diagnosis, self.practice_policy.learner,
            getattr(p.lesson_generator, "catalog", None),
            ManualFacts(credits=self.learner_progress.teaching_credits(self.fingerprint),
                trouble=tuple((unit["stage_key"],unit["start_beat"],unit["end_beat"],tuple(unit["source_indices"]))
                    for unit in self._valid_trouble_spots()),
                review=tuple((u["first_bar"],u["last_bar"],u["start_beat"],u["end_beat"],u["errors"])
                    for u in (self.performance_summary or {}).get("sections",())),
                review_current=self.review_stage_identity == p.identity,
                paused=self.visual_transport.paused,
                guidance_completed=bool(self.teaching is not None and self.teaching.snapshot(now=self.now())["completed"]),
                open_from_beat=self.open_from_beat,pending_rewind=self.visual_transport.pending_rewind))
        if not store:
            return self.session_commands.prepare(event=event, state=state, generator=p.lesson_generator)
        return self.attempt_settlement.prepare(event=event, state=state, generator=p.lesson_generator)

    def _manual_effect(self, action, *, from_beat=None, values=None):
        return self.session_commands.active or self._prepare_teaching("manual", action=action,
            from_beat=from_beat, values=values, store=False)

    def _install_command(self, effect):
        current = self.plan.teaching_progress()
        if current == effect.decision.before_progress:
            if self.session_commands.apply_progress(effect, plan=self.plan):
                self.attempt_settlement.authority_revision += 1
        elif current != effect.decision.progress_after:
            raise ValueError("Manual teaching progress changed before application")
        return effect.decision.next_exposure

    @property
    def _presentation_bpm(self):
        pending = self.attempt_settlement.pending
        if pending is not None and pending.receipt is None and pending.decision.next_exposure is not None:
            return pending.decision.next_exposure.bpm
        return self.plan.bpm if self.plan is not None else 0

    def _commit_pending(self) -> str:
        if self.pending_result is None or self.plan is None:
            return ""
        p = self.plan
        pending = self.attempt_settlement.pending
        if pending is None or pending.assessment is not self.pending_result:
            pending = self._prepare_teaching("full_result", self.pending_result)
        decision = pending.decision
        self.teaching_continuation.validate_announcement(pending)
        if pending.state.policy != resolve_mistake_policy(self.library.settings["mistake_response_strategy"]):
            raise ValueError("Teaching policy changed before settlement")
        chosen = replace(pending.state.course, definition=decision.definition_after,
                         progress=decision.progress_after)
        changed = chosen.key != p.identity
        prebuilt = None
        if changed and self.teaching_continuation.reservation is not None:
            selection, _ = self._decided_stage_selection()
            if self._future_stage_ready != (selection.stage_key, selection.revision) or self.teaching_continuation.reservation[0] != selection.identity:
                raise UnpreparedNextStage("The decided lesson selected a different next score")
            prebuilt = self.teaching_continuation.reservation[1]
            if prebuilt is None:
                raise UnpreparedNextStage("The next lesson score changed after preloading")
        previous_duration = p.active_phrase.end-p.active_phrase.start
        try:
            outcome = self.attempt_settlement.settle(pending, plan=p,
                binding=self._teaching_binding(), now=self.now(),continuation=self.teaching_continuation)
        except BaseException:
            self._settlement_failed = True
            raise
        # Mechanical publication occurs only after the shared transaction commits.
        self._prepared_stage_published = False
        self.retry_range = None
        if self.pending_result.passed:
            self._reset_trouble()
        self._remediation_pending = decision.remediation
        if outcome.accelerated:
            self.recovery_notice = {"kind": "speedup", "errors": 0,
                "from_bpm": outcome.previous_bpm, "to_bpm": p.bpm,
                "first_bar": p.active_phrase.first_bar, "last_bar": p.active_phrase.last_bar,
                "expires_at": self.now()+7.0}
        if changed:
            self.open_from_beat = 0.0
            self.performance_summary = self.review_stage_identity = None
            self.score_revision += 1
            self.awaiting_score_revision = None
            if prebuilt is None and self.auto and self._future_stage_ready == (p.identity, self.score_revision):
                prebuilt = self.future_score.adopt(self._score_selection())
            if prebuilt is not None:
                self.score_artifacts = prebuilt
                self._prepared_stage_published = True
                self.visual_transport.visual_offset_beats = (self.teaching_continuation.handoff_world
                    if self.teaching_continuation.handoff_world is not None else
                    self.visual_transport.visual_offset_beats+previous_duration+SETTLEMENT_SECONDS*outcome.previous_bpm/60.)
            else:
                self.score_artifacts.invalidate()
                self.visual_transport.visual_offset_beats = 0.0
        self.pending_result = None
        self._pending_assessed_bpm = None
        self._settlement_failed = False
        self.teaching_continuation.handoff_world = self.teaching_continuation.reservation = None
        return outcome.message

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float | None = None,
              presentation_lead_seconds: float = 0.0, decided: bool = False):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            effect = self.session_commands.active
            selected = None
            pending = self.attempt_settlement.pending
            if loop_continuation and pending is not None and pending.receipt is not None:
                selected = pending.decision.next_exposure
            elif decided:
                selected = self.session_commands.prepared
            if effect is None and not decided and not loop_continuation and scheduled_deadline is None:
                effect = self._prepare_teaching("manual", action="start", from_beat=from_beat, store=False, values={"mode":mode})
            if effect is not None:
                selected = effect.decision.next_exposure
                if selected is None:
                    return
                self._install_command(effect)
            if selected is not None and selected.stage_key == self.plan.identity:
                from_beat = selected.from_beat
                mode = selected.mode
            if self.mode == "learn":
                self._prepare_practice(exposure=selected)
                return
            if self.measurement.attempt_id is not None:
                self.measurement.interrupt("restart", self.recorder.presses if self.recorder else ())
            self.midi_ingress.resume_grading_after = 0.0
            self.midi_ingress.resume_ignored_pitches.clear()
            self._pause_floor = None
            self.mode = mode
            self.teaching = None
            self.guided_range = None
            self._guided_return = None
            self.performance_summary = None
            self.review_stage_identity = None
            self.review_session_complete = False
            self.preview_only = not self.midi.connected
            phrase = self.plan.active_phrase
            # Only the engine mutates transport and input state. The timing
            # policy below receives an explicit immutable musical schedule.
            self.visual_transport.begin_take(loop_continuation=loop_continuation)
            self._open_take(phrase=phrase, recording=True)
            self.running = True
            self.auto = (selected.automatic if selected is not None else mode == "practice") and not self.preview_only
            self.awaiting_score_revision = None
            self.visual_transport.visual_gap_beats = self._source_model()[
                "practice_timeline"]["gap"]["duration_beats"]
            position = self.open_from_beat if from_beat is None else from_beat
            scheduled = self.attempt_progression.schedule_start(
                phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
                time_signatures=self.plan.piece.time_signatures,
                bpm=self.plan.bpm, position=position,
                loop_continuation=loop_continuation,
                preview=self.preview_only, now=self.now())
            self.visual_transport.play_from_beat = scheduled.from_beat
            self.count_in_bar_beats = scheduled.count_in_bar_beats
            self.count_in_meter = list(scheduled.count_in_meter)
            self.count_in_beats = scheduled.count_in_beats
            self.next_boundary_beat = scheduled.next_boundary_beat
            self.visual_transport.run_at = (scheduled.run_at if scheduled_deadline is None
                                            else scheduled_deadline)
            if scheduled_deadline is None and presentation_lead_seconds > 0:
                # The renderer's reserved score deadline is the graded
                # deadline. Any lead longer than the count-in is silent:
                # the count-in stays the single bar before the first beat
                # (owner decision 2026-11-08: one "Ichi Ni San Shi" only).
                self.visual_transport.run_at = max(
                    self.visual_transport.run_at,
                    self.now() + presentation_lead_seconds)
            scope = ("preview" if self.preview_only else "perform" if mode == "perform" else
                     "partial" if self._automatic_remedial_review else
                     "section_review" if self.review_end_beat is not None else
                     "partial" if scheduled.from_beat > 1e-7 else "full")
            try:
                self.measurement.begin(self._learning_context(
                    scope=scope, start=scheduled.from_beat,
                    end=self.review_end_beat or phrase.end-phrase.start,
                    run_at=self.visual_transport.run_at))
            except Exception:
                self.running = False
                self.recorder = None
                self.auto = False
                self.feedback = "Could not record the start of this attempt"
                raise
            self.measurement.phase_changed("count_in" if self.count_in_beats else "active", self.now())
            self.feedback = "Count in, then play"
            self.next_action = scheduled.next_action

    def _next_count_in_beats(self) -> float:
        """The one count-in bar a user Play or Resume gets now.

        One full bar of the starting measure at any tempo (lead_in_beats,
        owner decision 2026-11-08). The renderer places an opening on an empty strip
        exactly this far ahead of the playhead, so Play to first note is one
        count-in bar and the score and graded deadlines stay identical.
        """
        if self.plan is None or self.plan.bpm <= 0:
            return 0.0
        if self.running or self.visual_transport.paused:
            bar_beats = self.count_in_bar_beats
        else:
            phrase = self.plan.active_phrase
            _, bar_beats, _ = self.attempt_progression.count_in_bar(
                phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
                time_signatures=self.plan.piece.time_signatures,
                position=self.open_from_beat)
        return lead_in_beats(bar_beats, self.plan.bpm) if bar_beats > 0 else 0.0

    def _next_count_in_meter(self) -> list[int]:
        """The meter of that count-in bar (its syllables and pulses)."""
        if self.plan is None or self.running or self.visual_transport.paused:
            return list(self.count_in_meter)
        _, _, meter = self.attempt_progression.count_in_bar(
            phrase=self.plan.active_phrase, boundaries=self.plan.piece.bar_boundaries,
            time_signatures=self.plan.piece.time_signatures,
            position=self.open_from_beat)
        return [int(meter[0]), int(meter[1])]

    def _continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Retain polling overshoot instead of moving the musical deadline."""
        announced = self.visual_transport.announced_deadline(from_beat)
        serial = (self.visual_transport.announce_serial
                  if announced is not None and abs(announced - deadline) <= 1e-9 else None)
        self.start(from_beat=from_beat, mode=self.mode, loop_continuation=True,
                   scheduled_deadline=deadline)
        self._queue_scheduled_start = (
            self.transport_id, self.visual_transport.play_from_beat,
            self.visual_transport.run_at, self.plan.identity,
            self.score_revision, serial)
        # An announced continuation starts AT its first graded beat; Godot
        # spoke its one count-in bar from the announced deadline during the
        # rest. A continuation that still has a whole bar of lead counts
        # that last bar itself (owner decision: one bar before every take).
        lead_beats = ((self.visual_transport.run_at - self.now())
                      * self.plan.bpm / 60.0)
        if self.count_in_bar_beats > 0 and \
                lead_beats >= self.count_in_bar_beats - 1e-6:
            self.count_in_beats = lead_in_beats(self.count_in_bar_beats, self.plan.bpm)

    def _reannounce_after_rest_pause(self, now: float, lead_seconds: float,
                                     *, reuse: bool = False) -> None:
        """Resume in the rest between takes: re-time or re-announce the take.

        resume() shifted the announced deadline by the pause, but the
        presentation axis kept moving. Godot reports either that the
        announced copy is still ahead of the playhead (reuse: the take keeps
        that ink and its plan identity, re-timed to reach the playhead in
        lead_seconds, like Resume of a paused take) or the earliest lead at
        which fresh ink can still be admitted; then a new announcement (new
        plan identity) is made no earlier than that, and the old copy, if
        visible, never gets a count-in.
        """
        announced = self.visual_transport.announced_continuation
        if (self.running or self.plan is None or self.mode != "practice"
                or announced is None
                or self.visual_transport.announced_deadline(announced[0]) is None):
            return
        if lead_seconds <= 0 and self._short_rest is None and self._continuous_horizon_beats <= 0:
            return
        # Godot owns the reuse decision (one count-in pulse plus the published
        # latency still ahead, at the announced tempo); it is not re-decided.
        if reuse and lead_seconds > 0.0:
            self.visual_transport.retime_announcement(now + float(lead_seconds))
            return
        floor = (self._short_rest_deadline(0.0, from_beat=announced[0], now=now)
                 if self._short_rest is not None else
                 now + self._continuous_horizon_beats * 60.0 / self.plan.bpm)
        # The copy announced before the pause is not reused, so it never
        # gets this take: always a NEW announcement (new plan identity) at
        # the earliest place Godot reported for fresh ink. Keeping the old
        # identity with resume()'s shifted deadline bound the take to the
        # old copy 1.7-1.9 beats off the playhead (round 4, Hanon).
        deadline = max(now + max(0.0, float(lead_seconds)), floor)
        self.visual_transport.announce_continuation(
            announced[0], deadline, announced[2])

    def _continuation_deadline(self, deadline: float, from_beat: float) -> float:
        """The ONE graded run_at of an automatic same-stage continuation.

        A continuation scheduled when the previous take finished was
        announced (score_queue_next) with this exact deadline, so Godot
        admitted its source offscreen at that world position. It starts
        unchanged: adding another reading lead here made the graded beat
        follow the visible ink by (horizon - rest) beats (R1 P1/M1).

        An unannounced continuation (a policy changed the source opening at
        settlement) gets a fresh full offscreen horizon from now, so its ink
        can still be admitted beyond the right edge before it is graded.
        """
        announced = self.visual_transport.announced_deadline(from_beat)
        if announced is not None and abs(announced - deadline) <= 1e-9:
            return deadline
        if self.plan is None or not self.auto:
            return deadline
        short = self._short_rest_deadline(
            None if self._rest_take_end is not None else deadline,
            from_beat=from_beat)
        if short is not None:
            # Settled early, during the written rest: open right after it.
            return max(deadline, short)
        if self._continuous_horizon_beats <= 0:
            return deadline
        return max(self._automatic_stream_deadline(deadline),
                   self.now() + self._continuous_horizon_beats * 60.0 / self.plan.bpm)



    def _start_rate_bpm(self, from_beat: float, bpm: float) -> float:
        """Authored tempo-map rate at a take's first beat, at this BPM."""
        if self.plan is None or bpm <= 0 or self.mode not in ("practice", "listen"):
            return float(bpm)
        tempo = self.tempo_map_cache.get(self.plan.active_stage, bpm)
        return float(tempo.bpm_at(from_beat)) if tempo is not None else float(bpm)

    def _note_tempo(self, now: float) -> None:
        """Remember WHEN the presentation tempo changed (tempo_epoch_ms).

        Godot sees a new BPM one snapshot later; it switches its forward-only
        presentation axis at this exact instant instead, so deadlines the
        engine computes from this moment at the new tempo stay equal to the
        ink (a stage handoff from 108 to 40 BPM drifted ~0.15 beat).
        """
        if self.plan is None:
            return
        key = (self.plan.identity, float(self._presentation_bpm))
        if key != self._tempo_key:
            self._tempo_key = key
            self._tempo_epoch = now




    def _schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float,
                              reading_lead_included: bool = False,
                              announce: bool = True,
                              short_deadline: float | None = None):
        """Reverse on this pass, then traverse one semantic rest into target.

        The resulting next_at is the graded run_at of the next take and is
        announced as such. reading_lead_included: reverse_seconds was
        derived from a renderer-reserved world position (manual Retry), so
        the deadline already IS that admitted position; adding the automatic
        reading horizon on top made the retried ink arrive early (R1 P3).
        """
        self.visual_transport.schedule_source_preparation(
            self._source_model(), source_from_beat=target,
            from_visual=from_visual, now=now,
            reverse_seconds=reverse_seconds, bpm=self._presentation_bpm)
        if announce and short_deadline is not None:
            # Short rest (P5): the repeat opens on the empty strip one
            # count-in bar ahead; the engine's own rewind animation ends by
            # then. This IS the announced deadline.
            vt = self.visual_transport
            vt.next_at = short_deadline
            vt._preparation_at = min(vt._preparation_at, short_deadline)
            vt._visual_rewind_seconds = max(
                .05, min(vt._visual_rewind_seconds, vt._preparation_at - vt._visual_rewind_at))
        elif not announce and short_deadline is not None:
            # Round 4: a failed take whose settlement may re-engrave or
            # reroute settles now, during its written rest bar, so whatever
            # runs next opens straight after that bar (_continuation_deadline
            # and the score acknowledgement use the recorded take end).
            self.visual_transport.next_at = now
        elif not reading_lead_included and announce:
            # An unannounced take gets its whole reading horizon when it is
            # settled (_continuation_deadline); adding it here as well would
            # double the rest.
            # An automatic recovery target may differ from the speculative
            # next passage. Its newly queued source must have the SAME
            # offscreen reading lead as a normal automatic repeat, after the
            # authentic printed rest. Godot never moves old ink.
            upcoming_rest = float(
                self.visual_transport.practice_preparation["measure"][
                    "duration_beats"])
            missing = max(
                0.0,
                self._continuous_horizon_beats - upcoming_rest,
            )
            self.visual_transport.next_at += missing * 60.0 / self._presentation_bpm
        if announce:
            # Publish the already selected exposure with this exact deadline.
            pending = self.attempt_settlement.pending
            if pending is not None and pending.receipt is None:
                self.teaching_continuation.announce(pending,deadline=self.visual_transport.next_at)
            else:
                self.visual_transport.announce_continuation(target,self.visual_transport.next_at,self._presentation_bpm)
        else:
            self.visual_transport.announced_continuation = None
        self.running = False
        self.recorder = None
        self.count_in_beats = 0.0
        self.measurement.phase_changed("preparation", now)


    def _visual_motion(self, now: float) -> tuple[float, float, float]:
        """Read the one transport projection, including authored tempo and silence."""
        phrase = self.plan.active_phrase
        return self.visual_transport.position(
            now, phrase_length=phrase.end-phrase.start, bpm=self.plan.bpm,
            running=self.running,
            pending_auto_result=(self.pending_result is not None and self.auto),
            tempo_map=self._active_tempo_map())

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            previous_reason = self._action_reason
            self._action_reason = action
            before = {"fingerprint": self.fingerprint,
                      "stage_key": self.plan.identity if self.plan else None,
                      "bpm": self.plan.bpm if self.plan else None, "mode": self.mode}
            previous_command = self.session_commands.active
            route = ControlDispatcher.route(action)
            if self.plan is not None and route in ("listening", "learning", "transport", "stage") and not (action in ("start","restart") and (self._settlement_failed or self._pending_rolling is not None)):
                change = (prepare_stage_change(self.plan, action, kwargs, warmup=self.is_builtin_warmup)
                          if route == "stage" else None)
                self.session_commands.active = self._prepare_teaching("manual", manual=change,
                    action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
            try:
                result = self._dispatch_control(action, **kwargs)
                if action not in ("score_ready", "demo_ready", "reset_path"):
                    self.measurement.event("manual_action", {"action": action,
                        "fingerprint": before["fingerprint"] or None,
                        "parameters": kwargs, "before": before,
                        "after": {"fingerprint": self.fingerprint,
                                  "stage_key": self.plan.identity if self.plan else None,
                                  "bpm": self.plan.bpm if self.plan else None, "mode": self.mode}})
                return result
            finally:
                self.session_commands.active = previous_command
                self._action_reason = previous_reason

    def _dispatch_control(self, action: str, **kwargs) -> None:
        """Single locked command entry; dispatch owns no engine state."""
        with self.lock:
            self._apply_listen_failure()
            route = ControlDispatcher.route(action)
            if route == "calibration":
                return self.midi_calibration_action(action)
            if route == "device_range":
                if action == "midi_range_cancel":
                    self.midi_key_shortcuts.cancel_capture()
                else:
                    if not self.midi.connected:
                        raise ValueError("Connect a MIDI piano before setting its key range")
                    if self.running and not self.visual_transport.paused:
                        self._pause_current_session()
                    self.midi_key_shortcuts.begin_capture(self.midi.device)
                return
            if route == "reset":
                return self._reset_current_path(
                    fingerprint=kwargs.get("fingerprint"),
                    confirm=kwargs.get("confirm") is True)
            if route == "acknowledgement":
                return self._control_acknowledgement(action, kwargs)
            if route == "listening":
                return self._control_listening(action, kwargs)
            if route == "learning":
                return self._control_learning(action, kwargs)
            if route == "transport":
                return self._control_transport(action, kwargs)
            return self._change_stage(action, kwargs)

    def _control_acknowledgement(self, action: str, kwargs: dict) -> None:
        if action == "score_ready":
            revision = int(kwargs.get("revision", -1))
            decision = choose_score_ack_action(revision, ScoreAckState(
                requested_revision=self.awaiting_score_revision,
                current_revision=self.score_revision,
                paused=self.visual_transport.paused, mode=self.mode,
                teaching_bound=self.teaching is not None))
            if decision == "defer":
                self._deferred_score_ack = revision
            elif decision == "listen":
                self.listen.acknowledge_score(revision)
                self._start_listen_if_ready()
            elif decision == "learn":
                self.awaiting_score_revision = None
                self.teaching.start(now=self.now())
            elif decision == "practice":
                # A take starting on a freshly (re-)engraved score: open it on
                # the empty strip one count-in bar ahead, with the snapshot
                # latency allowed, and publish that run_at as its plan.
                lead = (self._next_count_in_beats() * 60.0 / self.plan.bpm
                        + SHORT_REST_LATENCY_SECONDS) if self._short_rest is not None else 0.0
                # A re-engraved continuation still opens after the written
                # rest bar of the take it follows.
                after_rest = self._short_rest_deadline(
                    from_beat=self.open_from_beat) if lead > 0.0 else None
                if after_rest is not None:
                    lead = max(lead, after_rest - self.now())
                self.start(
                    from_beat=(self.visual_transport.pending_rewind if self.visual_transport.pending_rewind is not None
                               else self.open_from_beat),
                    mode="perform" if self.mode == "perform" else "practice",
                    presentation_lead_seconds=lead, decided=True)
                if self._short_rest is not None:
                    self._queue_scheduled_start = (
                        self.transport_id, self.visual_transport.play_from_beat,
                        self.visual_transport.run_at, self.plan.identity,
                        self.score_revision, None)
        elif self.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            # Demo tokens are invalidated by Stop, tempo and navigation.
            self._start_listen_if_ready()

    def _control_listening(self, action: str, kwargs: dict) -> None:
        if action == "listen":
            self._prepare_listen()
        elif action == "perform":
            self._prepare_perform(scope=str(kwargs.get("scope", "current")))
        elif action == "practice_weak":
            self._practice_weak()
        elif action == "review_retry":
            self._review_retry(kwargs.get("first_bar"), kwargs.get("last_bar"))
        elif action == "seek":
            self._seek(kwargs.get("bar"))

    def _control_learning(self, action: str, kwargs: dict) -> None:
        if action == "learn_next":
            if (self.mode != "learn" or self.teaching is None
                    or not self.teaching.snapshot(now=self.now())["completed"]):
                raise ValueError("Find the current notes before continuing to the next idea")
            self._save_guided_preparation()
            if self._guided_return is not None:
                self._prepare_practice()
            else:
                self._begin_course_stage()
        elif action == "skip_stage":
            if self.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs, not skips")
            self._skip_stage(kwargs.get("reason"))
        elif action == "place_original":
            if self.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs")
            self._place_original()
        elif action == "revisit_trouble":
            self._revisit_trouble(kwargs.get("stage_key"), kwargs.get("start_beat"))
        elif action in ("learn", "learn_retry"):
            if action == "learn":
                self.course_guided = True
                if "from_beat" not in kwargs:
                    self._begin_course_stage(explicit_learn=True)
                    return
            previous_start = self.guided_range[0] if self.guided_range else 0.0
            self._begin_learn(
                from_beat=float(kwargs.get(
                    "from_beat",
                    previous_start if action == "learn_retry" else 0.0)),
                recovery=self._guided_return is not None and action == "learn_retry")
        elif action == "open_at":
            self._open_selected_measure(kwargs)
        elif action == "hints":
            self.guided_session.set_hints(
                bool(kwargs.get("enabled", False)), now=self.now())
            if kwargs.get("enabled", False) and self.measurement.attempt_id is not None:
                self.measurement.assistance_used = True

    def _update_short_rest(self, kwargs: dict) -> None:
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
        clear, header = float(clear), float(header)
        if not all(math.isfinite(v) and 0.0 <= v <= 16.0 for v in (clear, header)):
            raise ValueError("Invalid short-rest geometry")
        self._short_rest = (clear, header)

    def _short_rest_deadline(self, take_end: float | None = None, *,
                             from_beat: float = 0.0,
                             now: float | None = None) -> float | None:
        """The graded run_at of the take that follows a written rest bar.

        The next source opens right after the rest bar printed behind the
        last take (take_end, default: the last finished take), but never
        closer than one count-in bar plus the snapshot latency from now,
        so its count-in is always whole. The rest is printed at the tempo
        of the take it follows. The deadline is where Godot admits the ink.
        """
        if self._short_rest is None or self.plan is None or self._presentation_bpm <= 0:
            return None
        clear, header = self._short_rest
        rest_bpm = self._presentation_bpm
        if take_end is None:
            if self._rest_take_end is None:
                return None
            take_end, rest_bpm = self._rest_take_end
        now = self.now() if now is None else now
        _, bar, _ = self.attempt_progression.count_in_bar(
            phrase=self.plan.active_phrase, boundaries=self.plan.piece.bar_boundaries,
            time_signatures=self.plan.piece.time_signatures, position=from_beat)
        span = clear + header
        after_rest = take_end + span * 60.0 / rest_bpm
        epoch = self._tempo_epoch
        if (epoch is not None and take_end < epoch < after_rest
                and abs(self._presentation_bpm - rest_bpm) > 1e-9):
            # Settled during the rest at another tempo: the presentation
            # axis switched rate at that tempo epoch.
            covered = (epoch - take_end) * rest_bpm / 60.0
            after_rest = epoch + (span - covered) * 60.0 / self._presentation_bpm
        return max(after_rest,
                   now + SHORT_REST_LATENCY_SECONDS + bar * 60.0 / self._presentation_bpm)


    def _update_continuous_horizon(self, value) -> None:
        if value is None:
            return
        horizon = float(value)
        if not math.isfinite(horizon) or not 0.0 <= horizon <= 64.0:
            raise ValueError("Invalid continuous score reading horizon")
        self._continuous_horizon_beats = horizon

    def _automatic_stream_deadline(self, deadline: float) -> float:
        # The semantic printed rest is already counted in the engine's
        # automatic next_at. Add only the missing offscreen reading lead
        # before the SAME MIDI-graded run_at is scheduled.
        gap = self.visual_transport.visual_gap_beats
        missing = max(0.0, self._continuous_horizon_beats-gap)
        return scheduled_offscreen_start(deadline, missing, self._presentation_bpm)


    def _presentation_lead(self, kwargs: dict) -> float:
        """Lead to the world position Godot reserved for this command.

        Godot reports the reserved deadline itself (presentation_deadline_ms,
        backend clock). Measuring the lead from it here absorbs the time the
        command spent queued behind engine work, which a relative lead added
        to the engine's own "now" turned into an offset (Clair, 12 px).
        """
        deadline = kwargs.get("presentation_deadline_ms")
        if deadline is not None and math.isfinite(float(deadline)):
            return max(0.0, float(deadline) / 1000.0 - self.now())
        return float(kwargs.get("presentation_lead_seconds", 0.0))

    def _control_transport(self, action: str, kwargs: dict) -> None:
        if action == "practice":
            self._prepare_practice()
            if kwargs.get("wait_for_player", False):
                # Listen returns to a ready score without an auto count-in.
                self.awaiting_score_revision = None
                self.feedback = "Ready to play"
                self.next_action = "Play one piano key to begin, or press Play."
        elif action == "stop":
            self._stop(reason="stop")
            # A stopped session has no take a later rest could follow (M6).
            self._rest_take_end = None
            self.feedback = "Stopped"
            self.next_action = "Start when you are ready."
        elif action in ("start", "restart"):
            self._update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self._update_short_rest(kwargs)
            self._start_or_restart(action, presentation_lead_seconds=self._presentation_lead(kwargs))
        elif action == "pause":
            self._pause_current_session()
        elif action == "resume":
            self._update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self._update_short_rest(kwargs)
            self._resume_current_session(presentation_lead_seconds=self._presentation_lead(kwargs),
                reuse_pending_score=kwargs.get("reuse_pending_score",False) is True,
                reuse_announced_score=kwargs.get("reuse_announced_score",False) is True)

    def _open_selected_measure(self, kwargs: dict):
        effect = self._manual_effect("open_at",values=kwargs)
        self._stop()
        selected = self._install_command(effect)
        self._reset_trouble()
        self.course_guided = selected.mode == "learn"
        self.open_from_beat = selected.from_beat
        if selected.mode == "learn":
            self._begin_learn(from_beat=selected.from_beat,exposure=selected)
        else:
            self._prepare_practice(exposure=selected)
            self.awaiting_score_revision = None
            self.feedback = f"Ready to practise from measure {kwargs.get('bar')}"
            self.next_action = "Press Start to play from the selected measure."

    def _start_or_restart(self, action: str, *,
                          presentation_lead_seconds: float = 0.0):
        """Start a take or schedule a seamless retry under the control lock."""
        if self._settlement_failed:
            revision = self.score_revision
            self.feedback = self._commit_pending() or "Assessment saved"
            if self.score_revision != revision:
                self.awaiting_score_revision = self.score_revision
            self.next_action = "Press Play when the score is ready."
            return
        if self._pending_rolling is not None:
            decision, phrase, grid, score_beat, _old_now = self._pending_rolling
            self._apply_rolling_recovery(decision, phrase, grid, score_beat, self.now())
            self.visual_transport.paused = False
            self.visual_transport.paused_at = 0.0
            return
        p = self.plan
        if p is None:
            raise ValueError("Open a piece first")
        effect = self._manual_effect(action)
        selected = self._install_command(effect)
        route = self.session_commands.start_route(effect,source_changed=(
            self.score_artifacts.source_bpm_changed(p.piece.bpm)
            if self.mode not in ("listen","learn") else False))
        if route == "listen":
            self._prepare_listen()
            return
        if route == "prepare_practice":
            self._prepare_practice()
            return
        if route == "reload_score":
            self._stop()
            self.score_revision += 1
            self.awaiting_score_revision = self.score_revision
            self.feedback = "Preparing sheet music"
            return
        if route == "rewind":
            sampled = self.now()
            visual_now = self.visual_transport.paused_at if self.visual_transport.paused else sampled
            position, _, _ = self._visual_motion(visual_now)
            target = selected.from_beat
            # Validate the complete future musical deadline before
            # interrupting the current graded take or clearing pause state.
            reverse_seconds = self.feedback_seconds
            if presentation_lead_seconds > 0:
                source = self._source_model()
                measures = source["measures"]
                context = max(
                    (index for index, measure in enumerate(measures)
                     if float(measure["start_beat"]) <= target + 1e-7),
                    default=0)
                rest_beats = float(
                    source["practice_timeline"]["gap"]["duration_beats"])
                # Source-metre preparation may be a different length from
                # the general repeat gap (e.g., a changing time signature).
                if 0 <= context < len(measures):
                    from .notation.practice_timeline import preparation_measure_descriptor
                    selected = measures[context]
                    following = measures[context + 1] if context+1 < len(measures) else None
                    rest_beats = float(preparation_measure_descriptor(
                        selected, 0.0, source["staff_order"],
                        following_measure=following)["duration_beats"])
                reverse_seconds = planned_retry_reverse_seconds(
                    reading_lead_seconds=presentation_lead_seconds,
                    semantic_rest_seconds=rest_beats * 60.0 / self.plan.bpm)
            self.measurement.interrupt("restart", self.recorder.presses if self.recorder else ())
            self.visual_transport.paused = False
            self.visual_transport.paused_at = 0.0
            self.pause_context = None
            self._deferred_score_ack = None
            self.awaiting_score_revision = None
            self.pending_result = None
            self.attempt_settlement.cancel(reason="restart", now=sampled)
            self.teaching_continuation.cancel()
            self._pending_assessed_bpm = None
            self.visual_transport._retry_previous_pass = False
            self._guided_recovery_pending = False
            self.midi_ingress.resume_grading_after = 0.0
            self.midi_ingress.resume_ignored_pitches.clear()
            self._pause_floor = None
            self._schedule_preparation(target, now=sampled, from_visual=position,
                                       reverse_seconds=reverse_seconds,
                                       reading_lead_included=presentation_lead_seconds > 0)
            self.feedback = "Get ready to retry"
            return
        self.start(mode=selected.mode,from_beat=selected.from_beat,decided=True,
                   presentation_lead_seconds=presentation_lead_seconds)
        return

    def _musical_seconds(self, at: float) -> float:
        """Graded musical time of wall instant ``at``, in seconds since run_at.

        The one clock the Recorder and the live input view share (R1 F2).
        It stands still from the Pause moment until grading resumes after
        Resume's lead (Resume moves run_at by the paused time plus that
        lead): a key held across the pause excludes the paused interval, and
        a key-up while paused or in the lead counts at the pause moment.
        """
        seconds = at - self.visual_transport.run_at
        floor = self._pause_floor
        if floor is None:
            return seconds
        if self.visual_transport.paused:
            return min(seconds, floor)
        if at < self.midi_ingress.resume_grading_after:
            return max(seconds, floor)
        return seconds

    def _pause_current_session(self):
        """Pause learning, playback or preparation using one sampled clock."""
        now = self.now()
        context = self._phase(now) if not self.visual_transport.paused else ""
        require_pausable(paused=self.visual_transport.paused, phase=context)
        self.pause_context = context
        if self.running:
            # A second Pause inside the resume lead keeps the first pause
            # moment: the graded timeline has not moved since.
            self._pause_floor = self._musical_seconds(now)
        self.visual_transport.pause(at=now)
        self.measurement.phase_changed("pause", now)
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.pause(now=now)
        return

    def _resume_current_session(self, *, presentation_lead_seconds: float = 0.0,
                                reuse_pending_score: bool = False,
                                reuse_announced_score: bool = False):
        """Resume grading after future-only visual notes have reading space."""
        learning = self.mode == "learn" and self.teaching is not None
        shift_run_at = resume_timeline(
            paused=self.visual_transport.paused, learning=learning, running=self.running,
            preview_pending=self.visual_transport._preview_loop_pending,
            automatic_feedback=self.pending_result is not None and self.auto)
        now = self.now()
        paused_at = self.visual_transport.paused_at
        if reuse_pending_score and (
                presentation_lead_seconds <= 0.0 or
                not (shift_run_at and self.running and
                     self.mode in ("practice", "perform")) or
                self.pause_context != "count_in" or
                self.visual_transport.run_at <= paused_at):
            # Reuse is permitted only for a count-in that never reached the
            # first attack. Reject before mutable transport.resume(): an
            # invalid command must preserve the paused take unchanged.
            raise ValueError("Cannot reuse a passage after graded notes began")
        previous_origin = self.visual_transport.run_at
        had_reading_lead = self.midi_ingress.resume_grading_after > paused_at
        if learning:
            self.teaching.resume(now=now)
        self.visual_transport.resume(now=now, shift_run_at=shift_run_at)
        if had_reading_lead:
            self.midi_ingress.resume_grading_after += max(0.0, now-paused_at)
        self._reannounce_after_rest_pause(now, presentation_lead_seconds,
                                          reuse=reuse_announced_score)
        pending = self.attempt_settlement.pending
        if pending is not None and self.teaching_continuation.schedule is not None and self.visual_transport.announced_continuation is not None:
            self.teaching_continuation.announce(pending,deadline=self.visual_transport.announced_continuation[1])
        # A paused passage returns with a short genuine count-in. Its
        # authoritative run_at moves, so MIDI grading and source ink agree
        # and no note is required during the visual reading lead-in.
        if (shift_run_at and self.running and self.plan is not None
                and self.mode in ("practice", "perform")
                and self.pause_context in ("playing", "count_in")):
            if presentation_lead_seconds > 0.0:
                # With an original source copy still ahead of the playhead,
                # never double-add a full reading lead to the old count-in.
                # Restore the graded downbeat to that exact unchanged future
                # world position. Earlier graded keys cannot exist yet.
                # The count-in is the one bar before grading resumes; a
                # longer reading lead before it is silent (owner decision
                # 2026-11-08). It never grows with the presentation lead.
                count_in = self._next_count_in_beats()
                if reuse_pending_score:
                    self.visual_transport.run_at = now + presentation_lead_seconds
                    self.midi_ingress.resume_grading_after = self.visual_transport.run_at
                else:
                    # The renderer reserves at least the published count-in
                    # (next_count_in_beats); its lead is the score deadline.
                    lead_seconds = max(count_in*60.0/self.plan.bpm,
                        presentation_lead_seconds)
                    already_waiting = max(0.0,self.midi_ingress.resume_grading_after-now)
                    additional = max(0.0,lead_seconds-already_waiting)
                    if additional > 0:
                        self.visual_transport.run_at += additional
                    self.midi_ingress.resume_grading_after = now + max(
                        lead_seconds,already_waiting)
                self.count_in_beats = count_in
            elif (self.midi.connected and not self.preview_only
                  and self.pause_context == "playing"
                  and not had_reading_lead
                  and self.visual_transport.run_at <= now):
                # Preserve the established direct-MIDI transport contract;
                # it does not have a connected renderer's reservations.
                lead_beats = max(1.0,min(4.0,self.count_in_bar_beats))
                lead_seconds = lead_beats*60.0/self.plan.bpm
                self.visual_transport.run_at += lead_seconds
                self.midi_ingress.resume_grading_after = now+lead_seconds
                self.count_in_beats = lead_beats
        self.measurement.event("timeline_resume", {
            "scheduled_origin_before": previous_origin-self.measurement.origin,
            "scheduled_origin_after": self.visual_transport.run_at-self.measurement.origin,
            "shift_run_at": shift_run_at})
        resumed_count_in = self.running and (
            now < self.visual_transport.run_at or now < self.midi_ingress.resume_grading_after)
        self.measurement.phase_changed("guided" if learning else
            "count_in" if resumed_count_in else "active", now)
        self.pause_context = None
        if self.running:
            self.feedback = "Count in" if resumed_count_in else "Playing"
        if self._deferred_score_ack is not None:
            revision = self._deferred_score_ack
            self._deferred_score_ack = None
            self.control("score_ready", revision=revision)
        self._start_listen_if_ready()
        return

    def _change_stage(self, action: str, kwargs: dict):
        """Change the active lesson or tempo while preserving scoring state."""
        p=self.plan
        if not p:
            raise ValueError("Open a piece first")
        change = prepare_stage_change(
            p, action, kwargs, warmup=self.is_builtin_warmup)
        was_guided = self.mode == "learn"
        guided_start = self.guided_range[0] if self.guided_range is not None else 0.0
        guided_return = self._guided_return
        guided_retry_range = self.retry_range
        self._stop()
        self._reset_trouble()
        # Preserve the original ordering of the source opening reset.
        if action in ("select_step", "next", "previous"):
            self.open_from_beat = 0.0
        effect = self.session_commands.active or self._prepare_teaching("manual", manual=change, action=action, store=False)
        self.session_commands.apply_progress(effect, plan=p)
        self.attempt_settlement.authority_revision += 1
        if action == "hand":
            self.open_from_beat = 0.0
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if not change.tempo_only:
            self.score_revision+=1
        self.feedback="Ready"
        self.next_action="Start when you are ready."
        if was_guided:
            selected = effect.decision.next_exposure
            if selected is not None and selected.mode == "learn":
                recovery = change.tempo_only and guided_return is not None and guided_return[0] == p.identity
                if recovery:
                    self.retry_range = guided_retry_range
                self._begin_learn(from_beat=selected.from_beat,bump_revision=False,recovery=recovery,exposure=selected)
            elif selected is not None:
                self._enter_selected_exposure(selected)
        self._save()

    def _poll_midi_connection(self):
        if self.midi.closed:
            self._midi_lost()
        if self.midi.scan_due(self.library.settings.get("midi_device", "")):
            try:
                self.ports()
            except RuntimeError:
                # Keep actionable device feedback without failing /state.
                pass

    def _decided_stage_selection(self):
        if not self.auto:
            return None
        return self.teaching_continuation.selection(self.attempt_settlement.pending,
            revision=self.score_revision,fingerprint=self.fingerprint)

    def _advance_pending_feedback(self, now: float, *, prepared_on_time: bool = False):
        """Commit finished feedback and schedule exactly one next transition."""
        if self.pending_result is not None and (self.attempt_settlement.pending is None
                or self.attempt_settlement.pending.assessment is not self.pending_result):
            self._prepare_teaching("full_result", self.pending_result)
        if self.auto and self.visual_transport.next_at and now >= self.visual_transport.next_at:
            readiness = ContinuationReadiness(self._future_stage_ready,self.score_revision,
                self.fingerprint,self._visual_motion(now)[0],self.plan.bpm,
                self._native_preload_failure,prepared_on_time)
            effect = self.teaching_continuation.advance(self.attempt_settlement.pending,now=now,readiness=readiness)
            if effect.action == "fault":
                self.feedback = "Cannot prepare the next lesson score"
                self.next_action = f"{effect.message}. Select another step or reopen the piece."
                return
            if effect.action == "await":
                if effect.message:
                    self.feedback = effect.message
                return
            deadline = self.visual_transport.next_at
            previous_revision = self.score_revision
            previous_identity = self.plan.identity
            try:
                message = self._commit_pending()
                # Settlement may step the tempo or change the stage now.
                self._note_tempo(now)
            except UnpreparedNextStage as exc:
                # The transaction rolled back to the score still on screen.
                # Never reset the camera or ask Godot to load the wrong step.
                self.visual_transport.pause(at=now)
                self.visual_transport.next_at = 0.0
                self.feedback = "The next lesson score changed during grading"
                self.next_action = (
                    f"{exc}. Select another step or reopen the piece.")
                return
            except Exception as exc:
                # A transient disk/generator failure cannot settle partial
                # evidence or repeatedly retry the same transaction at 20ms.
                # The pending graded attempt remains available for inspection.
                self.auto = False
                self.visual_transport.next_at = 0.0
                self.feedback = "Could not save the assessment"
                self.next_action = (
                    "Check storage or lesson generation, then Retry the attempt.")
                print("ASSESSMENT_SETTLEMENT_FAILED:",
                      type(exc).__name__, str(exc), flush=True)
                return
            self.feedback_marks=[]
            self.feedback_unmapped=0
            assignment = self._remediation_pending
            self._remediation_pending = None
            selected = self.attempt_settlement.pending.decision
            effect = self.teaching_continuation.after_settlement(selected,
                score_changed=self.score_revision != previous_revision,
                prepared=self._prepared_stage_published and self._future_stage_ready == (self.plan.identity,self.score_revision))
            route = effect.action
            if route == "handoff":
                self._future_stage_ready = None
                self._prepared_stage_published = False
                start = self.teaching_continuation.handoff(now=now,deadline=deadline,
                    lead_beats=self._future_stage_lead_beats,clear_beats=self._future_stage_clear_beats,
                    count_in_beats=self._next_count_in_beats(),bpm=self.plan.bpm,
                    rest_take_end=self._rest_take_end,latency=SHORT_REST_LATENCY_SECONDS)
                self._future_stage_lead_beats = 0.
                self._future_stage_clear_beats = None
                if self._future_stage_short_rest is not None:
                    self._short_rest = self._future_stage_short_rest
                    self._future_stage_short_rest = None
                self._continue_at(start.deadline,from_beat=selected.next_exposure.from_beat)
                self.count_in_beats = start.count_in
                return
            self._prepared_stage_published = False
            # The selected teaching exposure has precedence over a timed
            # policy reply. A prepared untimed Learn step must never be
            # redirected to timed Practice just because feedback also carries
            # a response. Preserve actual remediation/recovery ownership.
            if route == "guided":
                if assignment is not None:
                    self._start_remedial_assignment(
                        assignment, deadline=deadline, exposure=selected.next_exposure)
                elif selected.response is not None and selected.response.guided:
                    self._apply_policy_response(selected.response, now=now, deadline=deadline)
                else:
                    self._enter_selected_exposure(selected.next_exposure)
                return
            if route == "response" and selected.response is not None and \
                    selected.next_exposure is not None and self.auto:
                self._apply_policy_response(selected.response, now=now, deadline=deadline)
                return
            if route == "remediation":
                self._start_remedial_assignment(assignment,deadline=deadline, exposure=selected.next_exposure)
                return
            if route == "await_score":
                self.awaiting_score_revision = self.score_revision
                self.auto = False
                self.feedback = "Preparing next passage"
                self.visual_transport.next_at = 0
                self.visual_transport.announced_continuation = None
            elif route == "continue":
                # Failed attempts reuse the existing source; clean attempts
                # append another passage with the exact authored rest gap.
                if not self.visual_transport._retry_previous_pass:
                    self.visual_transport.visual_offset_beats += self._source_model()[
                        "practice_timeline"]["stride_beats"]
                target = selected.next_exposure.from_beat
                # The deadline already announced for this repeat, unchanged.
                self._continue_at(self._continuation_deadline(deadline, target),
                                  from_beat=target)
            else:
                self.visual_transport.next_at = 0
                self.visual_transport.announced_continuation = None
                self.auto = False
                self.feedback = message or self.feedback
        return

    def _start_remedial_assignment(self, assignment: RemedialAssignment,
                                   *, deadline: float | None = None, exposure=None) -> None:
        """Present an automatic remedial range without ever waiting for a key.

        A manually chosen guided lesson keeps the existing note-finding flow.
        An automatic rhythmic session always gets a scored, meter-bounded
        section that returns to the full passage after its recovery rest.
        """
        if self.plan is None or assignment.stage_key != self.plan.identity:
            return
        automatic = deadline is not None and self.auto and (exposure is None or exposure.mode == "practice")
        if exposure is not None:
            assignment = replace(assignment,start_beat=exposure.from_beat,
                end_beat=exposure.end_beat if exposure.end_beat is not None else self.plan.active_phrase.end-self.plan.active_phrase.start)
        # Validate the authored source grid before mutating any clock.
        review = (None if assignment.guided and not automatic else
                  plan_timed_remedial_review(
                      assignment,self.plan.active_phrase,self.plan.piece.bar_boundaries))
        if automatic:
            self.open_from_beat = review.start_beat
            full_end = self.plan.active_phrase.end-self.plan.active_phrase.start
            self._automatic_remedial_review = (
                review.start_beat > 1e-7 or review.end_beat < full_end-1e-7)
            self.review_end_beat = (review.end_beat if
                review.end_beat < full_end-1e-7 else None)
            self.retry_range = review.retry_range
            self.feedback = f"Retrying {assignment.focus} with the music still moving"
            self.next_action = "Play this section, then return to the complete passage."
            self._continue_at(
                self._continuation_deadline(deadline, review.start_beat),
                from_beat=review.start_beat)
            return
        if assignment.guided:
            self._begin_learn(
                from_beat=assignment.start_beat, recovery=True,
                remediation=assignment, exposure=exposure)
            self.feedback = "Reviewing recurring pitch mistakes"
        else:
            self._prepare_practice(exposure=exposure)
            self.open_from_beat = review.start_beat
            self.review_end_beat = review.end_beat
            self.retry_range = review.retry_range
            self.awaiting_score_revision = None
            self.feedback = f"Focused {assignment.focus} practice ready"
            self.next_action = (
                "Press Start to practise these measures. "
                "This partial retry cannot award mastery.")

    def _apply_rolling_recovery(self, decision, phrase: Phrase, grid, score_beat: float, now: float):
        """Apply an accepted source-grid recovery decision atomically."""
        # Capture marks at the performance tempo, not at the slower
        # BPM selected for the next retry. Re-scaling the recorded
        # timestamps early would move mistakes to incorrect notes.
        self.feedback_marks=self._live_feedback((now-self.visual_transport.run_at))
        self.live_assessment.publish(self.feedback_marks, self._feedback_take())
        pending = self.attempt_settlement.pending
        if self._pending_rolling is None or pending is None:
            tempo_map = self._active_tempo_map()
            assessed = self.assessment_policies.select(tempo_map).grade(
                phrase, hand=self.plan.hand, bpm=self.plan.bpm,
                played=self.recorder.presses if self.recorder else [],
                from_beat=self.visual_transport.play_from_beat, end_beat=decision.end_beat,
                tempo=tempo_map)
            pending = self._prepare_teaching("rolling_result", assessed, rolling=decision, end_beat=decision.end_beat)
        assessed = pending.assessment
        response = pending.decision.response
        if response.action == "continue":
            from .measure_grid import next_chunk_end
            following = next_chunk_end(grid, decision.end_beat)
            self.next_boundary_beat = following if following > decision.end_beat+1e-7 else 0.
            self.attempt_settlement.pending = None
            return
        from .application.rolling_recovery import project_rolling_response
        transition = project_rolling_response(response,decision,grid=grid,
            first_bar=phrase.first_bar,before_bpm=pending.state.route.performed_bpm,now=now)
        self.measurement.seal(self.recorder.presses if self.recorder else (),
            state="interrupted", reason="rolling_recovery", result=assessed,
            extra={"assessed_end_beat": decision.end_beat})
        try:
            self.attempt_settlement.settle(pending, plan=self.plan,
                binding=self._teaching_binding(), now=now,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]))
        except Exception:
            self._pending_rolling = (decision, phrase, grid, score_beat, now)
            self.running = self.auto = False
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=now)
            self.feedback = "Could not save the retry evidence"
            self.next_action = "Check storage, then press Retry to save this same attempt."
            raise
        self._pending_rolling = None
        self.measurement.finish()
        self._note_tempo(now)
        self._schedule_preparation(transition.restart_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds)
        self._trouble_key = transition.trouble_key
        self._trouble_count = transition.trouble_count
        self._guided_recovery_pending = transition.guided
        if transition.guided:
            # The next step is note-by-note learning, not a timed take.
            self.visual_transport.announced_continuation = None
        self.recovery_notice = transition.display.notice
        self.retry_range = transition.display.retry_range
        self.feedback = transition.display.feedback
        self.next_action = transition.display.next_action
        if transition.action != "repair":
            self.next_action = transition.reason
        if transition.action == "pause":
            self.auto = False
            self.visual_transport.cancel_preparation()
            self.visual_transport.next_at = 0.
            self.feedback = "Practice paused · " + transition.reason
        return

    def _complete_attempt(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> None:
        """Apply post-performance state after the score's settlement interval.

        This method is called from the locked _update loop. Assessment and
        grading are calculated only after a completed non-preview take.
        """
        self._rest_take_end = (self.visual_transport.run_at + duration, self.plan.bpm)
        if self.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.measurement.seal((), state="completed", reason="preview")
            with self.measurement.atomic():
                self.measurement.persist()
            self.measurement.finish()
            self.running = False
            self.visual_transport._preview_loop_pending = True
            short = self._short_rest_deadline(self.visual_transport.run_at + duration)
            self.visual_transport.announce_continuation(0.0, short if short is not None else
                self._automatic_stream_deadline(repeat_deadline(
                    run_at=self.visual_transport.run_at, duration=duration,
                    gap_beats=self.visual_transport.visual_gap_beats,
                    bpm=self.plan.bpm)), self.plan.bpm)
            self.feedback = "Timing preview - repeating after one empty measure"
            self.next_action = "Connect your MIDI piano to earn progress."
            if now >= self.visual_transport.next_at:
                self._update()
            return
        tempo_map = self._active_tempo_map()
        # Grading/projection uses explicit assessment inputs. The engine
        # still owns take settlement and every subsequent state mutation.
        assessed = assess_completed_take(
            phrase=phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.visual_transport.play_from_beat, end_beat=ending,
            tempo=tempo_map, policies=self.assessment_policies,
            layout_for_feedback=self._layout_for_completed_take)
        result = assessed.result
        route = completion_route(self.mode, self.review_end_beat, self.visual_transport.play_from_beat)
        if self._automatic_remedial_review and route == "section_review":
            route = "partial_recovery"
        self.measurement.seal(self.recorder.presses if self.recorder else (),
            state="completed", reason=route, result=result,
            eligible=(route == "full_passage" and self.mode == "practice"
                      and self.plan.bpm >= self.plan.target_bpm),
            extra={"assessed_end_beat": ending})
        summary = self._performance_review(phrase, result)
        completed_visual = self._visual_motion(now)[0]
        response = None
        if route != "full_passage":
            pending = self._prepare_teaching("focused_result", result, end_beat=ending)
            response = pending.decision.response
            self.attempt_settlement.settle(pending, plan=self.plan,
                binding=self._teaching_binding(), now=now,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]),
                performance_summary=summary if route == "perform" else None)
            self._note_tempo(now)
        self.feedback_marks = assessed.marks
        self.feedback_unmapped = assessed.unmapped
        # The completed take's settled grades, before any transition below can
        # start another transport.
        self.live_assessment.publish(self.feedback_marks, self._feedback_take(),
                                     final=True)
        self.feedback = assessed.feedback
        self.running=False
        self.recorder=None
        self.performance_summary = summary
        self.review_stage_identity = self.plan.identity
        self.measurement.phase_changed("feedback", now)
        if response is not None:
            self._apply_policy_response(response, now=now, visual_from=completed_visual)
            return
        if route == "perform":
            self._finish_performance_review(phrase, result)
        elif route == "section_review":
            self._finish_section_review(result)
        elif route == "partial_recovery":
            if pending.decision.continuation in ("stop","pause"):
                self.auto = False
                self.visual_transport.cancel_preparation()
                self.visual_transport.next_at = 0.
                self.next_action = "Review this section before starting another take."
            elif pending.decision.next_exposure.mode == "learn":
                self._enter_selected_exposure(pending.decision.next_exposure)
            else:
                self._finish_partial_recovery(result, now, exposure=pending.decision.next_exposure)
        else:
            self._finish_full_passage(result, total_beats, duration, now)


    def _finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.next_action = ("Review your performance, then press Start to repeat this warm-up."
            if self.is_builtin_warmup else
            "Review your performance, then Practice the weakest section."
            if self.performance_summary["weakest_bars"] else
            "Clean performance. Choose Practice to build your clean-run streak.")
        self.auto = False

    def _finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.auto = False
        self.review_end_beat = None
        self.review_session_complete = True
        self.visual_transport.pending_rewind = None
        self.retry_range = None
        self.open_from_beat = 0.0
        self.feedback = "Section review finished · " + result.summary
        self.next_action = "Review the notes or press Start for the whole passage."

    def _finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.review_end_beat = None
        self._automatic_remedial_review = False
        self.open_from_beat = exposure.from_beat if exposure is not None else 0.0
        self._schedule_preparation(self.open_from_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + self.visual_transport.play_from_beat
                + self._elapsed_beat(now-self.visual_transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.feedback = "Selected section finished · " + result.summary
        self.next_action = "Next: play the whole passage from its beginning to earn mastery."
        self.retry_range = None

    @staticmethod
    def _teaching_instruction(pending):
        decision,state = pending.decision,pending.state
        if decision.progress_after.cursor == state.progress.cursor:
            return "passage mastered" if decision.message == "Piece mastered" else "play the passage again"
        chosen = replace(state.course,definition=decision.definition_after,progress=decision.progress_after)
        if chosen.progress.cursor[0] != state.progress.cursor[0]:
            return "now learn the next passage"
        if chosen.hand != state.course.hand:
            return "now play both hands together" if chosen.hand == "both" else f"now learn the {chosen.hand} hand"
        notes = chosen.stage.variant.notes
        if any(sum(abs(other.start-note.start)<1e-6 for other in notes)>1 for note in notes):
            return "now restore missing chord notes"
        return "now play all the notes" if chosen.stage.variant.level == "original" else "now add more melody notes"

    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        self.pending_result = result
        self._pending_assessed_bpm = self.plan.bpm
        pending = self._prepare_teaching("full_result", result)
        decision = pending.decision
        exposure = decision.next_exposure
        response = decision.response
        if self.measurement.attempt_id is not None and self.measurement.sealed is None:
            self.measurement.seal(self.recorder.presses if self.recorder else (),state="completed",
                reason="full_passage",result=result,eligible=decision.mastery_eligible)
        self.attempt_settlement.checkpoint_failed_streak(pending, plan=self.plan, now=now)
        same_timed = (exposure is not None and exposure.stage_key == self.plan.identity
                      and exposure.mode == "practice" and decision.remediation is None)
        rewind = decision.invalidate_failed_streak and self.auto
        if rewind:
            visual_from = self._visual_motion(now)[0]
            self._note_tempo(now)
            self.visual_transport._retry_previous_pass = True
            target = exposure.from_beat if exposure else self.visual_transport.play_from_beat
            self._schedule_preparation(target, now=now, from_visual=visual_from,
                reverse_seconds=max(self.feedback_seconds, min(4., total_beats*60./self.plan.bpm/3.)),
                announce=same_timed,
                short_deadline=self._short_rest_deadline(None, from_beat=target))
        if self.is_builtin_warmup and decision.invalidate_failed_streak:
            self.auto = False
            self.visual_transport.cancel_preparation()
            self.visual_transport.next_at = 0
        if result.passed:
            label = "Clean" if result.clean else "Accepted"
            self.next_action = (f"{label} passage — restore tempo to {decision.progress_after.bpm} BPM toward {self.plan.target_bpm} BPM."
                if pending.state.progress.bpm < pending.state.progress.target_bpm else
                f"{label} pass {pending.state.progress.streak+1}/{SETTINGS.clean_runs_to_master} — {self._teaching_instruction(pending)}.")
        else:
            self.next_action = "Retry the whole passage (red errors or at least half the attacks yellow)."
        if response is not None and response.restart_beat > self.visual_transport.play_from_beat+1e-7:
            self.next_action = "Repeat the difficult measure at %d BPM, then play the whole passage." % response.bpm
        elif response is not None and response.bpm < self._pending_assessed_bpm:
            self.next_action = "Retry more slowly at %d BPM." % response.bpm
        planned = self._decided_stage_selection()
        if planned is not None:
            selection, _number = planned
            if self._future_stage_ready == (selection.stage_key, selection.revision) and self.future_score.ready(selection):
                self.visual_transport.next_at = now
                self._advance_pending_feedback(now, prepared_on_time=True)
                return
        if not self.auto:
            self.visual_transport.next_at = 0
        elif not self.visual_transport._retry_previous_pass:
            deadline = repeat_deadline(run_at=self.visual_transport.run_at, duration=duration,
                gap_beats=self.visual_transport.visual_gap_beats, bpm=self.plan.bpm)
            if same_timed:
                short = self._short_rest_deadline(self.visual_transport.run_at+duration)
                self.teaching_continuation.announce(pending,
                    deadline=short if short is not None else self._automatic_stream_deadline(deadline))
            else:
                self.visual_transport.announced_continuation = None
                self.visual_transport.next_at = now if self._short_rest is not None else deadline
            if now >= self.visual_transport.next_at:
                self._update()

    def _assess_rolling_boundary(self, boundary: float,
                                 grid: tuple[float, ...]):
        """Grade one authored boundary under the existing session lock."""
        try:
            self.measurement.checkpoint(self.recorder.presses if self.recorder else (), boundary=boundary)
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=self.now())
            self.feedback = "Could not save the recording checkpoint"
            self.next_action = "Check storage, then Resume to retry this boundary."
            raise
        if not resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]).interrupt_rolling:
            return None
        tempo_map = self._active_tempo_map()
        return self.assessment_policies.select(tempo_map).recover(
            self.plan.active_phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.visual_transport.play_from_beat, end_beat=boundary, grid=grid,
            threshold=(SETTINGS.warmup_recovery_errors
                       if self.is_builtin_warmup
                       else SETTINGS.recovery_errors_in_window),
            warmup=self.is_builtin_warmup, tempo=tempo_map)

    def _run_pre_assessment_transition(self, now: float) -> bool:
        """Apply an explicit non-grading transition under the session lock."""
        context = TransitionContext(
            has_plan=self.plan is not None,
            learning=self.mode == "learn" and self.teaching is not None,
            paused=self.visual_transport.paused, listening=self.mode == "listen",
            preview_pending=self.visual_transport._preview_loop_pending,
            preparation_pending=self.visual_transport._preparation_pending,
            feedback_pending=self.pending_result is not None,
            awaiting_score=self.awaiting_score_revision is not None,
            rewind_pending=self.visual_transport.pending_rewind is not None,
            running=self.running, run_at=self.visual_transport.run_at)
        decision = decide_transition(
            context, now=now, next_at=self.visual_transport.next_at,
            preparation_at=self.visual_transport._preparation_at)
        if decision.preparation_phase is not None:
            self.visual_transport.practice_preparation["phase"] = decision.preparation_phase
        if decision.action == "learning":
            self.guided_session.advance(connected=self.midi.connected, now=now)
            self._save_guided_preparation()
        elif decision.action == "listening":
            if self.running and self.listen.finished(now=now, run_at=self.visual_transport.run_at):
                self.running = False
                self.feedback = "Example complete"
                self.next_action = (
                    "Choose Learn to find the notes, or Practice to play the rhythm.")
        elif decision.action == "preview_due":
            deadline = self.visual_transport.next_at
            self.visual_transport.visual_offset_beats += self._source_model()[
                "practice_timeline"]["stride_beats"]
            self._continue_at(self._continuation_deadline(deadline, 0.0))
        elif decision.action == "feedback":
            self._advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self._guided_recovery_pending:
                self._begin_learn(from_beat=self.visual_transport.pending_rewind, recovery=True,
                    exposure=self.attempt_settlement.pending.decision.next_exposure)
            else:
                target = self.visual_transport.pending_rewind
                self._continue_at(
                    self._continuation_deadline(self.visual_transport.next_at, target),
                    from_beat=target)
        return decision.consumed

    def _update(self) -> None:
        try:
            self._update_transition()
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=self.now())
            self.feedback = "Could not save or finish the practice transition"
            self.next_action = "Check storage or the reported error, then Resume to retry this same take."
            raise
        # Display publication must never pause the take or alter feedback text.
        try:
            self._publish_live_assessment()
        except Exception:
            logging.getLogger(__name__).exception(
                "Live assessment publication failed; skipping this tick")

    def _update_transition(self) -> None:
        """Advance the backend clock under its existing session lock."""
        self._poll_midi_connection()
        self._apply_listen_failure()
        now = self.now()
        if self.visual_transport.paused:
            self.measurement.phase_changed("pause", now)
        elif self.mode == "learn":
            self.measurement.phase_changed("preparation" if self.awaiting_score_revision else
                "feedback" if self.teaching is not None and self.teaching.snapshot(now=now)["completed"] else "guided", now)
        elif self.running:
            # Split a count-in at its musical deadline even when polling is late.
            if self.measurement.phase == "count_in" and now >= self.visual_transport.run_at:
                self.measurement.phase_changed("active", self.visual_transport.run_at)
            else:
                self.measurement.phase_changed("count_in" if now < self.visual_transport.run_at else
                    "listen" if self.mode == "listen" else "preview" if self.preview_only else "active", now)
        elif self.pending_result is not None:
            self.measurement.phase_changed("feedback", now)
        elif self.visual_transport._preparation_pending or self.awaiting_score_revision is not None:
            self.measurement.phase_changed("preparation", now)
        else:
            self.measurement.phase_changed("feedback" if self.performance_summary is not None else "idle", now)
        if self._run_pre_assessment_transition(now):
            return
        phrase = self.plan.active_phrase
        score_beat = self.visual_transport.play_from_beat + max(
            0.0, self._elapsed_beat(now-self.visual_transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.visual_transport.play_from_beat,
            run_at=self.visual_transport.run_at, next_boundary=self.next_boundary_beat,
            review_end=self.review_end_beat, preview=self.preview_only,
            auto=self.auto, mode=self.mode,
            bpm=self.plan.bpm, gap_beats=self.visual_transport.visual_gap_beats),
            self._assess_rolling_boundary, self._elapsed_seconds)
        self.next_boundary_beat = step.next_boundary
        if step.action == "recovery":
            self._apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            self._complete_attempt(phrase, step.ending,
                                   phrase.end-phrase.start, step.duration, now)
            self._refloor_fresh_announcement()

    def _refloor_fresh_announcement(self) -> None:
        """Keep a just-made announcement one count-in bar ahead of the reply.

        A take's completion (grading, evidence, persistence) can take most
        of a second under the lock on large pieces (Chopin), and Godot only
        sees the announcement in the reply after it. A deadline floored at
        the START of that work then began its count-in before Godot knew of
        it (first syllable 0.3 s late). Godot has not seen it yet, so it is
        re-timed (same identity) to at least now + latency + one bar.
        """
        announced = self.visual_transport.announced_continuation
        if (announced is None or self.running or self.plan is None
                or self._short_rest is None or self.plan.bpm <= 0):
            return
        _, bar, _ = self.attempt_progression.count_in_bar(
            phrase=self.plan.active_phrase, boundaries=self.plan.piece.bar_boundaries,
            time_signatures=self.plan.piece.time_signatures, position=announced[0])
        floor = self.now() + SHORT_REST_LATENCY_SECONDS + bar * 60.0 / self.plan.bpm
        if announced[1] < floor:
            self.visual_transport.retime_announcement(floor)

    def _phase(self, now: float) -> str:
        teaching_phase = None
        if not self.visual_transport.paused and self.mode == "learn" and self.teaching is not None:
            teaching_phase = ("loading" if self.awaiting_score_revision is not None
                              else self.teaching.snapshot(now=now)["phase"])
        if (self.running and not self.visual_transport.paused
                and now < self.midi_ingress.resume_grading_after):
            return "count_in"
        return project_phase(PhaseSnapshot(
            paused=self.visual_transport.paused, running=self.running, run_at=self.visual_transport.run_at,
            teaching_phase=teaching_phase,
            performance_complete=self.performance_summary is not None,
            preview_loop_pending=self.visual_transport._preview_loop_pending,
            review_complete=self.review_session_complete,
            pending_result=self.pending_result is not None,
            awaiting_score=self.awaiting_score_revision is not None,
            pending_rewind=self.visual_transport.pending_rewind is not None,
        ), mode=self.mode, now=now)

    def _layout_for_completed_take(self) -> dict:
        """Ink for the settled take: the layout the learner just played from.

        The displayed score was engraved before the take started, so this is
        the published cached layout. Engraving inside the clock tick happens
        only if that invariant was broken, and is logged.
        """
        selection = self._score_selection()
        cached = self.score_artifacts.cached_layout(selection)
        if cached is not None:
            return cached.layout
        print("COMPLETED_TAKE_LAYOUT_COLD: engraving inside the clock tick", flush=True)
        return self.score_artifacts.engraving(selection).layout

    def _open_take(self, *, phrase: Phrase | None = None,
                   recording: bool = False) -> int:
        """Begin a new transport epoch: the ONE place take-scoped state resets.

        Practice, guided learning and Listen all open takes here, so a new
        transport ID never coexists with the previous take's recorder, live
        MIDI matches, settlement or feedback marks.
        """
        self.attempt_settlement.cancel(reason="new_exposure",now=self.now())
        self.teaching_continuation.cancel()
        self.transport_id += 1
        self.live_input.reset_attempt()
        self._pause_floor = None
        if phrase is not None:
            self.live_input.prepare(phrase)
        self.recorder = Recorder() if recording else None
        self.pending_result = None
        self._pending_assessed_bpm = None
        self.feedback_marks = []
        self.feedback_unmapped = 0
        self.live_assessment.clear()
        return self.transport_id

    def _feedback_take(self) -> dict:
        """Immutable identity of the take that the next feedback belongs to."""
        return {"piece_fingerprint": self.fingerprint or "",
                "revision": int(self.score_revision),
                "transport_id": int(self.transport_id), "mode": self.mode,
                "graded": (not self.preview_only
                           and self.mode in ("practice", "perform"))}

    def _publish_live_assessment(self) -> None:
        """Publish the incremental assessment continuously during playback.

        Uses the same _live_feedback grading call as every other consumer;
        only new or changed per-note results enter the feedback event log.
        """
        if (not self.running or self.preview_only
                or self.mode not in ("practice", "perform")):
            # No running graded take: never carry the previous take's marks.
            self.live_assessment.clear()
            return
        if self.visual_transport.paused:
            return
        elapsed = self.now() - self.visual_transport.run_at
        marks = self._live_feedback(elapsed) if elapsed >= 0 else []
        self.live_assessment.publish(marks, self._feedback_take())

    def _live_marks_for_snapshot(self, _elapsed_seconds: float) -> list[dict]:
        # _state_snapshot runs _update first, which refreshed these marks.
        return list(self.live_assessment.latest_marks) if self.running else []

    def _live_feedback(self, elapsed_seconds: float) -> list[dict]:
        """Only publish source-bound live marks with a current engraved map."""
        p = self.plan
        if p is None or self.preview_only or not self.running:
            return []
        engraving = self.score_artifacts.cached_layout(self._score_selection())
        if engraving is None:
            return []
        tempo_map = self._active_tempo_map()
        try:
            marks = self.assessment_policies.select(tempo_map).live(
                p.active_phrase, hand=p.hand, bpm=p.bpm,
                played=self.recorder.presses if self.recorder else [],
                from_beat=self.visual_transport.play_from_beat, elapsed_seconds=elapsed_seconds,
                bar_boundaries=p.piece.bar_boundaries,
                layout=engraving.layout, tempo=tempo_map)
        except (ValueError, RuntimeError, KeyError):
            return []
        # Live display only: a key still held within the grader's own hold
        # tolerance has no release verdict yet (pending), not "unreleased".
        # The grading status and the final take assessment are untouched.
        for mark in marks:
            until = mark.pop("hold_tolerance_until", None)
            if (until is not None and elapsed_seconds <= until
                    and (mark.get("dimensions") or {}).get("release") == "unreleased"):
                mark["dimensions"] = {**mark["dimensions"], "release": None}
        return marks

    def advance_clock(self) -> int:
        """Advance scheduled transitions without waiting for a UI state request.

        Called by the existing native command worker on its monotonic wakeup.
        The UI can poll rarely or stop polling altogether; no second engine,
        clock, thread, or unsynchronized state writer is introduced.
        Returns the next wakeup interval in milliseconds.
        """
        began = time.perf_counter()
        try:
            with self.lock:
                self._update()
                while self.midi_ingress.deferred:
                    message, received_at, corrected_at, _transport = self.midi_ingress.deferred.popleft()
                    self._receive_message(message, received_at=received_at,
                                          corrected_at=corrected_at, deferred=True)
                if self.plan is None or self.visual_transport.paused:
                    return 250
                if (self.running or self.visual_transport._preview_loop_pending or self.visual_transport._preparation_pending
                        or self.pending_result is not None or self.visual_transport.pending_rewind is not None
                        or self.mode == "listen"):
                    # Responsive automatic transitions, recovery, and practice.
                    # The musical deadline is still the absolute monotonic epoch.
                    return 20
                return 100
        finally:
            self.runtime_timings.tick_ms.append(
                (time.perf_counter() - began) * 1000.0)

    def state(self) -> dict:
        """Full snapshot, including static values; returned by commands."""
        began = time.perf_counter()
        try:
            state = self._state_snapshot()
            state["schema_version"] = state_contract.VERSION
            return state
        finally:
            self.runtime_timings.state_ms.append(
                (time.perf_counter()-began)*1000.0)

    def poll_state(self) -> dict:
        """The per-frame snapshot: the full state minus static values."""
        state = self.state()
        for key in state_contract.STATIC_KEYS:
            state.pop(key, None)
        return state

    def _state_snapshot(self) -> dict:
        with self.lock:
            self._update()
            state = project_session_state(self._capture_session_snapshot())
            if self.pending_result is not None:
                state["bpm"] = self._presentation_bpm
            # A single authoritative next-score intent covers automatic
            # Coda/Fukuda continuation, repair and disconnected-MIDI preview.
            # The frontend must not infer a repeat from streak, BPM, or phase.
            next_floor = None
            next_deadline = None
            next_transport = self.transport_id + 1
            next_bpm = float(self.plan.bpm) if self.plan is not None else 0.0
            plan_serial = None
            announced = self.visual_transport.announced_continuation
            if (self.mode == "practice" and not self.visual_transport.paused
                    and not self.running and announced is not None
                    and self.visual_transport.announced_deadline(
                        announced[0]) is not None):
                # Every automatic continuation (failed-take preparation,
                # manual Retry preparation, clean repeat, disconnected
                # preview) is announced with the run_at it WILL start with.
                next_floor = float(announced[0])
                next_deadline = float(announced[1]) * 1000.0
                next_bpm = float(announced[2])
                plan_serial = self.visual_transport.announce_serial
            elif (self.mode == "practice" and self.running and
                    self._queue_scheduled_start is not None):
                transport, floor, run_at, stage_key, revision, serial = (
                    self._queue_scheduled_start)
                if (transport == self.transport_id and
                        stage_key == self.plan.identity and
                        revision == self.score_revision):
                    next_floor = float(floor)
                    next_deadline = float(run_at) * 1000.0
                    next_transport = self.transport_id
                    plan_serial = serial
            elif (self.mode in ("listen", "perform") and self.running
                    and not self.visual_transport.paused and self.plan is not None):
                # Listen and graded whole-piece performance must publish
                # the same absolute source deadline as timed practice.
                # Otherwise their audio/assessment can start while the
                # continuous native staff has no admitted source copy.
                next_floor = float(self.visual_transport.play_from_beat)
                next_deadline = float(self.visual_transport.run_at)*1000.0
                next_transport = self.transport_id
            elif (self.mode == "learn" and self.plan is not None
                    and not self.visual_transport.paused
                    and self.awaiting_score_revision is None
                    and str(state.get("phase", "")) in
                        ("guided_wait", "introducing", "disconnected")):
                # The guided lesson is untimed: the *backend* republishes
                # the same current idea after it has passed, with authentic
                # full-meter silence. Completion/revision invalidates it.
                now = self.now()
                duration = max(0.25,
                    self.display_phrase().end-self.display_phrase().start)
                count_in = self._next_count_in_beats()
                lead_seconds = max(count_in, 1.0)*60.0/self.plan.bpm
                gap_seconds = max(2.0,self._continuous_horizon_beats)*60.0/self.plan.bpm
                if self._guided_stream_deadline is None:
                    self._guided_stream_deadline = now+lead_seconds
                elif now > self._guided_stream_deadline + (
                        duration*60.0/self.plan.bpm+gap_seconds):
                    self._guided_stream_deadline = max(
                        now+lead_seconds,
                        self._guided_stream_deadline+
                        duration*60.0/self.plan.bpm+gap_seconds+lead_seconds)
                next_floor = 0.0
                next_deadline = self._guided_stream_deadline*1000.0
                next_transport = self.transport_id
            if (self.plan is not None and next_floor is not None
                    and next_deadline is not None):
                _, bar_beats, plan_meter = self.attempt_progression.count_in_bar(
                    phrase=self.plan.active_phrase,
                    boundaries=self.plan.piece.bar_boundaries,
                    time_signatures=self.plan.piece.time_signatures,
                    position=next_floor)
                state["score_queue_next"] = {
                    # An announced continuation keeps one identity while its
                    # deadline is re-timed to its admitted ink (rest Resume).
                    "plan_id": f"{self.fingerprint}:{self.plan.identity}:"
                               f"{self.score_revision}:{next_transport}:"
                               f"{next_floor:.6f}:" + (
                                   f"a{plan_serial}" if plan_serial is not None
                                   else f"{next_deadline:.3f}"),
                    "source_from_beat": next_floor,
                    "deadline_at_ms": next_deadline,
                    # The take this source is graded as, and the one
                    # count-in bar spoken immediately before its deadline.
                    "transport_id": next_transport,
                    "count_in_beats": (lead_in_beats(bar_beats, next_bpm)
                                       if bar_beats > 0 and next_bpm > 0
                                       else 0.0),
                    # That take's start tempo: its count-in is at this BPM.
                    "bpm": next_bpm,
                    # The rate the take's own (possibly mapped) tempo starts
                    # at: Godot's presentation axis switches to it exactly at
                    # the deadline instead of a late snapshot later.
                    "start_rate_bpm": self._start_rate_bpm(next_floor, next_bpm),
                    # The meter its count-in pulses in (compound: M3).
                    "count_in_meter": list(plan_meter),
                }
            state["mistake_response_strategy"] = self.library.settings["mistake_response_strategy"]
            if self._tempo_epoch is not None and self.plan is not None and \
                    self._tempo_key == (self.plan.identity, float(self._presentation_bpm)):
                state["tempo_epoch_ms"] = self._tempo_epoch * 1000.0
            if self.teaching_continuation.handoff_world is not None:
                state["next_stage_start_beat"] = self.teaching_continuation.handoff_world
            if self.plan is not None:
                beat = self.plan.active_phrase.start + self.visual_transport.play_from_beat
                if self.running and self.now() >= self.visual_transport.run_at:
                    beat += self._elapsed_beat(self.now() - self.visual_transport.run_at)
                keys = [key for key in self.plan.piece.key_signatures
                        if key.beat <= beat + 1e-7
                        and key.hand in ("both", self.plan.hand)]
                state["key_fifths"] = keys[-1].fifths if keys else 0
            # A score-free Settings screen still needs an authoritative
            # backend clock epoch for its MIDI tap calibration. Midpoint-only
            # UI extrapolation drifts when score and device requests queue.
            calibration_sample_at = self.now()
            state.setdefault("clock_sampled_at_ms", calibration_sample_at * 1000.0)
            state["midi_offset_ms"] = self.library.settings["midi_offset_ms"]
            state["next_count_in_beats"] = self._next_count_in_beats()
            state["next_count_in_meter"] = self._next_count_in_meter()
            state["short_rest_latency_seconds"] = SHORT_REST_LATENCY_SECONDS
            state["resume_count_in_beat"] = (
                (calibration_sample_at - self.midi_ingress.resume_grading_after)
                * self.plan.bpm / 60.0
                if self.running and not self.visual_transport.paused
                and calibration_sample_at < self.midi_ingress.resume_grading_after
                and self.plan is not None else None)
            state["midi_key_range"] = self.midi_key_shortcuts.status(self.midi.device)
            state["midi_calibration"] = self.midi_calibration.snapshot(
                calibration_sample_at)
            return state

    def _set_snapshot_visual_gap(self, beats: float) -> None:
        # Engraved preparation is authoritative for loop silence.
        self.visual_transport.visual_gap_beats = beats

    def _capture_session_snapshot(self) -> SessionSnapshot:
        """Sample named read ports under the existing application lock."""
        values = SnapshotValues(
            _guided_recovery_pending=self._guided_recovery_pending,
            _guided_return=self._guided_return,
            _remediation_active=self._remediation_active,
            auto=self.auto,
            awaiting_score_revision=self.awaiting_score_revision,
            count_in_bar_beats=self.count_in_bar_beats,
            count_in_beats=self.count_in_beats,
            count_in_meter=self.count_in_meter,
            feedback=self.feedback,
            feedback_marks=self.feedback_marks,
            feedback_unmapped=self.feedback_unmapped,
            fingerprint=self.fingerprint,
            guided_range=self.guided_range,
            is_builtin_warmup=self.is_builtin_warmup,
            metronome=self.library.settings["metronome"],
            midi_input_count=self.midi.input_count,
            midi_input_note=self.midi.input_note,
            midi_input_at=self.midi.input_at,
            midi_connected=self.midi.connected,
            midi_device=self.midi.device,
            midi_notes=len(self.recorder.presses) if self.recorder is not None else 0,
            teaching_active=self.teaching is not None,
            mode=self.mode,
            next_action=self.next_action,
            next_at=self.visual_transport.next_at,
            open_from_beat=self.open_from_beat,
            pause_context=self.pause_context,
            paused=self.visual_transport.paused,
            paused_at=self.visual_transport.paused_at,
            pending_result=self.pending_result,
            pending_rewind=self.visual_transport.pending_rewind,
            performance_summary=self.performance_summary,
            persistent_hints=self.persistent_hints,
            plan=self.plan,
            play_from_beat=self.visual_transport.play_from_beat,
            practice_preparation=self.visual_transport.practice_preparation,
            preview_only=self.preview_only,
            recovery_notice=self.recovery_notice,
            retry_range=self.retry_range,
            review_end_beat=self.review_end_beat,
            run_at=self.visual_transport.run_at,
            running=self.running,
            score_revision=self.score_revision,
            transport_id=self.transport_id,
            visual_offset_beats=self.visual_transport.visual_offset_beats,
        )
        reads = SnapshotReadPorts(
            seek_grid=self._seek_grid,
            learner_snapshot=self._learner_snapshot,
            elapsed_beat=self._elapsed_beat,
            phase=self._phase,
            source_model=self._source_model,
            live_feedback=self._live_marks_for_snapshot,
            visual_motion=self._visual_motion,
            active_tempo_map=self._active_tempo_map,
            display_phrase=self.display_phrase,
            guided_marks=self._guided_marks,
            listen_snapshot=self.listen.snapshot,
            live_input_snapshot=self.live_input.snapshot,
            preparation_schedule=self.visual_transport.preparation_schedule,
            teaching_snapshot=self.teaching.snapshot if self.teaching is not None else None,
            set_visual_gap_beats=self._set_snapshot_visual_gap,
            clock=self.now,
        )
        return capture_session_snapshot(values, reads)

    def _next_stage_selection(self, *, offset: int = 1) -> tuple[ScoreSelection, int] | None:
        """Snapshot an upcoming lesson without mutating its active cursor."""
        if self.plan is None or self.is_builtin_warmup or self.mode != "practice":
            return None
        decided = self._decided_stage_selection() if offset == 1 else None
        if decided is not None:
            return decided
        p = self.plan
        number = p.lesson_step_number + offset
        if number > len(p.lesson_steps):
            return None
        future = manual_progress(p.course_state(), "select_step", number=number)
        return ScoreSelection(piece=future.piece, phrase=future.stage.variant.phrase,
            hand=future.hand, stage_key=future.key, revision=self.score_revision+offset,
            fingerprint=self.fingerprint, transformed_rhythm=future.stage.transformed_rhythm,
            display_name=str(future.stage.display_name or "")), number

    @staticmethod
    def _stage_runway_label(step, display_name: str = "") -> str:
        hand = {"right": "Right hand", "left": "Left hand",
                "both": "Both hands"}.get(step.hand, step.hand.capitalize())
        # Presentation is derived from the registered stage description,
        # never a technical generator identifier used for saved progress.
        return f'{hand} · {display_name or "Next exercise"}'

    def next_stage_score(self) -> bytes:
        """Begin ahead-of-time score preparation without blocking MIDI timing."""
        with self.lock:
            planned = self._next_stage_selection()
            if planned is None:
                return b'{"status":"none"}'
            selection, number = planned
            label = self._stage_runway_label(selection, selection.display_name)
            return self.future_score.ensure(
                selection, number=number, label=label)

    def report_preload_failure(self, *, fingerprint: str, step_number: int,
                               revision: int, error: str) -> dict:
        """Fail closed on an exact Godot native-ink compilation failure.

        An old response cannot poison another piece or the next stage.
        The current scored take still finishes; the failure is consumed only
        at its already scheduled transition boundary.
        """
        with self.lock:
            planned = self._next_stage_selection()
            if planned is None:
                return {"accepted": False}
            selection, number = planned
            if (fingerprint != self.fingerprint or number != step_number or
                    selection.revision != revision):
                return {"accepted": False}
            message = str(error).strip()[:400] or "Native score compilation failed"
            self._native_preload_failure = (
                self.fingerprint, revision, selection.stage_key, number, message)
            return {"accepted": True, "revision": revision, "step_number": number}

    def acknowledge_preloaded_stage(self, *, stage_key: str,
                                    revision: int,
                                    presentation_lead_beats: float = 0.0,
                                    presentation_clear_beats: float | None = None,
                                    continuation_clear_beats: float | None = None,
                                    continuation_header_beats: float | None = None) -> dict:
        """Only a fully compiled and exact source-bound future ink may advance."""
        with self.lock:
            planned = self._next_stage_selection()
            if planned is None:
                raise ValueError("No next lesson step to preload")
            selection, number = planned
            if selection.stage_key != stage_key or selection.revision != revision:
                raise ValueError("Preloaded step no longer matches the active course")
            if not self.future_score.ready(selection):
                raise ValueError("Next lesson notation is not yet prepared")
            if not 0.0 <= presentation_lead_beats <= 64.0 or not math.isfinite(
                    presentation_lead_beats):
                raise ValueError("Invalid future notation reading lead")
            if presentation_clear_beats is not None and not (
                    math.isfinite(presentation_clear_beats)
                    and 0.0 <= presentation_clear_beats <= 64.0):
                raise ValueError("Invalid outgoing notation clearance")
            self._future_stage_ready = (stage_key, revision)
            self._future_stage_lead_beats = presentation_lead_beats
            # Short handoff (P5): beats after the outgoing take's end until
            # the next stage may open on the empty strip; None = offscreen.
            self._future_stage_clear_beats = presentation_clear_beats
            # The incoming stage's own short-rest geometry (its density and
            # header), adopted when the handoff commits; the outgoing stage's
            # would time the new stage's repeats wrongly.
            self._future_stage_short_rest = None
            if continuation_clear_beats is not None and continuation_header_beats is not None:
                pending = (float(continuation_clear_beats), float(continuation_header_beats))
                if not all(math.isfinite(v) and 0.0 <= v <= 16.0 for v in pending):
                    raise ValueError("Invalid short-rest geometry")
                self._future_stage_short_rest = pending
            # If the future ink became ready during the existing rest gap,
            # schedule its exact delayed start immediately. Waiting for the
            # old full-bar deadline would show native ink on a false origin.
            if (self.pending_result is not None and self.auto and
                    not self.running and not self.visual_transport.paused and
                    self._decided_stage_selection() is not None):
                now = self.now()
                phrase = self.plan.active_phrase
                finish = (self.visual_transport.run_at +
                          self._elapsed_seconds(phrase.end-phrase.start) -
                          self._elapsed_seconds(self.visual_transport.play_from_beat) +
                          SETTLEMENT_SECONDS)
                if now >= finish - 1e-7:
                    self.visual_transport.next_at = now
                    self._advance_pending_feedback(now)
            # Prepare one more source-identity-bound stage while this step is
            # still being played. The next stage remains first in the queue.
            farther = self._next_stage_selection(offset=2)
            if farther is not None:
                ahead_selection, ahead_number = farther
                ahead_step = self.plan.lesson_steps[ahead_number-1]
                self.future_score.warm(
                    ahead_selection, number=ahead_number,
                    label=self._stage_runway_label(
                        ahead_step, ahead_selection.display_name))
            return {"accepted": True, "step_number": number,
                    "revision": revision, "stage_key": stage_key}

    def _score_selection(self) -> ScoreSelection:
        """Capture the selected source under the application lock."""
        if self.plan is None:
            raise ValueError("No piece loaded")
        p = self.plan
        return ScoreSelection(piece=p.piece, phrase=self.display_phrase(),
            hand=p.hand, stage_key=p.identity, revision=self.score_revision,
            fingerprint=self.fingerprint,
            transformed_rhythm=p.active_stage.transformed_rhythm)

    def _source_model(self) -> dict:
        with self.lock:
            return self.score_artifacts.source_model(self._score_selection())

    def _selected_artifacts(self) -> tuple[ScoreArtifacts, ScoreSelection]:
        """Capture the selection and its owner under the engine lock only.

        Notation, engraving and native asset preparation then run outside
        the engine lock (ScoreArtifacts serializes itself), so a cold Verovio
        engraving cannot stall the musical tick or a MIDI callback. Results
        carry their source revision; a stale one is rejected by revision.
        """
        with self.lock:
            return self.score_artifacts, self._score_selection()

    def semantic_score(self) -> dict:
        artifacts, selection = self._selected_artifacts()
        return artifacts.semantic_score(selection)

    def engraving(self) -> EngravedScore:
        artifacts, selection = self._selected_artifacts()
        return artifacts.engraving(selection)

    def geometry(self) -> dict:
        """Publish the selected native score and semantic asset revision."""
        artifacts, selection = self._selected_artifacts()
        return artifacts.geometry(selection)

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.learner_progress.lesson_overview(
                self.plan, fingerprint=self.fingerprint)


