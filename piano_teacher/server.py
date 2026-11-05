"""Piano practice engine embedded directly into the Godot process.

Owns the MIDI, grading, lessons, notation and persistent library state.
Communication with Godot uses an in-memory native command queue.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from .learning import LearningPlan
from .sqlite_transaction import sqlite_atomic
from .application.score_artifacts import ScoreArtifacts, ScoreSelection
from .application.future_score import FutureScore
from .application.midi_connection import MidiConnection, MidiNotice
from .application.midi_key_shortcuts import MidiKeyShortcuts
from .application.listen_session import ListenSelection, ListenSession
from .practice import Recorder
from .importing.pieces import import_piece
from .engraving.engraving import EngravedScore
from .fingering import FingeringService
from .library import ScoreLibrary
from .preprocessing_cache import PreprocessingCache
from .library_health import LibraryHealth
from .warmups import is_warmup
from .application.rolling_recovery import plan_rolling_recovery
from .application.mistake_responses import resolve_mistake_policy, whole_response, mistake_policy_facts
from .music import Phrase
from .measure_grid import phrase_grid
from .course_navigation import choose_source_opening
from .state_projection import (
    PhaseSnapshot, SessionSnapshot, project_phase, project_session_state,
)
from .assessment_service import AssessmentService
from .application.practice_assessment import PracticeAssessmentPolicies
from .application.strategy_session import restored_strategy_plan
from .application.control_dispatch import ControlDispatcher
from .application.score_ack import ScoreAckState, choose_score_ack_action
from .application.transport_commands import (
    StartFacts, select_start_route, require_pausable, resume_timeline,
)
from .application.stage_change import prepare_stage_change, apply_stage_change, guided_reentry
from .application.practice_transitions import TransitionContext, decide_transition
from .application.attempt_progression import AttemptProgression, AttemptTick, repeat_deadline, plan_full_passage, SETTLEMENT_SECONDS
from .application.feedback_route import FeedbackFacts, select_feedback_route
from .application.assessment_settlement import assess_completed_take
from .application.assessment_commit import commit_assessed_result
from .application.guided_session import GuidedSession, GuidedFragment, select_fragment
from .application.tempo_map_cache import TempoMapCache
from .application.session_snapshot_builder import (
    SnapshotValues, SnapshotReadPorts, capture as capture_session_snapshot,
)
from .completion_route import completion_route
from .visual_transport import VisualTransport
from .midi_calibration import MidiTapCalibration
from .live_event_ring import LiveEventRing
from .runtime_timings import RuntimeTimings
from .live_input_view import LiveInputView
from .instruction import next_full_attempt
from .learner_state import guided_units
from .progress_repository import ProgressRepository
from .application.learner_progress import LearnerProgress
from .lesson_settings import SETTINGS
from .teaching import TeachingConfig
from .application.learning_capture import LearningCapture, identifier

from .practice_history import PracticePolicyService
from .fukuda_mistake_store import FukudaMistakeStore
from .remediation import RemediationPlanner, RemedialAssignment, plan_timed_remedial_review


class UnpreparedNextStage(RuntimeError):
    """A graded source change invalidated the already approved future ink."""


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
                 live_events: LiveEventRing | None = None):
        self.lock = threading.RLock()
        # Whole-source inference must never block MIDI or state polling.
        # Serialize source loads and durable corrections separately instead.
        self._fingering_lock = threading.Lock()
        self._piece_generation = 0
        self.guided_session = GuidedSession()
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
        self.live_events = live_events if live_events is not None else LiveEventRing()
        self.runtime_timings = RuntimeTimings()
        self.recovery_notice: dict | None = None
        self.pause_context: str | None = None
        # Musical clock resumes at its previous beat after a reading lead-in.
        # No MIDI attack during that lead-in can alter a graded attempt.
        self._resume_grading_after = 0.0
        self._resume_ignored_pitches: set[int] = set()
        self._deferred_score_ack: int | None = None
        self.next_action = "Open a MIDI file."
        self.retry_range: dict | None = None
        # Persistent trouble means two boundary failures in consecutive takes
        # at the same stage and source two-bar chunk. Only a clean full take
        # or explicit stage navigation resets the history.
        self._trouble_key: tuple | None = None
        self._trouble_count = 0
        self._guided_recovery_pending = False
        self._policy_retry = None
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
        self.midi = MidiConnection(enabled=enable_midi)
        self.live_input = LiveInputView()
        self.assessment = AssessmentService()
        self.assessment_policies = PracticeAssessmentPolicies.defaults(self.assessment)
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        self.midi_key_shortcuts = MidiKeyShortcuts(self.library.settings["midi_key_ranges"])
        self._shortcut_pitch_key: tuple = ()
        self._shortcut_pitches: frozenset[int] = frozenset()
        self.library_health = LibraryHealth(self.library)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir
        self.listen = ListenSession(data_dir / "demo-audio", lock=self.lock)
        self.fingering = FingeringService(data_dir / "fingering")
        self.preprocessing = PreprocessingCache(data_dir / "preprocessed")
        self.score_artifacts = ScoreArtifacts(self.preprocessing)
        self.future_score = FutureScore(data_dir / "preprocessed")
        self._future_stage_ready: tuple[str, int] | None = None
        self._prepared_stage_published = False
        # Global musical origin of a delayed, pre-engraved next stage.
        self._stage_handoff_visual_beat: float | None = None
        # Pin the renderer-acknowledged source assets through settlement.
        self._stage_handoff_assets: tuple[tuple, ScoreArtifacts] | None = None
        # Final native renderer failures are tied to one exact future step.
        self._native_preload_failure: tuple[str, int, str, int, str] | None = None
        self.progress = ProgressRepository(data_dir / "progress.db")
        # Keep the public db handle for LearnerStateStore and existing clients.
        self.db = self.progress.db
        self.measurement = LearningCapture(self.progress.ledger)
        self.progress.ledger.prune(days=self.library.settings["evidence_retention_days"],
                                   budget_mib=self.library.settings["evidence_budget_mib"])
        self._action_reason = "transition"
        self._pending_rolling = None
        self._settlement_failed = False
        self._deferred_midi = deque()
        self.fukuda_mistakes = FukudaMistakeStore(self.db)
        self.learner_store = self.progress.learner_store
        self.learner_progress = LearnerProgress(self.learner_store)
        self.practice_policy = PracticePolicyService(
            self.progress.ledger,
            diagnosis=self.library.settings["diagnosis_strategy"],
            learner=self.library.settings["learner_strategy"])
        self.remediation_planner = RemediationPlanner()
        self._remediation_pending: RemedialAssignment | None = None
        self._remediation_active: RemedialAssignment | None = None

    def _midi_lost(self, reason: str = "device_disconnected") -> None:
        """Cancel session state after detachment and before closing the input."""
        with self.midi.disconnected(reason) as notice:
            self.midi_key_shortcuts.cancel_capture()
            self.live_input.clear_device()
            self._stop(reason=reason)
            if self.teaching is not None:
                self.teaching.set_connected(False, now=time.monotonic())
        self.feedback = notice.feedback
        self.next_action = notice.next_action

    def _present_midi_notice(self, notice: MidiNotice | None) -> None:
        if notice is None:
            return
        if notice.connected is not None and self.teaching is not None:
            self.teaching.set_connected(notice.connected, now=(notice.sampled_at
                if notice.sampled_at is not None else time.monotonic()))
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
                self.midi_calibration.start(time.monotonic())
                self.feedback = "Tap one key per click through five continuous rounds"
            elif action == "calibration_cancel":
                self.midi_calibration.cancel()
            elif action == "calibration_apply":
                result = self.midi_calibration.snapshot(time.monotonic())["result"]
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
                "timing_strategy": self.library.settings["timing_strategy"],
                "tempo_strategy": self.library.settings["tempo_strategy"],
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

    def learning_statistics(self, fingerprint: str | None = None) -> dict:
        """Read measured learning outcomes without advancing the musical clock."""
        from .learning_statistics import learning_statistics
        with self.lock:
            return learning_statistics(self.progress.ledger, fingerprint=fingerprint)

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

    def _record_policy_response(self, response, result, *, trigger: str):
        self.measurement.decision({"trigger": trigger,
            "policy": self.library.settings["mistake_response_strategy"],
            "policy_version": resolve_mistake_policy(self.library.settings["mistake_response_strategy"]).version,
            "stage_key": self.plan.identity,
            "reason": response.reason, "eligible": True, "selected": asdict(response),
            "before_bpm": self.measurement.context["performed_bpm"], "after_bpm": response.bpm,
            "trigger_evidence": {"accepted": result.passed, "strict_clean": result.clean,
                "wrong": sum(n.status == "wrong" for n in result.notes),
                "missed": sum(n.status == "missed" for n in result.notes)},
            "wrong_missed_source_ids": [n.note.source_id for n in result.notes if n.status in ("wrong", "missed")],
            "origin": "automatic", "state": "applied"})

    def _source_safe_response(self, response):
        """Expand source bars so a repair never severs an authored held note."""
        if response.end_beat is None or response.action in ("continue", "pause", "repair"):
            return response
        phrase = self.plan.active_phrase
        grid = self.attempt_progression.grid_for(phrase, self.plan.piece.bar_boundaries)
        start, end = response.restart_beat, response.end_beat
        notes = [n for n in phrase.notes if self.plan.hand == "both" or n.hand == self.plan.hand]
        while start > grid[0] and any(n.start < phrase.start+start-1e-7 < n.end-1e-7 for n in notes):
            start = grid[grid.index(start)-1]
        while end < grid[-1] and any(phrase.start+start-1e-7 <= n.start < phrase.start+end-1e-7
                                     and n.end > phrase.start+end+1e-7 for n in notes):
            end = grid[grid.index(end)+1]
        return replace(response, restart_beat=start, end_beat=end)

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
            self._begin_learn(from_beat=response.restart_beat, recovery=True)
            self.next_action = instruction
        elif deadline is not None:
            self._continue_at(deadline, from_beat=response.restart_beat)
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
                exercise_strategy=self.library.settings["exercise_strategy"],
                timing_strategy=self.library.settings["timing_strategy"],
                tempo_strategy=self.library.settings["tempo_strategy"],
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
                exercise_strategy=self.library.settings["exercise_strategy"],
                timing_strategy=self.library.settings["timing_strategy"],
                tempo_strategy=self.library.settings["tempo_strategy"],
                fukuda_mistakes=frozenset(), feedback={}) if self.plan else None)
            with self.measurement.atomic():
                self.progress.ledger.delete_learner()
            self.measurement.discard_deleted()
            self._stop(reason="delete_learner_history", persist_evidence=False)
            self.measurement = LearningCapture(self.progress.ledger)
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
            # Validate the complete configuration and prepare any new course
            # while the current session, revision and settings remain intact.
            # A generator failure must never leave a persisted strategy
            # pointing at an unrelated active learning plan.
            proposed = self.library.propose_update(**changes)
            before = self.library.settings["music_dir"]
            strategy_keys = ("exercise_strategy", "timing_strategy", "tempo_strategy")
            previous_strategy = tuple(self.library.settings[key] for key in strategy_keys)
            strategy_changed = previous_strategy != tuple(
                proposed[key] for key in strategy_keys)
            replacement = None
            if strategy_changed and self.plan is not None:
                self._save()
                replacement = restored_strategy_plan(
                    self.plan, settings=proposed,
                    progress=self.progress, fingerprint=self.fingerprint,
                    warmup=self.is_builtin_warmup,
                    fukuda_mistakes=self.fukuda_mistakes.problematic(self.fingerprint),
                    feedback=self.fukuda_mistakes.evidence(self.fingerprint))
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
            if replacement is not None:
                self._stop(reason="strategy_changed")
                self._reset_trouble()
                self.plan = replacement
                self.open_from_beat = 0.0
                self.mode = "practice"
                self.course_guided = False
                self.guided_range = None
                self.teaching = None
                self.score_artifacts.invalidate()
                self.score_revision += 1
                self.awaiting_score_revision = None
                self.feedback = "Exercise strategy changed"
                self.next_action = "Review the new exercise before starting."
                self._save()
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
                        "exercise_strategy": self.library.settings['exercise_strategy'],
                        "timing_strategy": self.library.settings['timing_strategy'],
                        "tempo_strategy": self.library.settings['tempo_strategy']}
            return {"loaded": True, "exercise_strategy": self.plan.exercise_strategy.name,
                    "timing_strategy": self.plan.timing_strategy.name,
                    "tempo_strategy": self.plan.tempo_strategy.name,
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
        now = time.monotonic() if received_at is None else received_at
        with self.lock:
            if self.midi_calibration.active:
                if not deferred:
                    self.midi.observe(message, now=now)
                if message.type == "note_on" and message.velocity > 0:
                    self.midi_calibration.observe(now)
                return
            # Hardware shortcuts are resolved before activity, grading,
            # count-in auto-start, guided capture, or live MIDI feedback.
            if message.type in ("note_on", "note_off"):
                # MIDI callbacks must not rescan an 8-measure exercise on
                # every attack/release. Regenerate this tiny pitch set only
                # when the selected score, source or practice hand changes.
                if self.plan is not None:
                    key = (self.fingerprint,self.score_revision,
                           self.plan.identity,self.plan.hand)
                    if key != self._shortcut_pitch_key:
                        self._shortcut_pitch_key = key
                        self._shortcut_pitches = frozenset(
                            note.pitch for note in self.plan.active_phrase.notes
                            if self.plan.hand == "both" or note.hand == self.plan.hand)
                else:
                    self._shortcut_pitch_key = ()
                    self._shortcut_pitches = frozenset()
                decision = self.midi_key_shortcuts.accept(
                    message, device=self.midi.device,
                    exercise_pitches=self._shortcut_pitches,
                    can_pause=self.running or (self.mode == "learn" and
                        self.teaching is not None),
                    paused=self.visual_transport.paused)
                if decision.completed_range is not None:
                    ranges = self.library.settings["midi_key_ranges"].copy()
                    ranges[self.midi.device] = list(decision.completed_range)
                    self.set_preferences(midi_key_ranges=ranges)
                if decision.action:
                    action = ("learn_retry" if decision.action == "restart"
                              and self.mode == "learn" else decision.action)
                    self.control(action)
                if decision.consumed:
                    return
            if not deferred:
                self.midi.observe(message, now=now)
            # Manual resume temporarily revisits source-time positions for
            # reading. Suppress that ungraded pre-roll, including the eventual
            # releases of keys first pressed during it.
            if message.type in ("note_on","note_off"):
                is_on = message.type == "note_on" and message.velocity > 0
                if now < self._resume_grading_after and self.running:
                    if is_on:
                        self._resume_ignored_pitches.add(message.note)
                    else:
                        self._resume_ignored_pitches.discard(message.note)
                    return
                if message.note in self._resume_ignored_pitches:
                    if not is_on:
                        self._resume_ignored_pitches.remove(message.note)
                    return
            corrected_at = (now - self.library.settings["midi_offset_ms"] / 1000.0
                            if corrected_at is None else corrected_at)
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
                if not deferred and (due or self._deferred_midi):
                    self._deferred_midi.append((message.copy(), now, corrected_at,
                                                self.transport_id))
                    return
            if message.type in ("note_on", "note_off"):
                is_on = message.type == "note_on" and message.velocity > 0
                self.live_input.receive(
                    pitch=message.note, is_on=is_on, now=corrected_at,
                    phrase=self.plan.active_phrase if self.plan is not None else None,
                    hand=self.plan.hand if self.plan is not None else "both",
                    bpm=self.plan.bpm if self.plan is not None else 60.0,
                    from_beat=self.visual_transport.play_from_beat, run_at=self.visual_transport.run_at,
                    running=self.running, paused=self.visual_transport.paused,
                    preview=self.preview_only, mode=self.mode,
                    transport_id=self.transport_id,
                    tempo_map=self._active_tempo_map(),
                )
                if is_on and self.live_input.events:
                    self.live_events.publish(self.live_input.events[-1])
            if self.mode == "learn":
                if (self.teaching is not None and self.midi.connected
                        and message.type in ("note_on", "note_off")):
                    self.teaching.receive(pitch=message.note,
                        is_on=message.type == "note_on" and message.velocity > 0,
                        channel=getattr(message, "channel", 0), at=now)
                    if self.measurement.attempt_id is not None:
                        self.measurement.guided.add(message.note,
                            message.type == "note_on" and message.velocity > 0,
                            now-self.measurement.origin-self.measurement.context["monotonic_start"])
                return
            if self.mode == "listen":
                return
            if self.running and not self.visual_transport.paused and now >= self.visual_transport.run_at and self.recorder:
                if message.type == "note_on":
                    self.recorder.add(message.note, message.velocity > 0, corrected_at - self.visual_transport.run_at)
                elif message.type == "note_off":
                    self.recorder.add(message.note, False, corrected_at - self.visual_transport.run_at)

    def load(self, path: str, *, warmup: bool = False):
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
                    timing_strategy=self.library.settings['timing_strategy'],
                    tempo_strategy=self.library.settings['tempo_strategy'],
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
        # current take and durable records are still intact.
        replacement = LearningPlan(piece, warmup=warmup,
                    exercise_strategy=self.library.settings['exercise_strategy'],
                    timing_strategy=self.library.settings['timing_strategy'],
                    tempo_strategy=self.library.settings['tempo_strategy'],
                    fukuda_mistakes=frozenset(), feedback={})
        # Publish all replacement records before stopping the current take.
        with self.measurement.atomic():
            self.measurement.interrupt("lesson_reset", self.recorder.presses if self.recorder else
                                       self.measurement.guided.presses)
            self.measurement.flush_intervals(time.monotonic())
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
                    extra={"guidance": self.teaching.snapshot(now=time.monotonic())}
                          if self.mode == "learn" and self.teaching is not None else None)
                self.measurement.flush_intervals(time.monotonic())
        self._deferred_midi.clear()
        self._resume_grading_after = 0.0
        self._resume_ignored_pitches.clear()
        # Stopping/restarting a take does not invalidate precompiled next
        # notation. Its stage-key + score revision remain authoritative:
        # navigation, library changes and generation mismatches fail that
        # identity check automatically at the next settlement.
        self._prepared_stage_published = False
        self._stage_handoff_visual_beat = None
        self._stage_handoff_assets = None
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
        self._policy_retry = None
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
        """Record a completed guided idea once, without awarding timed mastery."""
        prepared_before = self.guided_session.prepared
        completed = False
        guidance = (self.teaching.snapshot(now=time.monotonic()) if
                    self.mode == "learn" and self.teaching is not None else None)
        exposure_completed = bool(guidance and guidance["completed"] and
                                  self.measurement.attempt_id is not None)
        if guidance and not guidance["completed"]:
            self.measurement.observe_guidance(guidance)
            return
        if exposure_completed:
            self.measurement.seal(self.measurement.guided.presses,
                state="completed", reason="guided_preparation", extra={"guidance": guidance})
        try:
            with self.measurement.atomic():
                completed = self.guided_session.commit_completed_preparation(
                    learning=self.mode == "learn",
                    remediation_active=self._remediation_active is not None,
                    fingerprint=self.fingerprint,
                    stage_key=self.plan.identity if self.plan is not None else "",
                    current_unit=self._guided_unit,
                    record_preparation=self.learner_progress.record_guided_preparation)
                if exposure_completed:
                    self.measurement.observe_guidance(guidance)
                    policy = resolve_mistake_policy(self.library.settings["mistake_response_strategy"])
                    if (self._guided_return is not None and policy.whole_handler is not None
                            and self.measurement.episode is not None and not self.measurement.decisions):
                        start, end = self.guided_range
                        self.measurement.decision({"trigger": "guided_completion",
                            "policy": policy.name, "policy_version": policy.version,
                            "stage_key": self.plan.identity, "reason": "guidance_requires_unsupported_retry",
                            "before_bpm": self.plan.bpm, "after_bpm": self.plan.bpm,
                            "selected": {"bpm": self.plan.bpm, "restart_beat": start,
                                "end_beat": end, "guided": False, "action": "isolate",
                                "reason": "guidance_requires_unsupported_retry", "mode": policy.name},
                            "assisted_count": guidance.get("assisted_count"),
                            "mastery_eligible": False, "origin": "automatic", "state": "applied"})
                    self.measurement.persist()
        except Exception:
            self.guided_session.prepared = prepared_before
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=time.monotonic())
            self.feedback = "Could not save the guided preparation"
            self.next_action = "Check storage, then Resume to save this same exposure."
            raise
        if exposure_completed:
            self.measurement.finish()


    def _learner_snapshot(self) -> dict:
        return self.learner_progress.snapshot(
            self.plan, fingerprint=self.fingerprint, mode=self.mode,
            guided_range=self.guided_range, course_guided=self.course_guided)

    def _begin_course_stage(self, *, bump_revision: bool = True, explicit_learn: bool = False):
        if self.plan.exercise.kind == "perform" and not explicit_learn:
            self._prepare_perform()
            return
        unit = self.learner_progress.next_course_unit(
            self.plan.active_variant, self.plan.piece.bar_boundaries,
            self._learner_saved(), explicit_learn=explicit_learn)
        if unit is None:
            self._prepare_practice()
        else:
            self._begin_learn(from_beat=unit["start_beat"], bump_revision=bump_revision)

    def _select_step(self, step):
        self.plan.select_step(self.plan.lesson_steps.index(step) + 1)
        self._reset_trouble()

    def _skip_stage(self, reason):
        p = self.plan
        following = self.learner_progress.next_skippable_step(p, reason)
        self.learner_progress.mark_skipped(
            fingerprint=self.fingerprint, stage_key=p.identity, reason=reason)
        self._stop(reason="skip_stage")
        self._select_step(following)
        self.course_guided = True
        self._begin_course_stage()
        self._save()

    def _place_original(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        p = self.plan
        candidate = self.learner_progress.original_placement_step(p)
        self.learner_progress.mark_prior_steps_placed(
            p, fingerprint=self.fingerprint, candidate=candidate)
        self._stop()
        self._select_step(candidate)
        self.course_guided = True
        self._begin_course_stage()
        self._save()

    def _valid_trouble_spots(self, *, stage_key: str | None = None) -> list[dict]:
        return self.learner_progress.valid_trouble_spots(
            self.plan, fingerprint=self.fingerprint, stage_key=stage_key)

    def _revisit_trouble(self, stage_key, start_beat):
        step, unit = self.learner_progress.choose_trouble_spot(
            self.plan, fingerprint=self.fingerprint,
            stage_key=stage_key, start_beat=start_beat)
        p = self.plan
        bpm = p.bpm
        self._stop()
        self._select_step(step)
        p.bpm = bpm
        self.learner_progress.reactivate_trouble(
            fingerprint=self.fingerprint, stage_key=stage_key)
        self.course_guided = True
        self.retry_range = {
            field: unit[field] for field in (
                "first_bar", "last_bar", "start_beat", "end_beat")}
        self._begin_learn(from_beat=unit["start_beat"], recovery=True)
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
                     remediation: RemedialAssignment | None = None):
        if self.plan is None:
            raise ValueError("Open a piece first")
        fragment = select_fragment(
            self.plan.active_variant, self.plan.piece.bar_boundaries,
            from_beat=from_beat)
        start, end = fragment.beat_range
        retry_range = self.retry_range if recovery else None
        self._stop(reason="guided_recovery" if recovery else "learn", preserve_episode=recovery)
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
        self.transport_id += 1
        # Reuse the existing guided owner: one controller, held-key history,
        # fragment source and completion state for this teaching session.
        self.guided_session.bind(GuidedFragment(
            variant=(remediation.variant if remediation is not None
                     else self.plan.active_variant),
            start_beat=start, end_beat=end,
            phrase=fragment.phrase),
            stage_key=self.plan.identity, revision=self.score_revision,
            now=time.monotonic(), connected=self.midi.connected,
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


    def _prepare_practice(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        return_context = self._guided_return
        retry_range = self.retry_range
        guided_range = self.guided_range
        self._stop(reason="reintegration", preserve_episode=return_context is not None)
        # An idle score selected with Open at measure N must already point
        # at that source measure. Start later uses the same origin.
        phrase = self.plan.active_phrase
        self.visual_transport.play_from_beat = max(0.0, min(
            self.open_from_beat, phrase.end - phrase.start - 1e-6))
        if return_context is not None and return_context[0] == self.plan.identity:
            self.visual_transport.pending_rewind = return_context[1]
            self.retry_range = retry_range
            self._guided_return = return_context
            if (guided_range is not None and resolve_mistake_policy(
                    self.library.settings["mistake_response_strategy"]).whole_handler is not None):
                self.open_from_beat = return_context[1]
                self.review_end_beat = guided_range[1] if guided_range[1] < phrase.end-phrase.start-1e-7 else None
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
        self.transport_id += 1
        self.running = True
        self.count_in_bar_beats = start.count_in_bar_beats
        self.count_in_meter = list(start.count_in_meter)
        self.count_in_beats = start.count_in_beats
        self.visual_transport.run_at = time.monotonic()+start.delay_seconds
        self.feedback = "Count in, then listen"

    def _prepare_perform(self, *, scope: str = "current"):
        if self.plan is None:
            raise ValueError("Open a piece first")
        if scope not in ("current", "whole"):
            raise ValueError("Choose the current passage or whole piece")
        self._stop()
        p = self.plan
        if scope == "whole":
            bpm = p.bpm
            index = next((i for i, exercise in reversed(list(enumerate(p.exercises)))
                          if exercise.kind == "perform"), None)
            p.select(index if index is not None else 0)
            p.hand_index = p.hands.index("both") if "both" in p.hands else 0
            p.variant_index = len(p.variants)-1
            p.bpm = bpm
            self._reset_trouble()
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
        """Select only a scored, real source interval from the current review."""
        selected = self.assessment.select_review_section(
            self.performance_summary,
            plan_ready=(self.plan is not None
                        and self.review_stage_identity == self.plan.identity),
            first_bar=first_bar, last_bar=last_bar)
        self._prepare_practice()
        self.open_from_beat = selected["start_beat"]
        self.review_end_beat = selected["end_beat"]
        self.retry_range = {key: selected[key] for key in
                            ("first_bar", "last_bar", "start_beat", "end_beat")}
        # Rendering prepares the selected score; this retry must not start
        # automatically when Godot acknowledges that the notation is ready.
        self.awaiting_score_revision = None
        self.auto = False
        self.feedback = f"Ready to repeat measures {first_bar}-{last_bar}"
        self.next_action = "Press Start to practise this section; no mastery is awarded for a partial attempt."

    def _practice_weak(self):
        if (self.mode != "perform" or not self.performance_summary
                or not self.performance_summary["weakest_bars"]):
            raise ValueError("Finish a performance with a difficult section first")
        selected = self.performance_summary["weakest_bars"][0]
        self._review_retry(selected["first_bar"], selected["last_bar"])

    def _seek_grid(self) -> tuple[float, ...] | None:
        if (self.plan is None or self.mode not in ("learn", "practice", "perform")
                or not self.plan.piece.bar_boundaries):
            return None
        try:
            return phrase_grid(self.plan.active_phrase, self.plan.piece.bar_boundaries)
        except ValueError:
            return None

    def _seek(self, bar):
        # Validate before cancelling any paused clock, feedback, or score ack.
        if not self.visual_transport.paused:
            raise ValueError("Pause before choosing a source bar")
        grid = self._seek_grid()
        if grid is None:
            raise ValueError("Seeking needs a source measure grid in Learn, Practice, or Perform")
        phrase = self.plan.active_phrase
        if type(bar) is not int or not phrase.first_bar <= bar <= phrase.last_bar:
            raise ValueError("Choose a whole bar number inside the active passage")
        start = grid[bar-phrase.first_bar]
        if self.mode == "learn":
            self._begin_learn(from_beat=start)
        else:
            self._prepare_practice()
            self.visual_transport.pending_rewind = start
            self.retry_range = {"first_bar": bar, "last_bar": phrase.last_bar,
                                "start_beat": start, "end_beat": grid[-1]}
            self.next_action = f"Get ready to play from bar {bar} at {self.plan.bpm} BPM."

    def _commit_pending(self) -> str:
        """Settle graded evidence, source feedback and mastery atomically.

        The pending take is retained until every SQLite effect succeeds.
        Roll back the same LearningPlan object if a generator, evidence
        store or durable write fails midway through the transaction.
        """
        if self.pending_result is None or self.plan is None:
            return ""
        p = self.plan
        result = self.pending_result
        previous_phrase_start, previous_phrase_end = (
            p.active_phrase.start, p.active_phrase.end)
        # Snapshots contain only the mutating LearningPlan collections.
        # Source Piece, exercises and immutable stage definitions are shared.
        plan_before = {key: (value.copy() if isinstance(value, (dict, list, set))
                             else value) for key, value in vars(p).items()}
        engine_fields = (
            "_trouble_key", "_trouble_count", "retry_range",
            "_remediation_pending", "recovery_notice", "score_revision",
            "awaiting_score_revision", "open_from_beat",
            "performance_summary", "review_stage_identity",
            "_prepared_stage_published", "_stage_handoff_visual_beat",
            "_stage_handoff_assets",
        )
        engine_before = {key: getattr(self, key) for key in engine_fields}
        visual_offset_before = self.visual_transport.visual_offset_beats
        score_artifacts_before = self.score_artifacts
        self._prepared_stage_published = False
        try:
            with self.measurement.atomic():
                self.measurement.persist()
                # Source-specific mistakes are learned from authentic original
                # MIDI attempts, never from generated exercises or Listen previews.
                use_feedback = (p.accepts_performance_feedback
                              and p.active_variant.level=="original"
                              and not self.is_builtin_warmup
                              and bool(result.notes))
                if result.passed:
                    self._reset_trouble()
                    self.learner_progress.resolve_trouble(
                        fingerprint=self.fingerprint, stage_key=p.identity)
                self.retry_range = None
                outcome = commit_assessed_result(
                    plan=p, result=result, fingerprint=self.fingerprint,
                    assessed_bpm=self._pending_assessed_bpm,
                    automatic=self.auto, mode=self.mode, warmup=self.is_builtin_warmup,
                    observe=self.practice_policy.observe,
                    plan_remediation=(self.remediation_planner.plan if resolve_mistake_policy(
                        self.library.settings["mistake_response_strategy"]).whole_handler is None
                        else lambda *args, **kwargs: None))
                if use_feedback:
                    # Reuse graded original source IDs through the selected generator's
                    # feedback contract. No name-based algorithm dispatch in the engine.
                    self.fukuda_mistakes.observe(self.fingerprint, result)
                    evidence = self.fukuda_mistakes.evidence(self.fingerprint)
                    failed_ids = frozenset(n.note.source_id for n in result.notes
                                           if n.status != "correct")
                    accepted = result.passed
                    settled_stage = p.identity
                    changed = p.refresh_from_feedback(
                        evidence, prefer_repair=not accepted and bool(failed_ids),
                        focus_ids=failed_ids)
                    if not changed and not accepted and failed_ids:
                        changed = p.revisit_source_errors(failed_ids)
                    if changed and p.identity != settled_stage:
                        # Re-engrave only if the next *active score* has changed.
                        # An accepted take may update the future practice catalog
                        # while retaining exactly the same active source notes.
                        self._remediation_pending = None
                        self.score_artifacts.invalidate()
                        self.score_revision += 1
                        self.awaiting_score_revision = None
                if outcome.remediation is not None and not (
                        use_feedback and changed):
                    self._remediation_pending = outcome.remediation
                if outcome.accelerated:
                    self.recovery_notice = {
                        "kind": "speedup", "errors": 0,
                        "from_bpm": outcome.previous_bpm, "to_bpm": p.bpm,
                        "first_bar": p.active_phrase.first_bar,
                        "last_bar": p.active_phrase.last_bar,
                        "expires_at": time.monotonic() + 7.0,
                    }
                if outcome.stage_changed:
                    self.open_from_beat = 0.0
                    self.performance_summary = None
                    self.review_stage_identity = None
                    # The upcoming score was rendered before this committed
                    # stage change. Do not reset the moving camera to beat 0.
                    # The next pre-engraved stage begins immediately after the
                    # final graded note's bounded settlement window, without
                    # inserting a full rest/count-in between different steps.
                    stage_advance_beats = (
                        previous_phrase_end - previous_phrase_start
                        + SETTLEMENT_SECONDS * outcome.previous_bpm / 60.0)
                    self.score_revision += 1
                    if (self.auto and self._future_stage_ready ==
                            (p.identity, self.score_revision)):
                        next_selected = self._score_selection()
                        pinned = self._stage_handoff_assets
                        prebuilt = (pinned[1] if pinned is not None and
                                    pinned[0] == next_selected.identity
                                    else self.future_score.adopt(next_selected))
                        if prebuilt is not None:
                            self.score_artifacts = prebuilt
                            self._prepared_stage_published = True
                            self.visual_transport.visual_offset_beats = (
                                self._stage_handoff_visual_beat
                                if self._stage_handoff_visual_beat is not None
                                else self.visual_transport.visual_offset_beats + stage_advance_beats)
                        elif self.auto and result.passed and self._stage_handoff_assets is not None:
                            # Never commit an automatic step that cannot be
                            # displayed by the renderer already approved for
                            # this musical handoff. Roll back all assessment
                            # effects and report the invalidated source.
                            raise UnpreparedNextStage(
                                "The next lesson score changed after preloading")
                        else:
                            self.visual_transport.visual_offset_beats = 0.0
                    elif self.auto and result.passed and self._stage_handoff_assets is not None:
                        raise UnpreparedNextStage(
                            "The graded lesson selected a different next score")
                    else:
                        self.visual_transport.visual_offset_beats = 0.0
                self._save()
                if self.measurement.attempt_id is not None:
                    self.measurement.event("progression", {
                        "fingerprint": self.fingerprint,
                        "before_stage": outcome.previous_stage,
                        "after_stage": p.identity, "before_bpm": outcome.previous_bpm,
                        "after_bpm": p.bpm, "streak": p.streak,
                        "mastery_transition": (outcome.previous_stage not in plan_before["mastered"]
                                               and outcome.previous_stage in p.mastered),
                        "mastery_bpm": p.mastered.get(outcome.previous_stage),
                        },
                        key=f"{self.measurement.attempt_id}:progression")

        except Exception:
            vars(p).clear()
            vars(p).update(plan_before)
            for key, value in engine_before.items():
                setattr(self, key, value)
            self.visual_transport.visual_offset_beats = visual_offset_before
            self.score_artifacts = score_artifacts_before
            self._settlement_failed = True
            raise
        self.pending_result = None
        self._pending_assessed_bpm = None
        self.measurement.finish()
        self._settlement_failed = False
        self._stage_handoff_visual_beat = None
        self._stage_handoff_assets = None
        return outcome.message

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float | None = None):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            if self.mode == "learn":
                self._prepare_practice()
                return
            if self.measurement.attempt_id is not None:
                self.measurement.interrupt("restart", self.recorder.presses if self.recorder else ())
            self._policy_retry = None
            self._resume_grading_after = 0.0
            self._resume_ignored_pitches.clear()
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
            self.transport_id += 1
            self.live_input.reset_attempt()
            self.live_input.prepare(phrase)
            self.running = True
            self.auto = mode == "practice" and not self.preview_only
            self.awaiting_score_revision = None
            self.pending_result = None
            self._pending_assessed_bpm = None
            self.feedback_marks = []
            self.feedback_unmapped = 0
            self.recorder = Recorder()
            self.visual_transport.visual_gap_beats = self._source_model()[
                "practice_timeline"]["gap"]["duration_beats"]
            position = self.open_from_beat if from_beat is None else from_beat
            scheduled = self.attempt_progression.schedule_start(
                phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
                time_signatures=self.plan.piece.time_signatures,
                bpm=self.plan.bpm, position=position,
                loop_continuation=loop_continuation,
                preview=self.preview_only, now=time.monotonic())
            self.visual_transport.play_from_beat = scheduled.from_beat
            self.count_in_bar_beats = scheduled.count_in_bar_beats
            self.count_in_meter = list(scheduled.count_in_meter)
            self.count_in_beats = scheduled.count_in_beats
            self.next_boundary_beat = scheduled.next_boundary_beat
            self.visual_transport.run_at = (scheduled.run_at if scheduled_deadline is None
                                            else scheduled_deadline)
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
            self.measurement.phase_changed("count_in" if self.count_in_beats else "active", time.monotonic())
            self.feedback = "Count in, then play"
            self.next_action = scheduled.next_action

    def _continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Retain polling overshoot instead of moving the musical deadline."""
        self.start(from_beat=from_beat, mode=self.mode, loop_continuation=True,
                   scheduled_deadline=deadline)

    def _schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float):
        """Reverse on this pass, then traverse one semantic rest into target."""
        self.visual_transport.schedule_source_preparation(
            self._source_model(), source_from_beat=target,
            from_visual=from_visual, now=now,
            reverse_seconds=reverse_seconds, bpm=self.plan.bpm)
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
                self.teaching.start(now=time.monotonic())
            elif decision == "practice":
                self.start(
                    from_beat=(self.visual_transport.pending_rewind if self.visual_transport.pending_rewind is not None
                               else self.open_from_beat),
                    mode="perform" if self.mode == "perform" else "practice")
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
                    or not self.teaching.snapshot(now=time.monotonic())["completed"]):
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
                bool(kwargs.get("enabled", False)), now=time.monotonic())
            if kwargs.get("enabled", False) and self.measurement.attempt_id is not None:
                self.measurement.assistance_used = True

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
            self.feedback = "Stopped"
            self.next_action = "Start when you are ready."
        elif action in ("start", "restart"):
            self._start_or_restart(action)
        elif action == "pause":
            self._pause_current_session()
        elif action == "resume":
            self._resume_current_session()

    def _open_selected_measure(self, kwargs: dict):
        """Open a source measure using the existing lesson navigation policy."""
        # Select a source measure across the entire imported piece,
        # then enter the existing learning or timed-practice flow.
        # No score is awarded simply by changing the starting point.
        target = choose_source_opening(
            self.plan, bar=kwargs.get("bar"),
            mode=kwargs.get("mode", "learn"),
            warmup=self.is_builtin_warmup)
        plan = self.plan
        requested_mode = target.mode
        selected_bar = target.bar
        index = target.exercise_index
        self._stop()
        self._reset_trouble()
        plan.select(index)
        self.course_guided = requested_mode == "learn"
        beat = plan.piece.bar_boundaries[selected_bar-1] - plan.active_phrase.start
        if not 0 <= beat < plan.active_phrase.end - plan.active_phrase.start:
            raise ValueError("Selected measure falls outside the playable passage")
        self.open_from_beat = beat
        if requested_mode == "learn":
            self._begin_learn(from_beat=beat)
        else:
            self._prepare_practice()
            # This opening is user-initiated. Wait for Start after
            # engraving rather than auto-running on score_ready.
            self.awaiting_score_revision = None
            self.feedback = f"Ready to practise from measure {selected_bar}"
            self.next_action = "Press Start to play from the selected measure."
        return

    def _start_or_restart(self, action: str):
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
            self._apply_rolling_recovery(decision, phrase, grid, score_beat, time.monotonic())
            self.visual_transport.paused = False
            self.visual_transport.paused_at = 0.0
            return
        p = self.plan
        route = select_start_route(StartFacts(
            action=action, mode=self.mode, loaded=p is not None,
            source_changed=(self.score_artifacts.source_bpm_changed(p.piece.bpm)
                            if p is not None and self.mode not in ("listen", "learn")
                            else False),
            exercise_kind=p.exercise.kind if p is not None else None))
        if route == "listen":
            self._prepare_listen()
            return
        if route == "prepare_practice":
            self.control("practice")
            return
        if route == "reload_score":
            self._stop()
            self.score_revision += 1
            self.awaiting_score_revision = self.score_revision
            self.feedback = "Preparing sheet music"
            return
        if route == "rewind":
            sampled = time.monotonic()
            self.measurement.interrupt("restart", self.recorder.presses if self.recorder else ())
            visual_now = self.visual_transport.paused_at if self.visual_transport.paused else sampled
            position, _, _ = self._visual_motion(visual_now)
            target = (self.visual_transport.pending_rewind if self.visual_transport.pending_rewind is not None
                      else self.visual_transport.play_from_beat)
            self.visual_transport.paused = False
            self.visual_transport.paused_at = 0.0
            self.pause_context = None
            self._deferred_score_ack = None
            self.awaiting_score_revision = None
            self.pending_result = None
            self._policy_retry = None
            self._pending_assessed_bpm = None
            self.visual_transport._retry_previous_pass = False
            self._guided_recovery_pending = False
            self._resume_grading_after = 0.0
            self._resume_ignored_pitches.clear()
            self._schedule_preparation(target, now=sampled, from_visual=position,
                                       reverse_seconds=self.feedback_seconds)
            self.feedback = "Get ready to retry"
            return
        self.start(mode="perform" if self.mode == "perform" else "practice")
        return

    def _pause_current_session(self):
        """Pause learning, playback or preparation using one sampled clock."""
        now = time.monotonic()
        context = self._phase(now) if not self.visual_transport.paused else ""
        require_pausable(paused=self.visual_transport.paused, phase=context)
        self.pause_context = context
        self.visual_transport.pause(at=now)
        self.measurement.phase_changed("pause", now)
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.pause(now=now)
        return

    def _resume_current_session(self):
        """Resume teaching and transport from the same monotonic instant."""
        learning = self.mode == "learn" and self.teaching is not None
        shift_run_at = resume_timeline(
            paused=self.visual_transport.paused, learning=learning, running=self.running,
            preview_pending=self.visual_transport._preview_loop_pending,
            automatic_feedback=self.pending_result is not None and self.auto)
        now = time.monotonic()
        paused_at = self.visual_transport.paused_at
        previous_origin = self.visual_transport.run_at
        had_reading_lead = self._resume_grading_after > paused_at
        if learning:
            self.teaching.resume(now=now)
        self.visual_transport.resume(now=now, shift_run_at=shift_run_at)
        if had_reading_lead:
            self._resume_grading_after += max(0.0, now-paused_at)
        # A paused passage returns with a short genuine count-in. Its
        # authoritative run_at moves, so MIDI grading and source ink agree
        # and no note is required during the visual reading lead-in.
        if (shift_run_at and self.running and self.plan is not None
                and self.mode in ("practice", "perform")
                and self.midi.connected and not self.preview_only
                and self.pause_context == "playing"
                and not had_reading_lead
                and self.visual_transport.run_at <= now):
            lead_beats = max(1.0, min(4.0, self.count_in_bar_beats))
            lead_seconds = lead_beats * 60.0 / self.plan.bpm
            self.visual_transport.run_at += lead_seconds
            self._resume_grading_after = now + lead_seconds
            self.count_in_beats = lead_beats
        self.measurement.event("timeline_resume", {
            "scheduled_origin_before": previous_origin-self.measurement.origin,
            "scheduled_origin_after": self.visual_transport.run_at-self.measurement.origin,
            "shift_run_at": shift_run_at})
        resumed_count_in = self.running and (
            now < self.visual_transport.run_at or now < self._resume_grading_after)
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
        apply_stage_change(p, change, warmup=self.is_builtin_warmup)
        if action == "hand":
            self.open_from_beat = 0.0
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if not change.tempo_only:
            self.score_revision+=1
        self.feedback="Ready"
        self.next_action="Start when you are ready."
        continuation = guided_reentry(
            change=change, was_guided=was_guided,
            course_guided=self.course_guided,
            previous_return=guided_return, current_stage=p.identity)
        if continuation.route == "same_fragment":
            if continuation.recovery:
                self.retry_range = guided_retry_range
            self._begin_learn(
                from_beat=guided_start, bump_revision=False,
                recovery=continuation.recovery)
        elif continuation.route == "course":
            self._begin_course_stage(
                bump_revision=False, explicit_learn=continuation.explicit_learn)
        elif continuation.route == "fresh":
            self._begin_learn(bump_revision=False)
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

    def _mastery_candidate(self, result):
        """Exact next step eligible for an automatic clean-run advancement."""
        if (not self.auto or result is None or not getattr(result, "passed", False) or
                self.plan is None or self.plan.bpm < self.plan.target_bpm or
                self.plan.streak + 1 < SETTINGS.clean_runs_to_master):
            return None
        return self._next_stage_selection()

    def _advance_pending_feedback(self, now: float, *, prepared_on_time: bool = False):
        """Commit finished feedback and schedule exactly one next transition."""
        if self.auto and self.visual_transport.next_at and now >= self.visual_transport.next_at:
            # Keep the current music axis moving until authentic next-step ink
            # is compiled, acknowledged, and adoptable. A cache miss is never
            # allowed to change the score revision and blank the viewport.
            upcoming = self._mastery_candidate(self.pending_result)
            if upcoming is not None:
                selection, _number = upcoming
                accepted = self._future_stage_ready == (
                    selection.stage_key, selection.revision)
                prebuilt = (self.future_score.adopt(selection)
                            if accepted and self.future_score.ready(selection) else None)
                prepared = prebuilt is not None
                if not prepared:
                    self._stage_handoff_assets = None
                    failure = self.future_score.failure(selection)
                    reported = self._native_preload_failure
                    if (reported is not None and reported[:4] == (
                            self.fingerprint, selection.revision,
                            selection.stage_key, _number)):
                        failure = failure or reported[4]
                    if accepted and self.future_score.ready(selection):
                        failure = failure or "Prepared stage assets were lost"
                    if failure is not None:
                        # A genuinely unengraveable exercise must fail visibly,
                        # without trying to grade unrendered or stale notation.
                        self.visual_transport.pause(at=now)
                        self.visual_transport.next_at = 0.0
                        self.feedback = "Cannot prepare the next lesson score"
                        self.next_action = (
                            f"{failure}. Select another step or reopen the piece.")
                        return
                    self._stage_handoff_visual_beat = None
                    self.visual_transport.next_at = now + .10
                    self.feedback = "Preparing the next lesson while scrolling"
                    return
                self._stage_handoff_assets = (selection.identity, prebuilt)
                if self._stage_handoff_visual_beat is None and not prepared_on_time:
                    # Reserve a two-beat reading runway when assets arrive
                    # after the natural handoff. The existing score keeps
                    # scrolling through this gap at the authoritative BPM.
                    self._stage_handoff_visual_beat = self._visual_motion(now)[0] + 2.0
                    self.visual_transport.next_at = now + 2.0 * 60.0 / self.plan.bpm
                    return
            deadline = self.visual_transport.next_at
            previous_revision = self.score_revision
            previous_identity = self.plan.identity
            try:
                message = self._commit_pending()
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
            route = select_feedback_route(FeedbackFacts(
                automatic=self.auto, has_remediation=assignment is not None,
                same_stage=self.plan.identity == previous_identity,
                coda=self.plan.exercise_strategy.name == "coda-part",
                course_guided=self.course_guided,
                score_changed=self.score_revision != previous_revision,
                message=message))
            # Exact, precompiled source-bound ink is already on the screen,
            # including after guided-origin practice. This fast path must be
            # checked BEFORE the ordinary guided-stage reentry, or the latter
            # reopens a lesson and interrupts the scrolling view.
            if (route in ("await_score", "guided_stage") and
                    self._prepared_stage_published and
                    self._future_stage_ready ==
                    (self.plan.identity, self.score_revision)):
                self._future_stage_ready = None
                self._prepared_stage_published = False
                self._continue_at(deadline)
                return
            self._prepared_stage_published = False
            selected_retry = self._policy_retry
            self._policy_retry = None
            if selected_retry is not None and selected_retry[0] == self.plan.identity and self.auto:
                self._remediation_pending = None
                self._apply_policy_response(selected_retry[1], now=now, deadline=deadline)
                return
            if route == "remediation":
                self._start_remedial_assignment(assignment,deadline=deadline)
                return
            if route == "guided_stage":
                self._begin_course_stage()
                return
            if route == "await_score":
                self.awaiting_score_revision = self.score_revision
                self.auto = False
                self.feedback = "Preparing next passage"
                self.visual_transport.next_at = 0
            elif route == "continue":
                # Failed attempts reuse the existing source; clean attempts
                # append another passage with the exact authored rest gap.
                if not self.visual_transport._retry_previous_pass:
                    self.visual_transport.visual_offset_beats += self._source_model()[
                        "practice_timeline"]["stride_beats"]
                target = (self.visual_transport.practice_preparation["source_from_beat"]
                          if self.visual_transport._retry_previous_pass and self.visual_transport.practice_preparation else 0.0)
                self._continue_at(deadline, from_beat=target)
            else:
                self.visual_transport.next_at = 0
                self.auto = False
                self.feedback = message or self.feedback
        return

    def _start_remedial_assignment(self, assignment: RemedialAssignment,
                                   *, deadline: float | None = None) -> None:
        """Present an automatic remedial range without ever waiting for a key.

        A manually chosen guided lesson keeps the existing note-finding flow.
        An automatic rhythmic session always gets a scored, meter-bounded
        section that returns to the full passage after its recovery rest.
        """
        if self.plan is None or assignment.stage_key != self.plan.identity:
            return
        automatic = deadline is not None and self.auto and self.mode == "practice"
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
            self._continue_at(deadline,from_beat=review.start_beat)
            return
        if assignment.guided:
            self._begin_learn(
                from_beat=assignment.start_beat, recovery=True,
                remediation=assignment)
            self.feedback = "Reviewing recurring pitch mistakes"
        else:
            self._prepare_practice()
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
        tempo_map = self._active_tempo_map()
        assessed = self.assessment_policies.select(tempo_map).grade(
            phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.visual_transport.play_from_beat, end_beat=decision.end_beat,
            tempo=tempo_map)
        transition = plan_rolling_recovery(
            decision, identity=self.plan.identity, bpm=self.plan.bpm,
            previous_key=self._trouble_key, previous_count=self._trouble_count,
            grid=grid, first_bar=phrase.first_bar, now=now,
            # Automatic rhythmic playback never enters a note-by-note lesson
            # that waits indefinitely for input. Learn remains user-selectable.
            allow_guided=not self.auto,
            strategy=self.library.settings["mistake_response_strategy"],
            context=(self._retry_context(assessed, end_beat=decision.end_beat)
                if resolve_mistake_policy(self.library.settings["mistake_response_strategy"]).rolling_handler is not None else None))
        unsafe_focus = False
        if transition.action == "isolate":
            from .application.mistake_responses import WholeResponse
            selected = self._source_safe_response(WholeResponse(transition.bpm,
                transition.restart_beat, transition.mode, decision.end_beat, action="isolate"))
            unsafe_focus = selected.restart_beat != transition.restart_beat or selected.end_beat != decision.end_beat
        if transition.action == "continue" or unsafe_focus:
            from .measure_grid import next_chunk_end
            following = next_chunk_end(grid, decision.end_beat)
            self.next_boundary_beat = following if following > decision.end_beat+1e-7 else 0.
            return
        self.measurement.seal(self.recorder.presses if self.recorder else (),
            state="interrupted", reason="rolling_recovery", result=assessed,
            extra={"assessed_end_beat": decision.end_beat})
        if not self.measurement.decisions:
            self.measurement.decision({"trigger": "rolling", "policy":
                self.library.settings["mistake_response_strategy"],
                "policy_version": "registered-recovery-v1",
                "reason": "wrong_missed_threshold", "eligible": True,
                "parameters": mistake_policy_facts(resolve_mistake_policy(self.library.settings["mistake_response_strategy"])),
                "trigger_evidence": asdict(decision), "selected": asdict(transition),
                "before_bpm": self.plan.bpm, "after_bpm": transition.bpm,
                "wrong_missed_source_ids": [n.note.source_id for n in assessed.notes
                                             if n.status in ("wrong", "missed")],
                "origin": "automatic", "state": "applied"})
        before = (self.plan.streak, self.plan.failures, self.plan.bpm)
        try:
            with self.measurement.atomic():
                self.measurement.persist()
                if self.fingerprint:
                    unit = next((unit for unit in guided_units(self.plan.active_variant, self.plan.piece.bar_boundaries)
                        if unit["start_beat"] == decision.restart_beat and unit["end_beat"] == decision.end_beat), None)
                    if unit is not None:
                        self.learner_progress.record_rolling_trouble(
                            fingerprint=self.fingerprint, stage_key=self.plan.identity,
                            unit=unit, assessed_notes=assessed.notes, phrase_start=phrase.start)
                self.plan.streak = 0
                self.plan.failures += 1
                self.plan.bpm = transition.bpm
                self._save()
        except Exception:
            self.plan.streak, self.plan.failures, self.plan.bpm = before
            self._pending_rolling = (decision, phrase, grid, score_beat, now)
            self.running = self.auto = False
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=now)
            self.feedback = "Could not save the retry evidence"
            self.next_action = "Check storage, then press Retry to save this same attempt."
            raise
        self._pending_rolling = None
        self.measurement.finish()
        self._schedule_preparation(transition.restart_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds)
        self._trouble_key = transition.trouble_key
        self._trouble_count = transition.trouble_count
        self._guided_recovery_pending = transition.guided
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
        if self.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.measurement.seal((), state="completed", reason="preview")
            with self.measurement.atomic():
                self.measurement.persist()
            self.measurement.finish()
            self.running = False
            self.visual_transport._preview_loop_pending = True
            self.visual_transport.next_at = repeat_deadline(
                run_at=self.visual_transport.run_at, duration=duration,
                gap_beats=self.visual_transport.visual_gap_beats, bpm=self.plan.bpm)
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
            layout_for_feedback=lambda: self.engraving().layout)
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
        policy = resolve_mistake_policy(self.library.settings["mistake_response_strategy"])
        if (route in ("section_review", "partial_recovery") and self.auto
                and policy.whole_handler is not None and self.measurement.parent_decision is not None):
            response = whole_response(policy, result, phrase=phrase,
                grid=self.attempt_progression.grid_for(phrase, self.plan.piece.bar_boundaries),
                bpm=self.plan.bpm, minimum_bpm=SETTINGS.minimum_bpm,
                play_from_beat=self.visual_transport.play_from_beat,
                context=self._retry_context(result, end_beat=ending))
            response = self._source_safe_response(response)
        if route != "full_passage":
            previous_bpm = self.plan.bpm
            try:
                with self.measurement.atomic():
                    if response is not None:
                        self._record_policy_response(response, result, trigger="focused_take")
                        self.plan.bpm = response.bpm
                    self.measurement.persist()
                    if response is not None:
                        self._save()
                    if route == "perform":
                        self._save_performance_feedback(phrase, result, summary)
            except Exception:
                self.plan.bpm = previous_bpm
                raise
            self.measurement.finish()
        self.feedback_marks = assessed.marks
        self.feedback_unmapped = assessed.unmapped
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
            self._finish_partial_recovery(result, now)
        else:
            self._finish_full_passage(result, total_beats, duration, now)

    def _save_performance_feedback(self, phrase: Phrase, result, summary: dict):
        """Join original-source trouble feedback to the exposure's savepoint."""
        if self.fingerprint:
            if result.clean:
                self.learner_progress.resolve_trouble(
                    fingerprint=self.fingerprint, stage_key=self.plan.identity)
            else:
                for unit in summary["weakest_bars"]:
                    self._record_saved_trouble(phrase, result, start=unit["start_beat"],
                                              end=unit["end_beat"], errors=unit["errors"])

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

    def _finish_partial_recovery(self, result, now: float):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.review_end_beat = None
        self._automatic_remedial_review = False
        self.open_from_beat = 0.0
        self._schedule_preparation(0.0, now=now,
            from_visual=self.visual_transport.visual_offset_beats + self.visual_transport.play_from_beat
                + self._elapsed_beat(now-self.visual_transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.feedback = "Selected section finished · " + result.summary
        self.next_action = "Next: play the whole passage from its beginning to earn mastery."
        self.retry_range = None

    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        """Settle a full take using independent transport decisions."""
        decision = plan_full_passage(
            accepted=result.passed,
            automatic=self.auto, warmup=self.is_builtin_warmup,
            retry_pending=self.visual_transport._retry_previous_pass,
            run_at=self.visual_transport.run_at, duration=duration, total_beats=total_beats,
            gap_beats=self.visual_transport.visual_gap_beats, bpm=self.plan.bpm,
            feedback_seconds=self.feedback_seconds)
        self.pending_result = result
        # The response policy may slow the next retry before this take is
        # committed. Durable evidence must retain the tempo actually assessed.
        self._pending_assessed_bpm = self.plan.bpm
        whole_recovery = None
        assessed_bpm = self.plan.bpm
        if decision.rewind and not self.is_builtin_warmup:
            policy = resolve_mistake_policy(self.library.settings["mistake_response_strategy"])
            whole_recovery = whole_response(
                policy,
                result, phrase=self.plan.active_phrase,
                grid=self.attempt_progression.grid_for(
                    self.plan.active_phrase, self.plan.piece.bar_boundaries),
                bpm=self.plan.bpm, minimum_bpm=SETTINGS.minimum_bpm,
                play_from_beat=self.visual_transport.play_from_beat,
                context=self._retry_context(result) if policy.whole_handler is not None else None)
            if policy.whole_handler is not None:
                whole_recovery = self._source_safe_response(whole_recovery)
        if decision.rewind:
            # Preserve the original, assessed take before changing tempo.
            visual_from = self._visual_motion(now)[0]
            if whole_recovery is not None and policy.whole_handler is not None:
                self._record_policy_response(whole_recovery, result, trigger="full_take")
                self._policy_retry = self.plan.identity, whole_recovery
            else:
                self.measurement.decision({"trigger": "full_take",
                "policy": self.library.settings["mistake_response_strategy"],
                "policy_version": "registered-recovery-v1",
                "reason": "full_take_not_accepted", "eligible": True,
                "parameters": mistake_policy_facts(resolve_mistake_policy(self.library.settings["mistake_response_strategy"])),
                "before_bpm": assessed_bpm,
                "after_bpm": whole_recovery.bpm if whole_recovery else assessed_bpm,
                "restart_beat": whole_recovery.restart_beat if whole_recovery else 0.0,
                "wrong_missed_source_ids": [n.note.source_id for n in result.notes
                                             if n.status in ("wrong", "missed")],
                    "origin": "automatic", "state": "applied"})
            if whole_recovery is not None:
                self.plan.bpm = whole_recovery.bpm
            self.visual_transport._retry_previous_pass = True
            self._schedule_preparation(
                (whole_recovery.restart_beat if whole_recovery is not None
                 else self.visual_transport.play_from_beat), now=now,
                from_visual=visual_from,
                reverse_seconds=decision.rewind_seconds)
        if decision.failed:
            self.plan.streak = 0
        if decision.stop_auto:
            self.auto = False
            self.visual_transport.cancel_preparation()
        self.next_action = next_full_attempt(self.plan, result)
        if (whole_recovery is not None and not result.passed and
                whole_recovery.restart_beat >
                    self.visual_transport.play_from_beat + 1e-7):
            # A partial retry never awards mastery; the original take must
            # be proven clean over the full passage afterward.
            self.next_action = (
                "Repeat the difficult measure at %d BPM, then play the "
                "whole passage." % whole_recovery.bpm)
        elif whole_recovery is not None and whole_recovery.bpm < assessed_bpm:
            self.next_action = "Retry more slowly at %d BPM." % whole_recovery.bpm
        # A fully pre-rendered next stage on the third accepted target-speed
        # take is allowed to advance on the first post-grading tick. Failed
        # attempts, lower BPM clean repetitions and unprepared stages keep
        # the existing musical rewind/rest schedule.
        planned = self._mastery_candidate(result)
        if planned is not None:
            selection, _number = planned
            if (self._future_stage_ready ==
                    (selection.stage_key, selection.revision) and
                    self.future_score.ready(selection)):
                self.visual_transport.next_at = now
                self._advance_pending_feedback(now, prepared_on_time=True)
                return
        if decision.deadline_action == "clear":
            self.visual_transport.next_at = 0
        elif decision.deadline_action == "schedule":
            self.visual_transport.next_at = decision.deadline_at
            if now >= self.visual_transport.next_at:
                self._update()

    def _assess_rolling_boundary(self, boundary: float,
                                 grid: tuple[float, ...]):
        """Grade one authored boundary under the existing session lock."""
        try:
            self.measurement.checkpoint(self.recorder.presses if self.recorder else (), boundary=boundary)
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=time.monotonic())
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
            self._continue_at(deadline)
        elif decision.action == "feedback":
            self._advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self._guided_recovery_pending:
                self._begin_learn(from_beat=self.visual_transport.pending_rewind, recovery=True)
            else:
                self._continue_at(self.visual_transport.next_at, from_beat=self.visual_transport.pending_rewind)
        return decision.consumed

    def _update(self) -> None:
        try:
            self._update_transition()
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=time.monotonic())
            self.feedback = "Could not save or finish the practice transition"
            self.next_action = "Check storage or the reported error, then Resume to retry this same take."
            raise

    def _update_transition(self) -> None:
        """Advance the backend clock under its existing session lock."""
        self._poll_midi_connection()
        self._apply_listen_failure()
        now = time.monotonic()
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
            coda=self.plan.exercise_strategy.name == "coda-part",
            bpm=self.plan.bpm, gap_beats=self.visual_transport.visual_gap_beats),
            self._assess_rolling_boundary, self._elapsed_seconds)
        self.next_boundary_beat = step.next_boundary
        if step.action == "recovery":
            self._apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            self._complete_attempt(phrase, step.ending,
                                   phrase.end-phrase.start, step.duration, now)

    def _phase(self, now: float) -> str:
        teaching_phase = None
        if not self.visual_transport.paused and self.mode == "learn" and self.teaching is not None:
            teaching_phase = ("loading" if self.awaiting_score_revision is not None
                              else self.teaching.snapshot(now=now)["phase"])
        if (self.running and not self.visual_transport.paused
                and now < self._resume_grading_after):
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
            return self.assessment_policies.select(tempo_map).live(
                p.active_phrase, hand=p.hand, bpm=p.bpm,
                played=self.recorder.presses if self.recorder else [],
                from_beat=self.visual_transport.play_from_beat, elapsed_seconds=elapsed_seconds,
                bar_boundaries=p.piece.bar_boundaries,
                layout=engraving.layout, tempo=tempo_map)
        except (ValueError, RuntimeError, KeyError):
            return []

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
                while self._deferred_midi:
                    message, received_at, corrected_at, _transport = self._deferred_midi.popleft()
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
        began = time.perf_counter()
        try:
            return self._state_snapshot()
        finally:
            self.runtime_timings.state_ms.append(
                (time.perf_counter()-began)*1000.0)

    def _state_snapshot(self) -> dict:
        with self.lock:
            self._update()
            state = project_session_state(self._capture_session_snapshot())
            state["mistake_response_strategy"] = self.library.settings["mistake_response_strategy"]
            if self._stage_handoff_visual_beat is not None:
                state["next_stage_start_beat"] = self._stage_handoff_visual_beat
            if self.plan is not None:
                beat = self.plan.active_phrase.start + self.visual_transport.play_from_beat
                if self.running and time.monotonic() >= self.visual_transport.run_at:
                    beat += self._elapsed_beat(time.monotonic() - self.visual_transport.run_at)
                keys = [key for key in self.plan.piece.key_signatures
                        if key.beat <= beat + 1e-7
                        and key.hand in ("both", self.plan.hand)]
                state["key_fifths"] = keys[-1].fifths if keys else 0
            # A score-free Settings screen still needs an authoritative
            # backend clock epoch for its MIDI tap calibration. Midpoint-only
            # UI extrapolation drifts when score and device requests queue.
            calibration_sample_at = time.monotonic()
            state.setdefault("clock_sampled_at_ms", calibration_sample_at * 1000.0)
            state["midi_offset_ms"] = self.library.settings["midi_offset_ms"]
            state["resume_count_in_beat"] = (
                (calibration_sample_at - self._resume_grading_after)
                * self.plan.bpm / 60.0
                if self.running and not self.visual_transport.paused
                and calibration_sample_at < self._resume_grading_after
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
            live_feedback=self._live_feedback,
            visual_motion=self._visual_motion,
            active_tempo_map=self._active_tempo_map,
            display_phrase=self.display_phrase,
            guided_marks=self._guided_marks,
            listen_snapshot=self.listen.snapshot,
            live_input_snapshot=self.live_input.snapshot,
            preparation_schedule=self.visual_transport.preparation_schedule,
            teaching_snapshot=self.teaching.snapshot if self.teaching is not None else None,
            set_visual_gap_beats=self._set_snapshot_visual_gap,
        )
        return capture_session_snapshot(values, reads)

    def _next_stage_selection(self, *, offset: int = 1) -> tuple[ScoreSelection, int] | None:
        """Snapshot an upcoming lesson without mutating its active cursor."""
        if self.plan is None or self.is_builtin_warmup or self.mode != "practice":
            return None
        import copy
        p = self.plan
        number = p.lesson_step_number + offset
        if number > len(p.lesson_steps):
            return None
        future = copy.copy(p)
        future.stage_tempos = p.stage_tempos.copy()
        future.transferable_tempos = p.transferable_tempos.copy()
        future.mastered = p.mastered.copy()
        future.select_step(number)
        return ScoreSelection(
            piece=future.piece, phrase=future.active_phrase,
            hand=future.hand, stage_key=future.identity,
            revision=self.score_revision + offset, fingerprint=self.fingerprint,
            transformed_rhythm=future.active_stage.transformed_rhythm,
            display_name=str(future.active_stage.display_name or "")), number

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
            future_step = self.plan.lesson_steps[number - 1]
            label = self._stage_runway_label(future_step, selection.display_name)
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
                                    revision: int) -> dict:
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
            self._future_stage_ready = (stage_key, revision)
            # If the future ink became ready during the existing rest gap,
            # schedule its exact delayed start immediately. Waiting for the
            # old full-bar deadline would show native ink on a false origin.
            if (self.pending_result is not None and self.auto and
                    not self.running and not self.visual_transport.paused and
                    self._mastery_candidate(self.pending_result) is not None):
                now = time.monotonic()
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

    def semantic_score(self) -> dict:
        with self.lock:
            return self.score_artifacts.semantic_score(self._score_selection())

    def engraving(self) -> EngravedScore:
        with self.lock:
            return self.score_artifacts.engraving(self._score_selection())

    def geometry(self) -> dict:
        """Publish the selected native score and semantic asset revision."""
        with self.lock:
            return self.score_artifacts.geometry(self._score_selection())

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.learner_progress.lesson_overview(
                self.plan, fingerprint=self.fingerprint)


