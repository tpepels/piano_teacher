"""Piano practice engine embedded directly into the Godot process.

Owns the MIDI, grading, lessons, notation and persistent library state.
Communication with Godot uses an in-memory native command queue.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from collections import deque
from concurrent.futures import ThreadPoolExecutor
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
from .application import practice_flow
from .application.playback_coordinator import PlaybackCoordinator
from .application.playback_session import PlaybackSession
from .application.playback_transitions import CountInPlan
from .application.playback_facts import (
    PlaybackSourceFacts, PlaybackRuntimeFacts, TimedTakeSource, TimedStartRequest,
    PreparationRequest, ResumeRequest, FullPassageFacts, RestResumeFacts, PreloadedFeedbackSource,
)
from .application.flow_course_session import PracticeFlowCourseSession
from .application.passage_outcome_presenter import performance_next_action
from .application.learning_evidence_session import LearningEvidenceSession
from .application.source_preparation_session import SourcePreparationSession
from .application.score_state_publisher import ScoreStatePublisher, ScoreProjectionFacts
from .application.headless_score_projection import project_headless_score_queue
from .application.attempt_settlement import AttemptSettlement
from .application.attempt_runtime import AttemptRuntime
from .application.recovery_streak import RecoveryStreak
from .application.session_commands import SessionCommands
from .application.source_identity import SourceIdentity
from .application.lesson_cursor import LessonCursor
from .application.session_notices import SessionNotices
from .application.session_lifecycle import SessionLifecycle
from .application.history_management import HistoryManagement
from .application.source_workflows import SourceWorkflows
from .application.policy_registry import PolicyRegistry
from .application.settings_workflows import SettingsWorkflows
from .application.device_workflows import DeviceWorkflows
from .application.teaching_workflows import TeachingDecisions
from .application.session_evidence_context import SessionEvidenceContext
from .application.exposure_installer import ExposureInstaller
from .application.exposure_workflows import ExposureWorkflows
from .application.lesson_execution import LessonExecution
from .application.teaching_continuation import (
    TeachingContinuation, UnpreparedNextStage, FeedbackWaiting, FeedbackFault,
    SettledSourceFacts, EnterSelectedExposure, ApplySelectedResponse,
    EnterSelectedRemediation, ContinueSelectedScore,
)
from .application.musical_scheduler import (
    SCHEDULER, SNAPSHOT_LATENCY_SECONDS,
    RestMeasurement, ContinuationMeasurement,
)

from .sqlite_transaction import sqlite_atomic
from .application.score_artifacts import ScoreArtifacts, ScoreSelection
from .application.score_artifact_registry import ScoreArtifactRegistry
from .application.future_score import FutureScore
from .application.midi_connection import MidiConnection, MidiNotice
from .application.midi_key_shortcuts import MidiKeyShortcuts
from .application.midi_ingress import MidiIngress, MidiInputFacts, InputTransportFacts
from .application.listen_session import ListenSession
from .application.exposure_preparation import (
    ExposureSource, GuidedPreparation, TimedPreparation, ListenPreparation,
    prepare_guided, prepare_timed, prepare_listen, prepare_response, prepare_remedial,
)
from .importing.pieces import import_piece
from .engraving.engraving import EngravedScore
from .fingering import FingeringService
from .library import ScoreLibrary
from .preprocessing_cache import PreprocessingCache
from .library_health import LibraryHealth
from .warmups import is_warmup
from .application.mistake_responses import resolve_mistake_policy
from .music import Phrase
from .measure_grid import phrase_grid
from .course_navigation import choose_source_opening
from .state_projection import (
    PhaseSnapshot, SessionSnapshot, project_phase, project_session_state,
)
from .assessment_service import AssessmentService
from .application.practice_assessment import PracticeAssessmentPolicies
from .application.control_dispatch import ControlDispatcher
from .application.stage_change import prepare_stage_change
from .application.practice_transitions import TransitionContext, decide_transition
from .application.attempt_progression import AttemptProgression, AttemptTick
from .application.guided_session import GuidedSession
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
from .live_feedback import live_scope
from .runtime_timings import RuntimeTimings
from .live_input_view import LiveInputView
from .learner_state import guided_units
from .progress_repository import ProgressRepository
from .application.learner_progress import LearnerProgress
from .lesson_settings import SETTINGS
from .application.learning_capture import LearningCapture, CapturePhaseFacts, identifier

from .practice_history import PracticePolicyService
from .fukuda_mistake_store import FukudaMistakeStore
from .remediation import RemedialAssignment


class PracticeEngine:
    # Public observations of independently owned application session facts.
    @property
    def plan(self) -> LearningPlan | None:
        return self.source_identity.plan

    @property
    def assessment_policies(self) -> PracticeAssessmentPolicies:
        return self.policy_registry.grading

    @property
    def practice_policy(self) -> PracticePolicyService:
        return self.policy_registry.learning

    @property
    def score_artifacts(self) -> ScoreArtifacts:
        return self.score_artifact_registry.current

    @property
    def source(self):
        return self.source_identity.source

    @property
    def is_builtin_warmup(self) -> bool:
        return self.source_identity.warmup

    @property
    def fingerprint(self) -> str:
        return self.source_identity.fingerprint

    @property
    def score_revision(self) -> int:
        return self.source_identity.revision

    @property
    def open_from_beat(self) -> float:
        return self.lesson_cursor.opening_beat

    @property
    def course_guided(self) -> bool:
        return self.lesson_cursor.course_guided

    @property
    def feedback(self) -> str:
        return self.notices.feedback

    @feedback.setter
    def feedback(self, value: str) -> None:
        self.notices.feedback = value

    @property
    def next_action(self) -> str:
        return self.notices.next_action

    @next_action.setter
    def next_action(self, value: str) -> None:
        self.notices.next_action = value

    @property
    def _remediation_active(self) -> RemedialAssignment | None:
        return self.attempt.remediation_active


    @property
    def teaching(self):
        return self.guided_session.controller

    @property
    def persistent_hints(self) -> bool:
        return self.guided_session.persistent_hints

    # Public transport observations; only PlaybackSession stores these flags.
    @property
    def running(self):
        return self.playback_session.running

    @property
    def mode(self):
        return self.playback_session.mode

    @property
    def auto(self):
        return self.playback_session.auto

    @property
    def preview_only(self):
        return self.playback_session.preview_only

    @property
    def transport_id(self):
        return self.playback_session.transport_id

    @property
    def count_in_beats(self):
        return self.playback_session.count_in_beats

    @property
    def count_in_bar_beats(self):
        return self.playback_session.count_in_bar_beats

    @property
    def count_in_meter(self):
        return list(self.playback_session.count_in_meter)

    @property
    def awaiting_score_revision(self):
        return self.playback_session.awaiting_score_revision

    @property
    def pause_context(self):
        return self.playback_session.pause_context

    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True,
                 feedback_events: FeedbackEventLog | None = None,
                 clock: Clock | None = None):
        # The one monotonic clock of this session; collaborators receive it.
        self.now: Clock = clock if clock is not None else monotonic
        self.lock = threading.RLock()
        self.guided_session = GuidedSession(clock=self.now)
        self.attempt = AttemptRuntime()
        self.recovery_streak = RecoveryStreak()
        self.source_identity = SourceIdentity()
        self.lesson_cursor = LessonCursor()
        self.notices = SessionNotices()
        self.visual_transport = VisualTransport(
            _visual_rewind_seconds=SETTINGS.feedback_seconds)
        self.playback = PlaybackCoordinator()
        self.playback_session = PlaybackSession()
        self.tempo_map_cache = TempoMapCache()
        self.attempt_progression = AttemptProgression()
        self.feedback_seconds = SETTINGS.feedback_seconds
        self.midi_calibration = MidiTapCalibration()
        # The single acknowledged note-feedback channel to the score: provisional
        # attack/release events and authoritative per-note assessments.
        self.feedback_events = (feedback_events if feedback_events is not None
                                else FeedbackEventLog())
        self.live_assessment = LiveAssessmentPublisher(self.feedback_events)
        self.runtime_timings = RuntimeTimings()
        # Musical clock resumes at its previous beat after a reading lead-in.
        # No MIDI attack during that lead-in can alter a graded attempt.
        # Graded musical position (seconds since run_at) at the Pause moment.
        # The graded timeline stands still there until grading resumes after
        # Resume's lead; see _musical_seconds (R1 F2).
        # Persistent trouble means two boundary failures in consecutive takes
        # at the same stage and source two-bar chunk. Only a clean full take
        # or explicit stage navigation resets the history.
        # Automatic remedial sections are timed source reviews, never an
        # input-blocking lesson. A partial review never awards mastery.
        # Practice flow lesson state: changed only through the transitions
        # of application/practice_flow.py (see _flow_execute).
        self.flow_session = PracticeFlowCourseSession(self.now)
        # One short on-screen message at a time: (serial, text, engine time).
        self.guided_session.clear_selection()
        self.guided_session.set_hints(False,now=self.now())
        self.midi = MidiConnection(enabled=enable_midi, clock=self.now)
        self.live_input = LiveInputView()
        self.assessment = AssessmentService()
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        self.midi_key_shortcuts = MidiKeyShortcuts(self.library.settings["midi_key_ranges"])
        self.library_health = LibraryHealth(self.library)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir
        self.listen = ListenSession(data_dir / "demo-audio", lock=self.lock)
        self.fingering = FingeringService(data_dir / "fingering")
        self.preprocessing = PreprocessingCache(data_dir / "preprocessed")
        self.score_artifact_registry = ScoreArtifactRegistry(ScoreArtifacts(self.preprocessing))
        future_score = FutureScore(data_dir / "preprocessed", clock=self.now)
        self.teaching_continuation = TeachingContinuation(future_score,self.visual_transport)
        # The untimed guided engine owns repeat presentation epochs; no
        # Godot-side guess about missed notes or lesson progression.
        self.score_state_publisher = ScoreStatePublisher()
        # Explicit backend-selected next take. Renderer may only enqueue this
        # source identity at this exact monotonic graded deadline.
        # Godot's empty-strip geometry (clear, header beats); None = no
        # renderer has reported it, keep the offscreen reading horizon.
        # (seconds, bpm) of the last finished take's end: the written rest
        # bar that follows it is printed from there at that tempo.
        # Global musical origin of a delayed, pre-engraved next stage.
        # Pin the renderer-acknowledged source assets through settlement.
        # Final native renderer failures are tied to one exact future step.
        self.progress = ProgressRepository(data_dir / "progress.db")
        # Keep the public db handle for LearnerStateStore and existing clients.
        self.db = self.progress.db
        self.measurement = LearningCapture(self.progress.ledger, clock=self.now)
        self.progress.ledger.prune(days=self.library.settings["evidence_retention_days"],
                                   budget_mib=self.library.settings["evidence_budget_mib"])
        self.fukuda_mistakes = FukudaMistakeStore(self.db)
        self.learner_store = self.progress.learner_store
        self.learner_progress = LearnerProgress(self.learner_store)
        self.policy_registry = PolicyRegistry(
            assessment=self.assessment, ledger=self.progress.ledger,
            settings=self.library.settings)
        self.midi_ingress = MidiIngress(self.midi,self.midi_calibration,self.midi_key_shortcuts,
            self.live_input,self.measurement,self.feedback_events)
        self.session_commands = SessionCommands()
        self.attempt_settlement = AttemptSettlement(self.progress, self.measurement,
            self.fukuda_mistakes, self.learner_progress)
        self.learning_evidence = LearningEvidenceSession(
            self.progress, self.library, self.measurement, self.midi,
            self.midi_calibration)
        self.source_preparation = SourcePreparationSession()
        self.playback_session.bind_transport(transport=self.visual_transport,
            midi=self.midi_ingress,attempt=self.attempt,
            settlement=self.attempt_settlement,measurement=self.measurement,
            continuation=self.teaching_continuation,live_input=self.live_input,
            assessment=self.live_assessment,progression=self.attempt_progression,
            listen=self.listen,clock=self.now)
        self.session_lifecycle = SessionLifecycle(
            playback=self.playback, playback_session=self.playback_session,
            attempt=self.attempt, settlement=self.attempt_settlement,
            midi_ingress=self.midi_ingress, visual_transport=self.visual_transport,
            continuation=self.teaching_continuation,
            guided_session=self.guided_session, live_input=self.live_input,
            listen=self.listen, measurement=self.measurement, clock=self.now)
        self.history_management = HistoryManagement(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, progress=self.progress, measurement=self.measurement,
            recovery_streak=self.recovery_streak, lifecycle=self.session_lifecycle,
            attempt_settlement=self.attempt_settlement, attempt=self.attempt,
            playback_session=self.playback_session, guided_session=self.guided_session,
            score_artifact_registry=self.score_artifact_registry,
            learning_evidence=self.learning_evidence, clock=self.now,
            data_dir=self._data_dir)
        self.source_workflows = SourceWorkflows(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, lifecycle=self.session_lifecycle,
            recovery_streak=self.recovery_streak,
            visual_transport=self.visual_transport,
            source_preparation=self.source_preparation,
            playback_session=self.playback_session, guided_session=self.guided_session,
            score_artifact_registry=self.score_artifact_registry,
            attempt=self.attempt, listen=self.listen,
            preprocessing=self.preprocessing, fingering=self.fingering,
            progress=self.progress, fukuda_mistakes=self.fukuda_mistakes,
            library=self.library, library_health=self.library_health,
            flow_session=self.flow_session, lock=self.lock, clock=self.now)
        self.settings_workflows = SettingsWorkflows(
            library=self.library, measurement=self.measurement,
            lifecycle=self.session_lifecycle, notices=self.notices,
            policy_registry=self.policy_registry,
            midi_key_shortcuts=self.midi_key_shortcuts,
            playback_session=self.playback_session,
            visual_transport=self.visual_transport, progress=self.progress,
            library_health=self.library_health, source_identity=self.source_identity)
        self.device_workflows = DeviceWorkflows(
            midi=self.midi, shortcuts=self.midi_key_shortcuts,
            live_input=self.live_input, lifecycle=self.session_lifecycle,
            guided_session=self.guided_session, notices=self.notices,
            playback_session=self.playback_session,
            calibration=self.midi_calibration, library=self.library,
            clock=self.now)
        self.teaching_decisions = TeachingDecisions(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            attempt=self.attempt, attempt_settlement=self.attempt_settlement,
            measurement=self.measurement, playback_session=self.playback_session,
            visual_transport=self.visual_transport,
            guided_session=self.guided_session, recovery_streak=self.recovery_streak,
            policy_registry=self.policy_registry, library=self.library,
            fukuda_mistakes=self.fukuda_mistakes,
            learner_progress=self.learner_progress,
            session_commands=self.session_commands,
            learning_evidence=self.learning_evidence, clock=self.now)
        self.evidence_context = SessionEvidenceContext(
            source_identity=self.source_identity, playback_session=self.playback_session,
            guided_session=self.guided_session, learning_evidence=self.learning_evidence)
        self.exposure_installer = ExposureInstaller(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, lifecycle=self.session_lifecycle,
            learner_progress=self.learner_progress, progress=self.progress,
            score_state_publisher=self.score_state_publisher,
            attempt=self.attempt, playback_session=self.playback_session,
            guided_session=self.guided_session, visual_transport=self.visual_transport,
            midi=self.midi, listen=self.listen, evidence_context=self.evidence_context,
            session_commands=self.session_commands, clock=self.now)
        self.exposure_workflows = ExposureWorkflows(
            source_identity=self.source_identity, flow_session=self.flow_session,
            teaching_decisions=self.teaching_decisions, session_commands=self.session_commands,
            guided_session=self.guided_session, attempt=self.attempt,
            tempo_map_cache=self.tempo_map_cache, playback_session=self.playback_session,
            listen=self.listen, notices=self.notices, installer=self.exposure_installer)

        self.lesson_execution = LessonExecution(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, teaching_decisions=self.teaching_decisions,
            exposure_workflows=self.exposure_workflows,
            exposure_installer=self.exposure_installer, flow_session=self.flow_session,
            playback_session=self.playback_session, guided_session=self.guided_session,
            attempt=self.attempt, learner_progress=self.learner_progress,
            progress=self.progress, lifecycle=self.session_lifecycle,
            recovery_streak=self.recovery_streak, visual_transport=self.visual_transport,
            attempt_settlement=self.attempt_settlement, measurement=self.measurement,
            library=self.library, clock=self.now, session_commands=self.session_commands)

    def require_presentation(self) -> None:
        with self.lock:
            self.playback.enable_presentation(self._playback_facts())

    def playback_status(self) -> dict:
        with self.lock:
            return self.playback.status()

    def reserve_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.reserve(self._playback_facts(),**values)

    def present_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.present(self._playback_facts(),
                commit=self._commit_playback_intent,capture=self._playback_facts,
                abort=self._abort_playback,**values)

    def withdraw_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.withdraw(self._playback_facts(),**values)

    def report_playback_failure(self, **values) -> dict:
        with self.lock:
            self.playback.fail(notify_failure=self._on_playback_failure,**values)
            return {"accepted":True}

    def _playback_facts(self, *, from_beat: float | None = None) -> PlaybackRuntimeFacts:
        """Frozen source, meter and transport facts; never hand over the engine."""
        source = None
        if self.plan is not None:
            plan = self.plan
            bar, meter = self.playback_session.count_in_bar_beats, tuple(self.playback_session.count_in_meter)
            if from_beat is not None:
                _, bar, meter = self.attempt_progression.count_in_bar(
                    phrase=plan.active_phrase,boundaries=plan.piece.bar_boundaries,
                    time_signatures=plan.piece.time_signatures,position=from_beat)
            tempo = self._active_tempo_map()
            segments = tuple((float(s["start_beat"]),float(s["end_beat"]),
                              float(s["bpm"])) for s in
                             (tempo.as_segments() if tempo is not None else ()))
            source = PlaybackSourceFacts(
                fingerprint=self.fingerprint,stage_key=plan.identity,
                revision=self.score_revision,hand=plan.hand,bpm=float(plan.bpm),
                end_beat=plan.active_phrase.sounding_end-plan.active_phrase.start,
                count_in_bar_beats=float(bar),count_in_meter=tuple(meter),
                tempo_segments=segments)
        return self.playback_session.facts(source)

    def _request_playback(self, *, from_beat: float, **kwargs):
        return self.playback.request(self._playback_facts(from_beat=from_beat),
                                     from_beat=from_beat,**kwargs)

    def _abort_playback(self, reason: str) -> None:
        self._stop(reason=reason)

    def _on_playback_failure(self, reason: str) -> None:
        if self.playback_session.running:
            self._stop(reason=reason)
        self.feedback = "The score stopped displaying correctly"
        self.next_action = "Select this lesson again after checking the score."

    def _midi_lost(self, reason: str = "device_disconnected") -> None:
        if self.plan is not None:
            self._prepare_teaching("interrupted", action=reason, store=False)
        self.device_workflows.disconnect(reason)

    def ports(self) -> list[str]:
        if not self.midi.enabled:
            return []
        with self.lock:
            scan = self.device_workflows.scan()
            if scan.lost:
                self._midi_lost()
            self.device_workflows.handle_scan_error(scan)
            self.device_workflows.restore_preferred(
                scan.names, callback=self._receive)
            return list(scan.names)

    def connect(self, name: str):
        with self.lock:
            self.device_workflows.select(name, callback=self._receive)
            self.set_preferences(midi_device=name)

    def hardware_diagnostics(self) -> dict:
        with self.lock:
            return self.device_workflows.hardware_diagnostics()

    def hardware_diagnostics_action(self, action: str) -> dict:
        with self.lock:
            return self.device_workflows.hardware_action(action)

    def library_listing(self) -> dict:
        with self.lock:
            return self.source_workflows.library_listing()

    def library_health_status(self) -> dict:
        return self.source_workflows.library_health_status()

    def start_library_health(self) -> dict:
        return self.source_workflows.start_library_health()

    def midi_calibration_action(self, action: str) -> None:
        with self.lock:
            changes = self.device_workflows.calibrate(
                action, stop_reason=self.session_commands.action_reason)
            if changes is not None:
                self.set_preferences(**changes)

    def preferences(self) -> dict:
        with self.lock:
            return self.settings_workflows.preferences()

    def _learning_context(self, *, scope: str, start: float, end: float,
                          run_at: float | None = None) -> dict:
        return self.evidence_context.build(
            scope=scope, start=start, end=end, run_at=run_at,
            tempo_map=self._active_tempo_map())

    def learning_history_status(self) -> dict:
        with self.lock:
            return self.history_management.status()

    def learning_statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        return self.history_management.statistics(fingerprint, query=query)

    def _retry_context(self, result, *, end_beat=None):
        return self.teaching_decisions.retry_context(result, end_beat=end_beat)

    def _apply_policy_response(self, response, *, now: float, deadline: float | None = None,
                               visual_from: float | None = None):
        """Apply registered source-bound decisions through the existing transport."""
        prepared = prepare_response(response,
            source_duration=self.plan.active_phrase.end-self.plan.active_phrase.start,
            has_deadline=deadline is not None)
        self.lesson_cursor.select_opening(prepared.start)
        self.attempt.prepare_recovery(prepared)
        if prepared.action == "pause":
            self.playback_session.stop_automatic()
            self.visual_transport.cancel_preparation()
            self.visual_transport.cancel_continuation()
            self.feedback = prepared.feedback
        elif prepared.action == "guided":
            self.lesson_execution.begin_learn(from_beat=prepared.start,recovery=True,
                exposure=self.attempt_settlement.pending.decision.next_exposure)
        elif prepared.action == "continue":
            self._continue_at(SCHEDULER.continuation(
                self._collect_continuation_measurement(deadline,prepared.start),
                now=self.now(),bpm=self._presentation_bpm),from_beat=prepared.start)
        else:
            self._schedule_preparation(prepared.start,now=now,
                from_visual=self._visual_motion(now)[0] if visual_from is None else visual_from,
                reverse_seconds=self.feedback_seconds)
        self.next_action = prepared.next_action

    def export_learning_history(self, path: str, include_detail: bool = False) -> dict:
        with self.lock:
            return self.history_management.export(path, include_detail=include_detail)

    def delete_piece_history(self, fingerprint: str, confirm: bool = False) -> dict:
        with self.lock:
            return self.history_management.delete_piece(fingerprint, confirm=confirm)

    def delete_learner_history(self, confirm: bool = False) -> dict:
        with self.lock:
            return self.history_management.delete_learner(confirm=confirm)

    def close(self) -> None:
        with self.lock:
            self.session_lifecycle.shutdown(
                midi=self.midi, progress=self.progress, receive=self._receive)

    def set_preferences(self, **changes) -> dict:
        with self.lock:
            return self.settings_workflows.update(
                changes, pause_current=self._pause_current_session)

    def _active_tempo_map(self):
        """Reuse an immutable authored tempo map until stage or BPM changes.

        This runs on the 20 ms worker as well as during state snapshots.
        ExerciseStage.tempo_map() may transform every note, so rebuilding it
        for every clock read creates work proportional to the full passage.
        """
        if self.plan is None or self.playback_session.mode not in ("practice", "listen"):
            return None
        return self.tempo_map_cache.get(self.plan.active_stage, self.plan.bpm)

    def _elapsed_beat(self, elapsed_seconds: float) -> float:
        return SCHEDULER.elapsed_beats(
            self._active_tempo_map(),self.visual_transport.play_from_beat,
            elapsed_seconds,self.plan.bpm)

    def _elapsed_seconds(self, beat: float) -> float:
        tempo = self._active_tempo_map()
        return SCHEDULER.source_seconds(tempo,beat,self.plan.bpm)

    def exercise_diagnostics(self) -> dict:
        with self.lock:
            return self.settings_workflows.exercise_diagnostics(
                tempo_map=self._active_tempo_map())

    def load_library(self, identifier: str) -> None:
        with self.lock:
            path = self.source_workflows.resolve_library(identifier)
        warmup = is_warmup(identifier)
        self.load(str(path), warmup=warmup)
        with self.lock:
            self.source_workflows.mark_library_opened(identifier, warmup=warmup)

    def performance_diagnostics(self) -> dict:
        return self.runtime_timings.snapshot()

    def _receive(self, message):
        began = time.perf_counter()
        try:
            self._receive_message(message)
        finally:
            self.runtime_timings.midi_ms.append(
                (time.perf_counter()-began)*1000.0)

    def _midi_transport_facts(self) -> InputTransportFacts:
        """Snapshot only the transport gates needed by the one MIDI router."""
        return InputTransportFacts(
            next_at=self.visual_transport.next_at,
            preview_loop_pending=self.visual_transport.preview_loop_pending,
            pending_teaching_result=self.attempt_settlement.pending_result is not None,
            pending_rewind=self.visual_transport.pending_rewind is not None,
            automatic=self.playback_session.auto,preview_only=self.playback_session.preview_only,
            visual_gap_beats=self.visual_transport.visual_gap_beats,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            exercise_kind=(self.plan.exercise.kind if self.plan else ""),
            review_end_beat=self.attempt.review_end_beat,
            presentation_required=self.playback.presentation_required,
            successor_action=(self.playback.intent.action
                if self.playback.intent is not None else None))

    def _apply_midi_shortcut(self, effect) -> None:
        if effect.completed_range is not None:
            ranges = self.library.settings["midi_key_ranges"].copy()
            ranges[self.midi.device] = list(effect.completed_range)
            self.set_preferences(midi_key_ranges=ranges)
        if effect.action:
            self.control(effect.action)

    def _receive_message(self, message, *, received_at=None, corrected_at=None, deferred=False):
        now = self.now() if received_at is None else received_at
        with self.lock:
            facts = MidiInputFacts(self.fingerprint,self.score_revision,
                self.plan.identity if self.plan else "",self.plan.active_phrase if self.plan else None,
                self.plan.hand if self.plan else "both",self.plan.bpm if self.plan else 60.,
                self.playback_session.mode,self.playback_session.running,self.visual_transport.paused,self.playback_session.preview_only,
                self.visual_transport.play_from_beat,self.visual_transport.run_at,self.playback_session.transport_id,
                self._active_tempo_map(),self.playback_session.running or (self.playback_session.mode == "learn" and self.teaching is not None))
            self.midi_ingress.dispatch(
                message,facts=facts,received_at=now,
                corrected_at=corrected_at,deferred=deferred,
                midi_offset_seconds=self.library.settings["midi_offset_ms"]/1000.0,
                apply_shortcut=self._apply_midi_shortcut,
                transport_facts=self._midi_transport_facts,
                musical_seconds=self._musical_seconds,
                recorder=lambda: self.attempt.recorder,
                teaching=lambda: self.teaching,
                feedback_take=self._feedback_take)

    def load(self, path: str, *, warmup: bool = False):
        """Commit a prepared source under one mutation guard and short lock."""
        diagnostics = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = time.perf_counter()
        with self.source_preparation.source_mutation():
            prepared = self.source_workflows.prepare(
                path, warmup=warmup, diagnostics=diagnostics)
            with self.lock:
                resumed = self.source_workflows.install(prepared, warmup=warmup)
                if resumed is not None:
                    self.lesson_execution.flow_open(resumed=resumed)
        if diagnostics:
            print("SCORE_LOAD_STAGE: ready",
                  round((time.perf_counter()-began)*1000,1),
                  "ms total",prepared.path.name,flush=True)

    def fingering_status(self) -> dict:
        with self.lock:
            return self.source_workflows.fingering_status()

    def correct_fingering(self, source_id: str, finger: int | None,
                         *, fingerprint: str | None = None) -> None:
        return self.source_workflows.correct_fingering(
            source_id, finger, fingerprint=fingerprint)

    def _restore(self):
        self.progress.restore(self.plan, self.fingerprint)

    def _save(self):
        self.progress.save(self.plan, self.fingerprint)

    def _reset_current_path(self, *, fingerprint: str, confirm: bool) -> None:
        return self.history_management.reset_current_path(
            fingerprint=fingerprint, confirm=confirm)

    def _stop(self, *, reason: str | None = None, preserve_episode: bool = False,
              persist_evidence: bool = True):
        self.session_lifecycle.stop(
            reason=reason or self.session_commands.action_reason,
            preserve_episode=preserve_episode, persist_evidence=persist_evidence)

    # -- practice flow (docs/practice-flow.md) ---------------------------------
    @property
    def flow(self) -> practice_flow.FlowState | None:
        return self.flow_session.state

    def _exposure_source(self) -> ExposureSource:
        return self.exposure_workflows.source()

    def _apply_exposure_preparation(self, prepared:
            GuidedPreparation | TimedPreparation | ListenPreparation) -> None:
        return self.exposure_installer.apply(prepared)

    def display_phrase(self) -> Phrase:
        return self.lesson_execution.display_phrase()

    def _guided_marks(self, snapshot: dict) -> list[dict]:
        """Project current guided note identities through the owned fragment."""
        if self.plan is None:
            return []
        engraving = self.score_artifacts.cached_layout(self._score_selection())
        return (self.guided_session.marks(snapshot, engraving.layout)
                if engraving is not None else [])


    def _prepare_practice(self, *, exposure=None):
        return self.exposure_workflows.prepare_practice(exposure=exposure)

    def _apply_listen_failure(self) -> None:
        self.exposure_workflows.apply_listen_failure()

    def _prepare_listen(self):
        return self.exposure_workflows.prepare_listen()

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            return self.listen.audio_path(token)

    def _start_listen_if_ready(self):
        self._apply_listen_failure()
        activation = self.playback_session.begin_listen_if_ready(
            revision=self.score_revision,presentation_required=self.playback.presentation_required)
        if activation.requested_count_in is not None:
            self._request_playback(action="listen",mode="listen",from_beat=activation.from_beat,
                count_in_beats=activation.requested_count_in)
        elif activation.started:
            self.feedback = "Count in, then listen"

    def _prepare_perform(self, *, scope: str = "current", exposure=None):
        return self.exposure_workflows.prepare_perform(scope=scope, exposure=exposure)

    def _performance_review(self, phrase: Phrase, result) -> dict:
        """Retained engine API; assessment service owns report construction."""
        tempo = self._active_tempo_map()
        elapsed_to_beat = (None if tempo is None else
            lambda seconds: tempo.beat_at(tempo.seconds_at(self.visual_transport.play_from_beat)+seconds))
        return self.assessment.review(
            phrase, result, bar_boundaries=self.plan.piece.bar_boundaries,
            played_from_beat=self.visual_transport.play_from_beat, bpm=self.plan.bpm,
            elapsed_to_beat=elapsed_to_beat)

    def _teaching_binding(self):
        return self.teaching_decisions.binding()

    def _prepare_teaching(self, kind, result=None, *, rolling=None, manual=None, action=None,
                          from_beat=None, end_beat=None, store=True, values=None, completed=False, assisted_count=0):
        return self.teaching_decisions.prepare(
            kind, result, rolling=rolling, manual=manual, action=action,
            from_beat=from_beat, end_beat=end_beat, store=store,
            values=values, completed=completed, assisted_count=assisted_count)

    def _manual_effect(self, action, *, from_beat=None, values=None):
        return self.teaching_decisions.manual_effect(
            action, from_beat=from_beat, values=values)

    def _install_command(self, effect):
        return self.teaching_decisions.install_command(effect)

    @property
    def _presentation_bpm(self):
        pending = self.attempt_settlement.pending
        if pending is not None and pending.receipt is None and pending.decision.next_exposure is not None:
            return pending.decision.next_exposure.bpm
        return self.plan.bpm if self.plan is not None else 0

    def _commit_pending(self, *, finish_publication: bool = True) -> str:
        if self.attempt_settlement.pending_result is None or self.plan is None:
            return ""
        pending = self.attempt_settlement.pending
        decision = pending.decision
        try:
            committed = self.attempt_settlement.commit_full_passage(
                plan=self.plan,binding=self._teaching_binding(),now=self.now(),
                continuation=self.teaching_continuation,
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]),
                score_revision=self.score_revision,
                visual_offset=self.visual_transport.visual_offset_beats)
            outcome = committed.receipt
            self.attempt.apply_settlement(committed,plan=self.plan)
            if decision.verdict is not None and decision.verdict.clears_trouble:
                self.lesson_execution.reset_trouble()
            if outcome.stage_changed:
                self.lesson_cursor.select_opening(0.0)
                self.source_identity.publish_revision(committed.selection.revision)
                self.playback_session.wait_for_player()
                prebuilt = self.teaching_continuation.consume_committed_asset(
                    committed.prepared,changed=True,auto=self.playback_session.auto,
                    selection=committed.selection)
                if prebuilt is not None:
                    self.score_artifact_registry.adopt(prebuilt)
                else:
                    self.score_artifacts.invalidate()
                self.visual_transport.adopt_committed_stage(
                    committed,preserved=prebuilt is not None)
            else:
                self.teaching_continuation.consume_committed_asset(
                    None,changed=False,auto=self.playback_session.auto,selection=None)
        except BaseException:
            self.attempt.publication_failed()
            raise
        if finish_publication:
            self.attempt_settlement.finish_publication()
        self.attempt.publication_finished()
        return outcome.message

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float | None = None,
              presentation_lead_seconds: float = 0.0, decided: bool = False,
              count_in_plan=None):
        with self.lock:
            self.playback_session.require_authorized_start(self.playback.presentation_required)
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
                effect = self._prepare_teaching("manual",action="start",
                    from_beat=from_beat,store=False,values={"mode":mode})
            if effect is not None:
                selected = effect.decision.next_exposure
                if selected is None:
                    return
                self._install_command(effect)
            if selected is not None and selected.stage_key == self.plan.identity:
                from_beat,mode = selected.from_beat,selected.mode
            if self.playback_session.mode == "learn":
                self._prepare_practice(exposure=selected)
                return
            self.guided_session.clear_selection()
            self.guided_session.discard_return()
            p = self.plan
            started = self.playback_session.begin_timed(
                TimedTakeSource(p.active_phrase,p.piece.bar_boundaries,
                    p.piece.time_signatures,p.bpm,
                    self._source_model()["practice_timeline"]["gap"]["duration_beats"]),
                TimedStartRequest(mode=mode,
                    position=self.open_from_beat if from_beat is None else from_beat,
                    automatic=selected.automatic if selected is not None else mode == "practice",
                    connected=self.midi.connected,loop_continuation=loop_continuation,
                    scheduled_deadline=scheduled_deadline,
                    presentation_lead_seconds=presentation_lead_seconds,
                    count_in_plan=count_in_plan))
            self.visual_transport.next_boundary_beat = started.next_boundary_beat
            try:
                self.playback_session.capture_start(self._learning_context(
                    scope=started.scope,start=started.from_beat,end=started.end_beat,
                    run_at=started.run_at))
            except Exception:
                self.feedback = "Could not record the start of this attempt"
                raise
            self.feedback = "Count in, then play"
            self.next_action = started.next_action

    def _commit_playback_intent(self, intent, receipt) -> None:
        """Apply source effects at the coordinator's single authorization gate."""
        with self.playback_session.authorization(intent,receipt) as authorized:
            if authorized.action in ("start","restart"):
                selected = self._install_command(authorized.transition.effect)
                authorized.validate_installed(selected,intent)
                with self.session_commands.executing(authorized.transition.effect):
                    self.start(mode=selected.mode,from_beat=selected.from_beat,
                        scheduled_deadline=authorized.deadline,count_in_plan=intent.count_in)
            elif authorized.action == "resume":
                self._resume_current_session(
                    presentation_lead_seconds=max(0.0,authorized.deadline-self.now()),
                    reuse_pending_score=receipt.reused_count_in,
                    scheduled_deadline=authorized.deadline)
            elif authorized.action in ("auto","score_ready"):
                with self.session_commands.executing(None):
                    self.start(from_beat=intent.from_beat,mode=intent.mode,
                        loop_continuation=authorized.action == "auto",
                        decided=False,scheduled_deadline=authorized.deadline,
                        count_in_plan=intent.count_in)
                self.visual_transport.scheduled_start = (
                    self.playback_session.transport_id,self.visual_transport.play_from_beat,
                    self.visual_transport.run_at,self.plan.identity,self.score_revision,None)
            elif authorized.action == "listen":
                self.playback_session.start_listen(revision=self.score_revision,
                    count_in=intent.count_in,deadline=authorized.deadline)
                self.feedback = "Count in, then listen"

    def _next_count_in(self) -> tuple[float,tuple[int,int]]:
        plan = self.plan
        return self.attempt_progression.next_count_in(
            phrase=plan.active_phrase if plan is not None else None,
            boundaries=plan.piece.bar_boundaries if plan is not None else (),
            time_signatures=plan.piece.time_signatures if plan is not None else (),
            bpm=float(plan.bpm) if plan is not None else 0.0,
            start_from=self.open_from_beat,
            already_active=self.playback_session.running or self.visual_transport.paused,
            current_bar_beats=self.playback_session.count_in_bar_beats,
            current_meter=tuple(self.playback_session.count_in_meter))

    def _next_count_in_beats(self) -> float:
        return self._next_count_in()[0]

    def _next_count_in_meter(self) -> list[int]:
        return list(self._next_count_in()[1])

    def _continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Continue only through the unified score-admission gate."""
        if self.playback.presentation_required:
            self.playback_session.prepare_admitted_continuation()
            self._request_playback( action="auto", mode=self.playback_session.mode,
                from_beat=from_beat, earliest_deadline=deadline,
                fixed_deadline=deadline if self.lesson_execution.flow_active() else None)
            self.visual_transport.scheduled_start = None
            self.feedback = "Preparing the next passage"
            return
        announced = self.visual_transport.announced_deadline(from_beat)
        serial = (self.visual_transport.announce_serial
                  if announced is not None and abs(announced - deadline) <= 1e-9 else None)
        self.start(from_beat=from_beat, mode=self.playback_session.mode, loop_continuation=True,
                   scheduled_deadline=deadline,
                   count_in_plan=(CountInPlan.create(
                       bar_beats=self._next_count_in_beats(),
                       meter=tuple(self._next_count_in_meter()),bpm=self.plan.bpm,
                       beats=self._next_count_in_beats()) if self.lesson_execution.flow_active() else None))
        self.visual_transport.scheduled_start = (
            self.playback_session.transport_id, self.visual_transport.play_from_beat,
            self.visual_transport.run_at, self.plan.identity,
            self.score_revision, serial)
        self.playback_session.retain_announced_count_in(bpm=self.plan.bpm)

    def _collect_continuation_measurement(self, deadline: float,
                                          from_beat: float
                                          ) -> ContinuationMeasurement:
        """Sample queue and engraving facts; deadline calculus lives in SCHEDULER."""
        return ContinuationMeasurement(
            deadline=deadline,
            announced_at=self.visual_transport.announced_deadline(from_beat),
            rest_beats=self.visual_transport.visual_gap_beats,
            horizon_beats=self.visual_transport.continuous_horizon_beats,
            rest=self._collect_rest_measurement(
                from_beat=from_beat,
                source_end=deadline if self.visual_transport.rest_take_end is None else None),
            automatic=self.plan is not None and self.playback_session.auto)


    def _start_rate_bpm(self, from_beat: float, bpm: float) -> float:
        """Authored tempo-map rate at a take's first beat, at this BPM."""
        if self.plan is None or bpm <= 0 or self.playback_session.mode not in ("practice", "listen"):
            return float(bpm)
        tempo = self.tempo_map_cache.get(self.plan.active_stage, bpm)
        return float(tempo.bpm_at(from_beat)) if tempo is not None else float(bpm)

    def _schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float,
                              reading_lead_included: bool = False,
                              announce: bool = True,
                              short_deadline: float | None = None):
        self.playback_session.schedule_preparation(PreparationRequest(
            self._source_model(),target,now,from_visual,reverse_seconds,
            self._presentation_bpm,self.visual_transport.continuous_horizon_beats,
            reading_lead_included,announce,short_deadline))

    def _visual_motion(self, now: float) -> tuple[float, float, float]:
        """Read the one transport projection, including authored tempo and silence."""
        phrase = self.plan.active_phrase
        return self.visual_transport.position(
            now, phrase_length=phrase.sounding_end-phrase.start, bpm=self.plan.bpm,
            running=self.playback_session.running,
            pending_auto_result=(self.attempt_settlement.pending_result is not None and self.playback_session.auto),
            tempo_map=self._active_tempo_map())

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            previous_reason = self.session_commands.action_reason
            self.session_commands.action_reason = action
            before = {"fingerprint": self.fingerprint,
                      "stage_key": self.plan.identity if self.plan else None,
                      "bpm": self.plan.bpm if self.plan else None, "mode": self.playback_session.mode}
            effect = self.session_commands.active
            route = ControlDispatcher.route(action)
            if self.plan is not None and route in ("listening", "learning", "transport", "stage") and not (action in ("start","restart") and (self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None)):
                change = (prepare_stage_change(self.plan, action, kwargs, warmup=self.is_builtin_warmup)
                          if route == "stage" else None)
                effect = self._prepare_teaching("manual", manual=change,
                    action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
            try:
                with self.session_commands.executing(effect):
                    result = self._dispatch_control(action, **kwargs)
                    self._prepare_score_presentation()
                    if action not in ("score_ready", "demo_ready", "reset_path"):
                        self.measurement.event("manual_action", {"action": action,
                            "fingerprint": before["fingerprint"] or None,
                            "parameters": kwargs, "before": before,
                            "after": {"fingerprint": self.fingerprint,
                                      "stage_key": self.plan.identity if self.plan else None,
                                      "bpm": self.plan.bpm if self.plan else None, "mode": self.playback_session.mode}})
                    return result
            finally:
                self.session_commands.action_reason = previous_reason

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
                    if self.playback_session.running and not self.visual_transport.paused:
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
            revision = int(kwargs.get("revision",-1))
            decision = self.playback_session.score_acknowledged(revision,
                current_revision=self.score_revision,teaching_bound=self.teaching is not None)
            if decision == "listen":
                self._start_listen_if_ready()
            elif decision == "learn":
                self.teaching.start(now=self.now())
            elif decision == "practice":
                position = (self.visual_transport.pending_rewind
                    if self.visual_transport.pending_rewind is not None else self.open_from_beat)
                mode = "perform" if self.playback_session.mode == "perform" else "practice"
                if self.playback.presentation_required:
                    self._request_playback(action="score_ready",mode=mode,from_beat=position)
                    return
                announce = self.visual_transport.short_rest is not None or self.lesson_execution.flow_active()
                timing = self.playback_session.headless_ready_timing(
                    reserved_ms=kwargs.get("presentation_deadline_ms"),
                    count_in_beats=self._next_count_in_beats(),bpm=self.plan.bpm,
                    announce=announce,rest=(self._collect_rest_measurement(
                        from_beat=self.open_from_beat) if announce and
                        kwargs.get("presentation_deadline_ms") is None else None),
                    presentation_bpm=self._presentation_bpm)
                self.start(from_beat=position,mode=mode,scheduled_deadline=timing.deadline,
                    presentation_lead_seconds=timing.lead_seconds,decided=True)
                if announce:
                    self.visual_transport.scheduled_start = (
                        self.playback_session.transport_id,self.visual_transport.play_from_beat,
                        self.visual_transport.run_at,self.plan.identity,self.score_revision,None)
        elif self.playback_session.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self._start_listen_if_ready()

    def _control_listening(self, action: str, kwargs: dict) -> None:
        if action == "listen":
            if (self.lesson_execution.flow_active() and self.flow is not None
                    and self.flow.stage_key == self.plan.identity
                    and self.playback_session.mode != "listen"):
                # Listen again: the state machine plays it, then Free.
                self.lesson_execution.flow_execute(self.flow_session.listen_again())
            else:
                self._prepare_listen()
        elif action == "perform":
            self._prepare_perform(scope=str(kwargs.get("scope", "current")))
        elif action == "practice_weak":
            self.lesson_execution.practice_weak()
        elif action == "review_retry":
            self.lesson_execution.review_retry(kwargs.get("first_bar"), kwargs.get("last_bar"))
        elif action == "seek":
            self.lesson_execution.seek(kwargs.get("bar"))

    def _control_learning(self, action: str, kwargs: dict) -> None:
        if action == "learn_next":
            if (self.playback_session.mode != "learn" or self.teaching is None
                    or not self.teaching.snapshot(now=self.now())["completed"]):
                raise ValueError("Find the current notes before continuing to the next idea")
            self.lesson_execution.save_guided_preparation()
            if self.guided_session.return_context is not None:
                self._prepare_practice()
            else:
                self.lesson_execution.begin_course_stage()
        elif action == "skip_stage":
            if self.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs, not skips")
            self.lesson_execution.skip_stage(kwargs.get("reason"))
        elif action == "place_original":
            if self.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs")
            self.lesson_execution.place_original()
        elif action == "revisit_trouble":
            self.lesson_execution.revisit_trouble(kwargs.get("stage_key"), kwargs.get("start_beat"))
        elif action in ("learn", "learn_retry"):
            if action == "learn":
                self.lesson_cursor.set_course_guided(True)
                if "from_beat" not in kwargs:
                    self.lesson_execution.begin_course_stage(explicit_learn=True)
                    return
            previous_start = (self.guided_session.beat_range[0]
                              if self.guided_session.beat_range else 0.0)
            self.lesson_execution.begin_learn(
                from_beat=float(kwargs.get(
                    "from_beat",
                    previous_start if action == "learn_retry" else 0.0)),
                recovery=self.guided_session.return_context is not None and action == "learn_retry")
        elif action == "open_at":
            self._open_selected_measure(kwargs)
        elif action == "hints":
            self.guided_session.set_hints(
                bool(kwargs.get("enabled", False)), now=self.now())
            if kwargs.get("enabled", False) and self.measurement.attempt_id is not None:
                self.measurement.use_assistance()

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
        self.visual_transport.short_rest = (clear, header)

    def _collect_rest_measurement(self, *,
                                  from_beat: float = 0.0,
                                  source_end: float | None = None
                                  ) -> RestMeasurement | None:
        """Read authored meter and actual native glyph clearance only.

        This routine has no timing arithmetic. The musical scheduler owns
        the outgoing/incoming tempo conversion, count-in and deadline.
        """
        if self.visual_transport.short_rest is None or self.plan is None or self._presentation_bpm <= 0:
            return None
        clear, header = self.visual_transport.short_rest
        outgoing_bpm = self._presentation_bpm
        if source_end is None:
            if self.visual_transport.rest_take_end is None:
                return None
            source_end,outgoing_bpm = self.visual_transport.rest_take_end
        _, bar, _ = self.attempt_progression.count_in_bar(
            phrase=self.plan.active_phrase,
            boundaries=self.plan.piece.bar_boundaries,
            time_signatures=self.plan.piece.time_signatures,
            position=from_beat)
        return RestMeasurement(
            source_end=source_end,outgoing_bpm=outgoing_bpm,
            clear_beats=clear,header_beats=header,
            count_in_beats=bar,tempo_epoch=self.visual_transport.tempo_epoch)


    def _update_continuous_horizon(self, value) -> None:
        if value is None:
            return
        horizon = float(value)
        if not math.isfinite(horizon) or not 0.0 <= horizon <= 64.0:
            raise ValueError("Invalid continuous score reading horizon")
        self.visual_transport.continuous_horizon_beats = horizon

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
                self.playback_session.wait_for_player()
                self.feedback = "Ready to play"
                self.next_action = "Play one piano key to begin, or press Play."
        elif action == "stop":
            self._stop(reason="stop")
            # A stopped session has no take a later rest could follow (M6).
            self.visual_transport.rest_take_end = None
            self.feedback = "Stopped"
            self.next_action = "Start when you are ready."
        elif action in ("start", "restart"):
            self._update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self._update_short_rest(kwargs)
            if self.playback.presentation_required:
                if self.attempt.settlement_failed or self.attempt_settlement.pending_rolling is not None:
                    self._start_or_restart(action)
                    return
                effect = self.session_commands.active or self._manual_effect(action)
                transition = self.session_commands.transition(
                    effect,action=action,source_changed=(
                        self.score_artifacts.source_bpm_changed(self.plan.piece.bpm)
                        if self.playback_session.mode not in ("listen", "learn") else False))
                if transition.route in ("listen", "prepare_practice",
                                        "reload_score", "learn"):
                    # These routes change assets or enter untimed teaching.
                    # The resulting timed source, if any, is requested only
                    # after its exact selected score revision is prepared.
                    self._start_or_restart(action)
                else:
                    selected = transition.exposure
                    self._request_playback( action=action,
                        mode=selected.mode, from_beat=selected.from_beat,
                        transition=transition)
            else:
                self._start_or_restart(
                    action, presentation_lead_seconds=self._presentation_lead(kwargs))
        elif action == "pause":
            self._pause_current_session(
                pending_admission=self.playback_session.suspend_admission(self.playback))
        elif action == "resume":
            self._update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self._update_short_rest(kwargs)
            if self.playback.presentation_required:
                suspended = self.playback_session.take_suspended_admission()
                if suspended is not None:
                    self._request_playback(action=suspended.action,
                        mode=suspended.mode,from_beat=suspended.from_beat,
                        transition=suspended.transition)
                    return
                if not self.playback_session.running:
                    # Resume inside a rest resumes the pending teaching
                    # decision; it is not a new timed take. Its next take
                    # will independently enter the admission transaction.
                    self._resume_current_session()
                    return
                from_beat = self.visual_transport.play_from_beat
                if self.playback_session.running:
                    from_beat += max(0.0, self._elapsed_beat(
                        self.visual_transport.paused_at
                        - self.visual_transport.run_at))
                self._request_playback( action="resume",
                    mode=self.playback_session.mode, from_beat=from_beat)
            else:
                self._resume_current_session(presentation_lead_seconds=self._presentation_lead(kwargs),
                    reuse_pending_score=kwargs.get("reuse_pending_score",False) is True,
                    reuse_announced_score=kwargs.get("reuse_announced_score",False) is True)

    def _open_selected_measure(self, kwargs: dict):
        effect = self._manual_effect("open_at",values=kwargs)
        self._stop()
        selected = self._install_command(effect)
        self.lesson_execution.reset_trouble()
        self.lesson_cursor.set_course_guided(selected.mode == "learn")
        self.lesson_cursor.select_opening(selected.from_beat)
        if selected.mode == "learn":
            self.lesson_execution.begin_learn(from_beat=selected.from_beat,exposure=selected)
        else:
            self._prepare_practice(exposure=selected)
            self.playback_session.wait_for_player()
            self.feedback = f"Ready to practise from measure {kwargs.get('bar')}"
            self.next_action = "Press Start to play from the selected measure."

    def _start_or_restart(self, action: str, *,
                          presentation_lead_seconds: float = 0.0,
                          scheduled_deadline: float | None = None):
        """Start a take or schedule a seamless retry under the control lock."""
        if self.attempt.settlement_failed:
            revision = self.score_revision
            self.feedback = self._commit_pending() or "Assessment saved"
            if self.score_revision != revision:
                self.playback_session.await_score(self.score_revision)
            self.next_action = "Press Play when the score is ready."
            return
        if self.attempt_settlement.pending_rolling is not None:
            decision, phrase, grid, score_beat, _old_now = self.attempt_settlement.pending_rolling
            self._apply_rolling_recovery(decision, phrase, grid, score_beat, self.now())
            self.visual_transport.clear_pause_for_restart()
            return
        p = self.plan
        if p is None:
            raise ValueError("Open a piece first")
        effect = self._manual_effect(action)
        selected = self._install_command(effect)
        route = self.session_commands.start_route(effect,source_changed=(
            self.score_artifacts.source_bpm_changed(p.piece.bpm)
            if self.playback_session.mode not in ("listen","learn") else False))
        if route == "listen":
            self._prepare_listen()
            return
        if route == "prepare_practice":
            self._prepare_practice(exposure=selected)
            return
        if route == "learn":
            self.lesson_execution.begin_learn(exposure=selected)
            return
        if route == "reload_score":
            self._stop()
            self.source_identity.advance_revision()
            self.playback_session.await_score(self.score_revision)
            self.feedback = "Preparing sheet music"
            return
        if route == "rewind":
            sampled = self.now()
            visual_now = self.visual_transport.paused_at if self.visual_transport.paused else sampled
            position,_,_ = self._visual_motion(visual_now)
            self.playback_session.prepare_retry(PreparationRequest(
                self._source_model(),selected.from_beat,sampled,position,self.feedback_seconds,
                self._presentation_bpm,self.visual_transport.continuous_horizon_beats,
                reading_lead_included=presentation_lead_seconds > 0,
                short_deadline=scheduled_deadline),
                presentation_lead_seconds=presentation_lead_seconds,source_bpm=p.bpm)
            self.feedback = "Get ready to retry"
            return
        self.start(mode=selected.mode,from_beat=selected.from_beat,decided=True,
                   scheduled_deadline=scheduled_deadline,
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
        return self.visual_transport.musical_seconds(
            at,grading_after=self.midi_ingress.resume_grading_after)

    def _pause_current_session(self, *, pending_admission: bool = False):
        now = self.now()
        context = ("admitting" if pending_admission else self._phase(now)) \
            if not self.visual_transport.paused else ""
        self.playback_session.pause(context=context,now=now)
        if self.playback_session.mode == "learn" and self.teaching is not None:
            self.teaching.pause(now=now)

    def _resume_current_session(self, *, presentation_lead_seconds: float = 0.0,
                                reuse_pending_score: bool = False,
                                reuse_announced_score: bool = False,
                                scheduled_deadline: float | None = None):
        resumed = self.playback_session.resume_timeline(ResumeRequest(
            learning=self.playback_session.mode == "learn" and self.teaching is not None,
            bpm=self.plan.bpm if self.plan is not None else None,
            full_count_in_beats=self._next_count_in_beats(),
            midi_connected=self.midi.connected,reading_lead_seconds=presentation_lead_seconds,
            reuse_pending_score=reuse_pending_score,scheduled_deadline=scheduled_deadline))
        if resumed.learning:
            self.teaching.resume(now=resumed.now)
        announced = self.visual_transport.announced_continuation
        self.visual_transport.reannounce_after_rest_pause(RestResumeFacts(
            now=resumed.now,reading_lead_seconds=presentation_lead_seconds,
            running=self.playback_session.running,mode=self.playback_session.mode,
            bpm=self.plan.bpm if self.plan is not None else None,
            presentation_bpm=self._presentation_bpm,horizon_beats=self.visual_transport.continuous_horizon_beats,
            physical_rest_enabled=self.visual_transport.short_rest is not None,
            rest=(self._collect_rest_measurement(from_beat=announced[0],source_end=0.0)
                if announced is not None else None),reuse=reuse_announced_score))
        completion = self.playback_session.finish_resume(resumed)
        if completion.feedback is not None:
            self.feedback = completion.feedback
        if completion.deferred_score_revision is not None:
            self.control("score_ready",revision=completion.deferred_score_revision)
        self._start_listen_if_ready()

    def _change_stage(self, action: str, kwargs: dict):
        """Change the active lesson or tempo while preserving scoring state."""
        p=self.plan
        if not p:
            raise ValueError("Open a piece first")
        change = prepare_stage_change(
            p, action, kwargs, warmup=self.is_builtin_warmup)
        was_guided = self.playback_session.mode == "learn"
        guided_start = (self.guided_session.beat_range[0]
                        if self.guided_session.beat_range is not None else 0.0)
        guided_return = self.guided_session.return_context
        guided_retry_range = self.attempt.retry_range
        self._stop()
        self.lesson_execution.reset_trouble()
        # Preserve the original ordering of the source opening reset.
        if action in ("select_step", "next", "previous"):
            self.lesson_cursor.select_opening(0.0)
        effect = self.session_commands.active or self._prepare_teaching("manual", manual=change, action=action, store=False)
        self.session_commands.apply_progress(effect, plan=p)
        self.attempt_settlement.command_applied()
        if action == "hand":
            self.lesson_cursor.select_opening(0.0)
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if not change.tempo_only:
            self.source_identity.advance_revision()
        self.feedback="Ready"
        self.next_action="Start when you are ready."
        if was_guided:
            selected = effect.decision.next_exposure
            if selected is not None and selected.mode == "learn":
                recovery = change.tempo_only and guided_return is not None and guided_return[0] == p.identity
                if recovery:
                    self.attempt.restore_retry(guided_retry_range)
                self.lesson_execution.begin_learn(from_beat=selected.from_beat,bump_revision=False,recovery=recovery,exposure=selected)
            elif selected is not None:
                self.lesson_execution.enter_selected_exposure(selected)
        self._save()

    def _poll_midi_connection(self):
        if self.midi.closed:
            self._midi_lost()
        if self.device_workflows.connection_due():
            try:
                self.ports()
            except RuntimeError:
                # Keep actionable device feedback without failing /state.
                pass

    def _decided_stage_selection(self):
        if not self.playback_session.auto:
            return None
        return self.teaching_continuation.selection(self.attempt_settlement.pending,
            revision=self.score_revision,fingerprint=self.fingerprint)

    def _advance_pending_feedback(self, now: float, *, force_early: bool = False):
        transaction = self.teaching_continuation.begin_feedback(
            self.attempt_settlement.pending,now=now,automatic=self.playback_session.auto,
            force_early=force_early,revision=self.score_revision,fingerprint=self.fingerprint)
        if isinstance(transaction,FeedbackWaiting):
            if transaction.message:
                self.feedback = transaction.message
            return
        if isinstance(transaction,FeedbackFault):
            self._publish_feedback_fault(transaction,now)
            return
        try:
            self._commit_pending(finish_publication=False)
            self.visual_transport.note_tempo(
            stage=self.plan.identity,bpm=self._presentation_bpm,now=now)
        except Exception as exc:
            self._publish_feedback_fault(self.teaching_continuation.settlement_failure(exc),now)
            if not isinstance(exc,UnpreparedNextStage):
                print("ASSESSMENT_SETTLEMENT_FAILED:",type(exc).__name__,str(exc),flush=True)
            return
        self.attempt.clear_feedback()
        publication = self.teaching_continuation.finish_feedback(transaction,SettledSourceFacts(
            fingerprint=self.fingerprint,stage_key=self.plan.identity,revision=self.score_revision,
            now=now,bpm=self.plan.bpm,presentation_bpm=self._presentation_bpm,
            count_in_beats=self._next_count_in_beats(),automatic=self.playback_session.auto,
            flow_active=self.lesson_execution.flow_active()))
        if publication.flow_outcome is not None:
            self.flow_session.settle_decided(publication.flow_outcome,plan=self.plan,
                message=publication.message,decision_id=transaction.decision_id)
        self._dispatch_continuation_effect(publication.effect,now)
        self.attempt_settlement.finish_publication()

    def _publish_feedback_fault(self, fault: FeedbackFault, now: float) -> None:
        self.playback_session.apply_feedback_fault(fault,now=now)
        self.feedback,self.next_action = fault.feedback,fault.next_action

    def _dispatch_continuation_effect(self, effect, now: float) -> None:
        """Apply typed source ports; every route/deadline was selected by its owner."""
        if isinstance(effect,EnterSelectedExposure):
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif isinstance(effect,ApplySelectedResponse):
            self._apply_policy_response(effect.response,now=now,deadline=effect.deadline)
        elif isinstance(effect,EnterSelectedRemediation):
            self._start_remedial_assignment(effect.assignment,deadline=effect.deadline,
                exposure=effect.exposure)
        else:
            if isinstance(effect,ContinueSelectedScore):
                applied = self.playback_session.apply_continuation(effect,
                    measurement=self._collect_continuation_measurement(
                        effect.deadline,effect.exposure.from_beat),
                    source_stride_beats=self._source_model()["practice_timeline"]["stride_beats"])
            else:
                applied = self.playback_session.apply_continuation(effect)
            if applied.feedback is not None:
                self.feedback = applied.feedback
            if applied.start is not None:
                self._continue_at(applied.start.deadline,from_beat=applied.start.from_beat)

    def _start_remedial_assignment(self, assignment: RemedialAssignment,
                                   *, deadline: float | None = None, exposure=None) -> None:
        """Present an automatic remedial range without ever waiting for a key.

        A manually chosen guided lesson keeps the existing note-finding flow.
        An automatic rhythmic session always gets a scored, meter-bounded
        section that returns to the full passage after its recovery rest.
        """
        if self.plan is None:
            return
        prepared = prepare_remedial(self._exposure_source(),assignment,exposure,
            has_deadline=deadline is not None,automatic=self.playback_session.auto)
        if prepared is None:
            return
        if prepared.action == "guided":
            self.lesson_execution.begin_learn(from_beat=prepared.start,recovery=True,
                remediation=prepared.assignment,exposure=exposure)
            self.feedback = prepared.feedback
            return
        if prepared.action == "prepare":
            self._prepare_practice(exposure=exposure)
            self.playback_session.wait_for_player()
        self.lesson_cursor.select_opening(prepared.start)
        self.attempt.prepare_recovery(prepared)
        self.feedback,self.next_action = prepared.feedback,prepared.next_action
        if prepared.action == "continue":
            self._continue_at(SCHEDULER.continuation(
                self._collect_continuation_measurement(deadline,prepared.start),
                now=self.now(),bpm=self._presentation_bpm),from_beat=prepared.start)

    def _apply_rolling_recovery(self, decision, phrase: Phrase, grid, score_beat: float, now: float):
        """Apply an accepted source-grid recovery decision atomically."""
        # Capture marks at the performance tempo, not at the slower
        # BPM selected for the next retry. Re-scaling the recorded
        # timestamps early would move mistakes to incorrect notes.
        self.attempt.publish_live_marks(
            self._live_feedback((now-self.visual_transport.run_at)))
        self.live_assessment.publish(self.attempt.feedback_marks, self._feedback_take())
        outgoing_bpm = self.plan.bpm
        scored_end = self.visual_transport.run_at + (
            self._elapsed_seconds(decision.end_beat) -
            self._elapsed_seconds(self.visual_transport.play_from_beat))
        try:
            completed = self.attempt_settlement.complete_rolling(
                decision=decision,phrase=phrase,grid=grid,score_beat=score_beat,
                now=now,bpm=outgoing_bpm,scored_end=scored_end,hand=self.plan.hand,
                played=self.attempt.recorder.presses if self.attempt.recorder else (),
                from_beat=self.visual_transport.play_from_beat,
                tempo=self._active_tempo_map(),policies=self.assessment_policies,
                prepare_decision=self._prepare_teaching,plan=self.plan,
                binding=self._teaching_binding(),
                policy=resolve_mistake_policy(self.library.settings["mistake_response_strategy"]))
        except Exception:
            self.playback_session.finish_take()
            self.playback_session.stop_automatic()
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=now)
            self.feedback = "Could not save the retry evidence"
            self.next_action = "Check storage, then press Retry to save this same attempt."
            raise
        if completed.transition is None:
            from .measure_grid import next_chunk_end
            following = next_chunk_end(grid, decision.end_beat)
            self.visual_transport.next_boundary_beat = following if following > decision.end_beat+1e-7 else 0.
            return
        pending,transition = completed.pending,completed.transition
        outgoing_bpm,scored_end = completed.outgoing_bpm,completed.scored_end
        self.visual_transport.note_tempo(
            stage=self.plan.identity,bpm=self._presentation_bpm,now=now)
        short_deadline = None
        if transition.uses_completed_rest:
            self.visual_transport.rest_take_end = (scored_end, outgoing_bpm)
            short_deadline = SCHEDULER.measured_rest(
                self._collect_rest_measurement(from_beat=transition.restart_beat),
                now=now,bpm=self._presentation_bpm)
        self._schedule_preparation(transition.restart_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds,
            short_deadline=short_deadline)
        self.recovery_streak.record(
            transition.trouble_key,transition.trouble_count)
        self.attempt.apply_recovery(transition)
        if transition.guided:
            # The next step is note-by-note learning, not a timed take.
            self.visual_transport.withdraw_announcement()
        self.feedback = transition.feedback
        self.next_action = transition.next_action
        if transition.action == "pause":
            self.playback_session.stop_automatic()
            self.visual_transport.cancel_preparation()
            self.visual_transport.cancel_continuation()
        self.attempt_settlement.finish_rolling_publication()
        return

    def _complete_attempt(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> None:
        """Apply post-performance state after the score's settlement interval.

        This method is called from the locked _update loop. Assessment and
        grading are calculated only after a completed non-preview take.
        """
        self.visual_transport.rest_take_end = (self.visual_transport.run_at + duration, self.plan.bpm)
        if self.playback_session.preview_only:
            # Disconnected MIDI: repeat as an ungraded preview, never create
            # fake notes, misses, accepted passes or mastery.
            self.attempt_settlement.finish_preview()
            self.playback_session.finish_take()
            self.visual_transport.schedule_preview_repeat(
                source_seconds=duration,source_bpm=self.plan.bpm,
                presentation_bpm=self._presentation_bpm,
                rest_measurement=self._collect_rest_measurement(
                    from_beat=0.0,
                    source_end=self.visual_transport.run_at+duration),
                now=now,reading_horizon_beats=self.visual_transport.continuous_horizon_beats)
            self.feedback = "Timing preview - repeating after one empty measure"
            self.next_action = "Connect your MIDI piano to earn progress."
            if self.playback.presentation_required:
                # The next preview must be admitted during the rest, not at
                # the previous retry deadline after its count-in is over.
                self._continue_at(self.visual_transport.next_at,
                    from_beat=0.0)
            elif now >= self.visual_transport.next_at:
                self._update()
            return
        completed_visual = self._visual_motion(now)[0]
        completed = self.attempt_settlement.complete_take(
            phrase=phrase,hand=self.plan.hand,bpm=self.plan.bpm,
            played=(self.attempt.recorder.presses
                    if self.attempt.recorder else ()),
            from_beat=self.visual_transport.play_from_beat,end_beat=ending,
            tempo=self._active_tempo_map(),policies=self.assessment_policies,
            layout_for_feedback=self._layout_for_completed_take,
            mode=self.playback_session.mode,review_end_beat=self.attempt.review_end_beat,
            automatic_remedial_review=self.attempt.automatic_remedial_review,
            performance_review=self._performance_review,
            prepare_decision=self._prepare_teaching,
            plan=self.plan,binding=self._teaching_binding(),now=now,
            policy=resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]))
        assessed = completed.assessed
        result,route,summary = assessed.result,completed.route,completed.summary
        pending,response,settled = (
            completed.pending,completed.response,completed.settled)
        if settled:
            self.visual_transport.note_tempo(
            stage=self.plan.identity,bpm=self._presentation_bpm,now=now)
        self.attempt.publish_completion(
            marks=assessed.marks,unmapped=assessed.unmapped)
        # The completed take's settled grades, before any transition below can
        # start another transport.
        self.live_assessment.publish(self.attempt.feedback_marks, self._feedback_take(),
                                     final=True)
        self.feedback = assessed.feedback
        self.playback_session.finish_take()
        self.attempt.finish_review(summary,self.plan.identity)
        self.measurement.phase_changed("feedback", now)
        effect = completed.effect
        if effect.action == "response":
            self._apply_policy_response(effect.response,now=now,visual_from=completed_visual)
        elif effect.action == "perform":
            self._finish_performance_review(phrase,result)
        elif effect.action == "section_review":
            self._finish_section_review(result)
        elif effect.action == "stop_review":
            self.playback_session.stop_automatic()
            self.visual_transport.cancel_preparation()
            self.visual_transport.cancel_continuation()
            self.next_action = "Review this section before starting another take."
        elif effect.action == "exposure":
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif effect.action == "partial_recovery":
            self._finish_partial_recovery(result,now,exposure=effect.exposure)
        else:
            self._finish_full_passage(result,total_beats,duration,now)


    def _finish_performance_review(self, phrase: Phrase, result):
        """Publish review only after its evidence and source feedback commit."""
        self.next_action = performance_next_action(
            warmup=self.is_builtin_warmup,summary=self.attempt.performance_summary)
        self.playback_session.stop_automatic()

    def _finish_section_review(self, result):
        """Complete finish section review after a scored take."""
        # Section reviews are deliberate, bounded practice. Stop at the
        # selected boundary, preserve detailed feedback, and never
        # auto-advance to a different passage.
        self.playback_session.stop_automatic()
        self.attempt.finish_section_review()
        self.visual_transport.finish_rewind()
        self.lesson_cursor.select_opening(0.0)
        self.feedback = "Section review finished · " + result.summary
        self.next_action = "Review the notes or press Start for the whole passage."

    def _finish_partial_recovery(self, result, now: float, *, exposure=None):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        # Clear the bounded review before the scheduled full-pass retry.
        self.attempt.prepare_full_retry()
        self.lesson_cursor.select_opening(exposure.from_beat if exposure is not None else 0.0)
        self._schedule_preparation(self.open_from_beat, now=now,
            from_visual=self.visual_transport.visual_offset_beats + self.visual_transport.play_from_beat
                + self._elapsed_beat(now-self.visual_transport.run_at),
            reverse_seconds=self.feedback_seconds)
        self.feedback = "Selected section finished · " + result.summary
        self.next_action = "Next: play the whole passage from its beginning to earn mastery."

    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        publication = self.attempt_settlement.begin_full_completion(
            result,total_beats=total_beats,duration=duration)
        pending = publication.pending
        total_beats,duration = publication.total_beats,publication.duration
        self.attempt_settlement.checkpoint_failed_streak(pending,plan=self.plan,now=now)
        self.visual_transport.note_tempo(
            stage=self.plan.identity,bpm=self._presentation_bpm,now=now)
        exposure = pending.decision.next_exposure
        target = exposure.from_beat if exposure is not None else self.visual_transport.play_from_beat
        completion = self.playback_session.finish_full_passage(FullPassageFacts(
            pending=pending,stage_key=self.plan.identity,bpm=self.plan.bpm,
            target_bpm=self.plan.target_bpm,
            assessed_bpm=self.attempt_settlement.pending_assessed_bpm,
            total_beats=total_beats,duration=duration,now=now,
            visual_from=self._visual_motion(now)[0],feedback_seconds=self.feedback_seconds,
            source_model=self._source_model(),presentation_bpm=self._presentation_bpm,
            horizon_beats=self.visual_transport.continuous_horizon_beats,warmup=self.is_builtin_warmup,
            presentation_required=self.playback.presentation_required,
            short_rest_enabled=self.visual_transport.short_rest is not None,
            retry_rest=self._collect_rest_measurement(from_beat=target),
            repeat_rest=self._collect_rest_measurement(from_beat=0.0,
                source_end=self.visual_transport.run_at+duration),
            assets_ready=self.teaching_continuation.decision_assets_ready(pending,
                revision=self.score_revision,fingerprint=self.fingerprint),
            exact_repeats=self.lesson_execution.flow_active()))
        if completion.next_action is not None:
            self.next_action = completion.next_action
        if completion.advance_feedback:
            self._advance_pending_feedback(now,force_early=completion.force_early)
        elif completion.update_clock:
            self.attempt_settlement.finish_full_completion(publication)
            self._update()
            return
        self.attempt_settlement.finish_full_completion(publication)

    def _assess_rolling_boundary(self, boundary: float,
                                 grid: tuple[float, ...]):
        """Grade one authored boundary under the existing session lock."""
        try:
            self.attempt_settlement.checkpoint(
                self.attempt.recorder.presses if self.attempt.recorder else (),
                boundary=boundary)
        except Exception:
            if not self.visual_transport.paused:
                self.visual_transport.pause(at=self.now())
            self.feedback = "Could not save the recording checkpoint"
            self.next_action = "Check storage, then Resume to retry this boundary."
            raise
        if self.lesson_execution.flow_active() or not resolve_mistake_policy(
                self.library.settings["mistake_response_strategy"]).interrupt_rolling:
            # Practice flow: a take always plays to its end (no mid-take rewind).
            return None
        tempo_map = self._active_tempo_map()
        return self.assessment_policies.select(tempo_map).recover(
            self.plan.active_phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.attempt.recorder.presses if self.attempt.recorder else [],
            from_beat=self.visual_transport.play_from_beat, end_beat=boundary, grid=grid,
            threshold=(SETTINGS.warmup_recovery_errors
                       if self.is_builtin_warmup
                       else SETTINGS.recovery_errors_in_window),
            warmup=self.is_builtin_warmup, tempo=tempo_map)

    def _run_pre_assessment_transition(self, now: float) -> bool:
        """Apply an explicit non-grading transition under the session lock."""
        if self.playback.presentation_required and self.playback.intent is not None:
            return True
        context = TransitionContext(
            has_plan=self.plan is not None,
            learning=self.playback_session.mode == "learn" and self.teaching is not None,
            paused=self.visual_transport.paused, listening=self.playback_session.mode == "listen",
            preview_pending=self.visual_transport.preview_loop_pending,
            preparation_pending=self.visual_transport.preparation_pending,
            feedback_pending=self.attempt_settlement.feedback_pending,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            rewind_pending=self.visual_transport.pending_rewind is not None,
            running=self.playback_session.running, run_at=self.visual_transport.run_at)
        decision = decide_transition(
            context, now=now, next_at=self.visual_transport.next_at,
            preparation_at=self.visual_transport.preparation_deadline)
        if decision.preparation_phase is not None:
            self.visual_transport.enter_preparation_phase(decision.preparation_phase)
        if decision.action == "learning":
            self.guided_session.advance(connected=self.midi.connected, now=now)
            self.lesson_execution.save_guided_preparation()
        elif decision.action == "listening":
            if self.playback_session.running and self.listen.finished(now=now, run_at=self.visual_transport.run_at):
                self.playback_session.finish_take()
                self.feedback = "Example complete"
                self.next_action = (
                    "Choose Learn to find the notes, or Practice to play the rhythm.")
                if (self.lesson_execution.flow_active() and self.flow is not None
                        and self.flow.step is practice_flow.Step.LISTEN):
                    self.lesson_execution.flow_execute(self.flow_session.listen_finished())
        elif decision.action == "preview_due":
            deadline = self.visual_transport.next_at
            self.visual_transport.advance_source_stride(self._source_model()[
                "practice_timeline"]["stride_beats"])
            self._continue_at(SCHEDULER.continuation(
                    self._collect_continuation_measurement(deadline, 0.0),
                    now=self.now(),bpm=self._presentation_bpm))
        elif decision.action == "feedback":
            publication = self.attempt_settlement.pending_full_completion
            if publication is not None:
                self._finish_full_passage(publication.result,
                    publication.total_beats,publication.duration,now)
            else:
                self._advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self.attempt.guided_recovery_pending:
                self.lesson_execution.begin_learn(from_beat=self.visual_transport.pending_rewind, recovery=True,
                    exposure=self.attempt_settlement.pending.decision.next_exposure)
            else:
                target = self.visual_transport.pending_rewind
                self._continue_at(
                    SCHEDULER.continuation(
                    self._collect_continuation_measurement(self.visual_transport.next_at, target),
                    now=self.now(),bpm=self._presentation_bpm),
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
        # A playback intent is reconciled by the actual monotonic worker
        # transition, never by a later serializer's snapshot traversal.
        # Only worker/command execution advances the accepted lifecycle.
        self.playback.advance(self._playback_facts())
        self._prepare_score_presentation()
        # Display publication must never pause the take or alter feedback text.
        try:
            self._publish_live_assessment()
        except Exception:
            logging.getLogger(__name__).exception(
                "Live assessment publication failed; skipping this tick")

    def _update_transition(self) -> None:
        """Advance the backend clock under its existing session lock."""
        self._poll_midi_connection()
        self.midi_calibration.advance(self.now())
        self._apply_listen_failure()
        now = self.now()
        learning = self.playback_session.mode == "learn"
        guided_completed = bool(
            learning and self.teaching is not None
            and self.teaching.snapshot(now=now)["completed"])
        self.measurement.observe_phase(CapturePhaseFacts(
            paused=self.visual_transport.paused,learning=learning,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            guided_completed=guided_completed,running=self.playback_session.running,
            count_in_activation=max(
                self.visual_transport.run_at,
                self.midi_ingress.resume_grading_after),
            mode=self.playback_session.mode,preview=self.playback_session.preview_only,
            pending_result=self.attempt_settlement.pending_result is not None,
            preparation_pending=self.visual_transport.preparation_pending,
            performance_complete=self.attempt.performance_summary is not None),now)
        if self._run_pre_assessment_transition(now):
            return
        if (self.playback_session.running and self.visual_transport.grading_is_frozen(
                    now,grading_after=self.midi_ingress.resume_grading_after)):
            # The canonical recorder and live-assessment clock stand at the
            # paused source position. Do not inspect rolling checkpoints,
            # missed attacks, completion or recovery during the admitted
            # continuation's reading/count-in lead.
            return
        phrase = self.plan.active_phrase
        score_beat = self.visual_transport.play_from_beat + max(
            0.0, self._elapsed_beat(now-self.visual_transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.visual_transport.play_from_beat,
            run_at=self.visual_transport.run_at, next_boundary=self.visual_transport.next_boundary_beat,
            review_end=self.attempt.review_end_beat, preview=self.playback_session.preview_only,
            auto=self.playback_session.auto, mode=self.playback_session.mode,
            bpm=self.plan.bpm, gap_beats=self.visual_transport.visual_gap_beats),
            self._assess_rolling_boundary, self._elapsed_seconds,
            exact_repeats=self.lesson_execution.flow_active())
        self.visual_transport.next_boundary_beat = step.next_boundary
        if step.action == "recovery":
            self._apply_rolling_recovery(
                step.recovery, phrase, step.grid, score_beat, now)
        elif step.action == "complete":
            self._complete_attempt(phrase, step.ending,
                                   phrase.sounding_end-phrase.start, step.duration, now)
            self.playback_session.refloor_fresh_announcement(TimedTakeSource(
                self.plan.active_phrase,self.plan.piece.bar_boundaries,
                self.plan.piece.time_signatures,self.plan.bpm,
                self.visual_transport.visual_gap_beats),
                physical_rest_enabled=self.visual_transport.short_rest is not None)

    def _phase(self, now: float) -> str:
        teaching_phase = None
        if not self.visual_transport.paused and self.playback_session.mode == "learn" and self.teaching is not None:
            teaching_phase = ("loading" if self.playback_session.awaiting_score_revision is not None
                              else self.teaching.snapshot(now=now)["phase"])
        if (self.playback_session.running and not self.visual_transport.paused
                and now < self.midi_ingress.resume_grading_after):
            return "count_in"
        return project_phase(PhaseSnapshot(
            paused=self.visual_transport.paused, running=self.playback_session.running, run_at=self.visual_transport.run_at,
            teaching_phase=teaching_phase,
            performance_complete=self.attempt.performance_summary is not None,
            preview_loop_pending=self.visual_transport.preview_loop_pending,
            review_complete=self.attempt.review_session_complete,
            pending_result=self.attempt_settlement.pending_result is not None,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            pending_rewind=self.visual_transport.pending_rewind is not None,
        ), mode=self.playback_session.mode, now=now)

    def _layout_for_completed_take(self) -> dict:
        """Read only the exact pre-engraved layout of the completed take.

        This runs inside the musical tick. Cold Verovio work belongs to the
        asset worker, never the clock or MIDI lock. The assessment owner
        explicitly handles a missing feedback layout without regrading.
        """
        cached = self.score_artifacts.cached_layout(self._score_selection())
        if cached is None:
            raise RuntimeError("Admitted score layout is unavailable for completed feedback")
        return cached.layout

    def _open_take(self, *, phrase: Phrase | None = None,
                   recording: bool = False) -> int:
        return self.playback_session.open_take(phrase=phrase,recording=recording)

    def _feedback_take(self) -> dict:
        """Immutable identity of the take that the next feedback belongs to."""
        return {"piece_fingerprint": self.fingerprint or "",
                "revision": int(self.score_revision),
                "transport_id": int(self.playback_session.transport_id), "mode": self.playback_session.mode,
                "release_advisory": not self.library.settings["grade_note_holds"],
                "graded": (not self.playback_session.preview_only
                           and self.playback_session.mode in ("practice", "perform"))}

    def _publish_live_assessment(self) -> None:
        """Publish the incremental assessment continuously during playback.

        Uses the same _live_feedback grading call as every other consumer;
        only new or changed per-note results enter the feedback event log.
        """
        if (not self.playback_session.running or self.playback_session.preview_only
                or self.playback_session.mode not in ("practice", "perform")):
            # No running graded take: never carry the previous take's marks.
            self.live_assessment.clear()
            return
        if self.visual_transport.paused:
            return
        elapsed = self._musical_seconds(self.now())
        marks = self._live_feedback(elapsed)
        scope, _ = live_scope(self.plan.active_phrase,
            from_beat=self.visual_transport.play_from_beat,elapsed_seconds=elapsed,
            bpm=self.plan.bpm,tempo=self._active_tempo_map())
        self.live_assessment.publish(marks, self._feedback_take(),scope_start_beat=scope)

    def _live_marks_for_snapshot(self, _elapsed_seconds: float) -> list[dict]:
        # The command worker publishes marks; serialization only reads them.
        return list(self.live_assessment.latest_marks) if self.playback_session.running else []

    def _live_feedback(self, elapsed_seconds: float) -> list[dict]:
        """Read the current cached source and ask the single grading owner."""
        plan = self.plan
        if plan is None or self.playback_session.preview_only or not self.playback_session.running:
            return []
        engraved = self.score_artifacts.cached_layout(self._score_selection())
        if engraved is None:
            return []
        return self.assessment_policies.live_projection(
            plan.active_phrase, hand=plan.hand, bpm=plan.bpm,
            played=self.attempt.recorder.presses if self.attempt.recorder else (),
            from_beat=self.visual_transport.play_from_beat,
            elapsed_seconds=elapsed_seconds,
            bar_boundaries=plan.piece.bar_boundaries,
            layout=engraved.layout, tempo=self._active_tempo_map())

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
                if (self.playback_session.running or self.visual_transport.preview_loop_pending or self.visual_transport.preparation_pending
                        or self.attempt_settlement.pending_result is not None or self.visual_transport.pending_rewind is not None
                        or self.playback_session.mode == "listen"):
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

    def _score_projection_facts(self, pending, timeline) -> ScoreProjectionFacts:
        announced = self.visual_transport.announced_continuation
        plan = self.plan
        return ScoreProjectionFacts(
            fingerprint=self.fingerprint,
            stage_key=plan.identity if plan is not None else "",
            revision=self.score_revision,
            transport_id=self.playback_session.transport_id,
            mode=self.playback_session.mode,
            running=self.playback_session.running,
            paused=self.visual_transport.paused,
            awaiting_score=self.playback_session.awaiting_score_revision is not None,
            bpm=float(plan.bpm) if plan is not None else 0.0,
            presentation_bpm=float(self._presentation_bpm),
            run_at=self.visual_transport.run_at,
            play_from_beat=self.visual_transport.play_from_beat,
            announced=announced,
            announced_deadline=(self.visual_transport.announced_deadline(
                announced[0]) if announced is not None else None),
            announcement_serial=self.visual_transport.announce_serial,
            scheduled_start=self.visual_transport.scheduled_start,
            timeline=({"intent":pending,"current":timeline}
                      if self.playback.presentation_required else {}),
            next_count_in_beats=self._next_count_in_beats(),
            next_count_in_meter=tuple(self._next_count_in_meter()),
            continuous_horizon_beats=self.visual_transport.continuous_horizon_beats,
            duration_beats=(self.display_phrase().end-self.display_phrase().start
                            if plan is not None else 0.0),
            has_source=plan is not None,
        )

    def _prepare_score_presentation(self) -> None:
        if self.plan is None or self.playback_session.mode != "learn":
            return
        now = self.now()
        state = project_session_state(self._capture_session_snapshot(sampled_at=now))
        pending, timeline = self.playback.snapshot()
        self.score_state_publisher.prepare_guided(
            state,self._score_projection_facts(pending,timeline),now=now)

    def _state_snapshot(self) -> dict:
        with self.lock:
            now = self.now()
            state = project_session_state(self._capture_session_snapshot(sampled_at=now))
            pending, timeline = self.playback.snapshot()
            facts = self._score_projection_facts(pending,timeline)
            plan = self.plan
            guided_plan = self.score_state_publisher.publish(state, facts)
            if not self.playback.presentation_required:
                # Test/command fixture adapter; never entered by the desktop.
                def count_in_source_at(from_beat, rate):
                    _, bars, meter = self.attempt_progression.count_in_bar(
                        phrase=plan.active_phrase,
                        boundaries=plan.piece.bar_boundaries,
                        time_signatures=plan.piece.time_signatures,
                        position=from_beat)
                    return bars,meter,self._start_rate_bpm(from_beat,rate)
                project_headless_score_queue(
                    state, facts, measure_at=count_in_source_at,
                    guided=guided_plan)
            if self.attempt_settlement.pending_result is not None:
                state["bpm"] = self._presentation_bpm
            state["mistake_response_strategy"] = self.library.settings["mistake_response_strategy"]
            if self.lesson_execution.flow_active():
                state["flow"] = self.lesson_execution.flow_state()
            if self.plan is not None:
                epoch = self.visual_transport.tempo_epoch_for(
                    stage=self.plan.identity,bpm=self._presentation_bpm)
                if epoch is not None:
                    state["tempo_epoch_ms"] = epoch*1000.0
            if self.plan is not None:
                beat = self.plan.active_phrase.start + self.visual_transport.play_from_beat
                if self.playback_session.running and now >= self.visual_transport.run_at:
                    beat += self._elapsed_beat(now - self.visual_transport.run_at)
                keys = [key for key in self.plan.piece.key_signatures
                        if key.beat <= beat + 1e-7
                        and key.hand in ("both", self.plan.hand)]
                state["key_fifths"] = keys[-1].fifths if keys else 0
            # A score-free Settings screen still needs an authoritative
            # backend clock epoch for its MIDI tap calibration. Midpoint-only
            # UI extrapolation drifts when score and device requests queue.
            calibration_sample_at = now
            state.setdefault("clock_sampled_at_ms", calibration_sample_at * 1000.0)
            state["midi_offset_ms"] = self.library.settings["midi_offset_ms"]
            state["next_count_in_beats"] = self._next_count_in_beats()
            state["next_count_in_meter"] = self._next_count_in_meter()
            state["short_rest_latency_seconds"] = SNAPSHOT_LATENCY_SECONDS
            state["resume_count_in_beat"] = (
                SCHEDULER.seconds_beats(
                    calibration_sample_at-self.midi_ingress.resume_grading_after,
                    self.plan.bpm)
                if self.playback_session.running and not self.visual_transport.paused
                and calibration_sample_at < self.midi_ingress.resume_grading_after
                and self.plan is not None else None)
            state["midi_key_range"] = self.midi_key_shortcuts.status(self.midi.device)
            state["midi_calibration"] = self.midi_calibration.snapshot(
                calibration_sample_at)
            return state

    def _capture_session_snapshot(self, *, sampled_at=None) -> SessionSnapshot:
        """Sample named read ports under the existing application lock."""
        values = SnapshotValues(
            _guided_recovery_pending=self.attempt.guided_recovery_pending,
            _guided_return=self.guided_session.return_context,
            _remediation_active=self._remediation_active,
            auto=self.playback_session.auto,
            awaiting_score_revision=self.playback_session.awaiting_score_revision,
            count_in_bar_beats=self.playback_session.count_in_bar_beats,
            count_in_beats=self.playback_session.count_in_beats,
            count_in_meter=self.playback_session.count_in_meter,
            feedback=self.feedback,
            feedback_marks=self.attempt.feedback_marks,
            feedback_unmapped=self.attempt.feedback_unmapped,
            fingerprint=self.fingerprint,
            guided_range=self.guided_session.beat_range,
            is_builtin_warmup=self.is_builtin_warmup,
            metronome=self.library.settings["metronome"],
            midi_input_count=self.midi.input_count,
            midi_input_note=self.midi.input_note,
            midi_input_at=self.midi.input_at,
            midi_connected=self.midi.connected,
            midi_device=self.midi.device,
            midi_notes=len(self.attempt.recorder.presses) if self.attempt.recorder is not None else 0,
            teaching_active=self.teaching is not None,
            mode=self.playback_session.mode,
            next_action=self.next_action,
            next_at=self.visual_transport.next_at,
            open_from_beat=self.open_from_beat,
            pause_context=self.playback_session.pause_context,
            paused=self.visual_transport.paused,
            paused_at=self.visual_transport.paused_at,
            pending_result=self.attempt_settlement.pending_result,
            assessment_verdict=(
                self.attempt_settlement.pending.decision.verdict
                if self.attempt_settlement.pending is not None
                and self.attempt_settlement.pending.assessment is self.attempt_settlement.pending_result
                else None),
            pending_rewind=self.visual_transport.pending_rewind,
            performance_summary=self.attempt.performance_summary,
            persistent_hints=self.persistent_hints,
            plan=self.plan,
            play_from_beat=self.visual_transport.play_from_beat,
            practice_preparation=self.visual_transport.practice_preparation,
            preview_only=self.playback_session.preview_only,
            recovery_notice=self.attempt.recovery_notice,
            retry_range=self.attempt.retry_range,
            review_end_beat=self.attempt.review_end_beat,
            run_at=self.visual_transport.run_at,
            running=self.playback_session.running,
            score_revision=self.score_revision,
            transport_id=self.playback_session.transport_id,
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
            clock=self.now if sampled_at is None else lambda: sampled_at,
        )
        return capture_session_snapshot(values, reads)

    def _next_stage_selection(self, *, offset: int = 1) -> tuple[ScoreSelection, int] | None:
        if self.plan is None or self.is_builtin_warmup or self.playback_session.mode != "practice":
            return None
        decided = self._decided_stage_selection() if offset == 1 else None
        return self.teaching_continuation.choose_ahead(
            self.plan,fingerprint=self.fingerprint,revision=self.score_revision,
            offset=offset,decided=decided)

    def next_stage_score(self) -> bytes:
        with self.lock:
            return self.teaching_continuation.ensure_next(
                self._next_stage_selection())

    def report_preload_failure(self, *, fingerprint: str, step_number: int,
                               revision: int, error: str) -> dict:
        with self.lock:
            return self.teaching_continuation.report_native_failure(
                self._next_stage_selection(),fingerprint=fingerprint,
                step_number=step_number,revision=revision,error=error)

    def acknowledge_preloaded_stage(self, *, stage_key: str,
                                    revision: int) -> dict:
        with self.lock:
            accepted = self.teaching_continuation.acknowledge_stage(
                self._next_stage_selection(),stage_key=stage_key,revision=revision)
            source = (PreloadedFeedbackSource(
                self.plan.active_phrase.sounding_end-self.plan.active_phrase.start,
                self.plan.bpm,self._active_tempo_map()) if self.plan is not None else None)
            released_at = self.playback_session.activate_preloaded_feedback(source,
                revision=self.score_revision,fingerprint=self.fingerprint)
            if released_at is not None:
                self._advance_pending_feedback(released_at)
            self.teaching_continuation.warm_more(
                self._next_stage_selection(offset=2))
            return accepted

    def _score_selection(self) -> ScoreSelection:
        """Capture the selected source under the application lock."""
        if self.plan is None:
            raise ValueError("No piece loaded")
        p = self.plan
        return ScoreSelection(piece=p.piece, phrase=self.display_phrase(),
            hand=p.hand, stage_key=p.identity, revision=self.score_revision,
            fingerprint=self.fingerprint,
            transformed_rhythm=(self._remediation_active.transformed_rhythm
                if self._remediation_active is not None else p.active_stage.transformed_rhythm),
            display_name=(self._remediation_active.focus if self._remediation_active is not None else ""))

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


