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
from .application.score_read_services import ScoreReadServices
from .application.session_read_models import SessionReadModels
from .application.transport_timing import TransportTiming
from .application.timed_playback import TimedPlayback
from .application.live_feedback_workflows import LiveFeedbackWorkflows
from .application.post_assessment_effects import PostAssessmentEffects
from .application.recovery_workflows import RecoveryWorkflows
from .application.completion_continuations import CompletionContinuations
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

        self.score_read = ScoreReadServices(
            source_identity=self.source_identity, attempt=self.attempt,
            lesson_execution=self.lesson_execution,
            guided_session=self.guided_session,
            score_artifact_registry=self.score_artifact_registry,
            learner_progress=self.learner_progress, lock=self.lock)

        self.transport_timing = TransportTiming(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, playback_session=self.playback_session,
            visual_transport=self.visual_transport, tempo_map_cache=self.tempo_map_cache,
            attempt_progression=self.attempt_progression,
            attempt_settlement=self.attempt_settlement, score_read=self.score_read,
            midi_ingress=self.midi_ingress, playback=self.playback, clock=self.now)

        self.timed_playback = TimedPlayback(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, playback_session=self.playback_session,
            playback=self.playback, attempt_settlement=self.attempt_settlement,
            session_commands=self.session_commands, teaching_decisions=self.teaching_decisions,
            exposure_workflows=self.exposure_workflows, guided_session=self.guided_session,
            visual_transport=self.visual_transport, midi=self.midi,
            score_read=self.score_read, evidence_context=self.evidence_context,
            transport_timing=self.transport_timing, lesson_execution=self.lesson_execution,
            clock=self.now, lock=self.lock, phase=self._phase)

        self.live_feedback_workflows = LiveFeedbackWorkflows(
            source_identity=self.source_identity, playback_session=self.playback_session,
            visual_transport=self.visual_transport,
            score_artifact_registry=self.score_artifact_registry,
            score_read=self.score_read, policy_registry=self.policy_registry,
            library=self.library, attempt=self.attempt,
            live_assessment=self.live_assessment,
            transport_timing=self.transport_timing, clock=self.now)

        self.outcome_effects = PostAssessmentEffects(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, attempt_settlement=self.attempt_settlement,
            teaching_decisions=self.teaching_decisions, clock=self.now,
            teaching_continuation=self.teaching_continuation, library=self.library,
            visual_transport=self.visual_transport, attempt=self.attempt,
            lesson_execution=self.lesson_execution, playback_session=self.playback_session,
            score_artifact_registry=self.score_artifact_registry,
            transport_timing=self.transport_timing, assessment=self.assessment,
            feedback_seconds=self.feedback_seconds)

        self.recovery_workflows = RecoveryWorkflows(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, attempt=self.attempt,
            playback_session=self.playback_session, visual_transport=self.visual_transport,
            transport_timing=self.transport_timing, timed_playback=self.timed_playback,
            lesson_execution=self.lesson_execution,
            exposure_workflows=self.exposure_workflows,
            attempt_settlement=self.attempt_settlement, policy_registry=self.policy_registry,
            library=self.library, recovery_streak=self.recovery_streak,
            live_feedback_workflows=self.live_feedback_workflows,
            live_assessment=self.live_assessment,
            teaching_decisions=self.teaching_decisions,
            clock=self.now, feedback_seconds=self.feedback_seconds)

        self.completion_continuations = CompletionContinuations(
            source_identity=self.source_identity, notices=self.notices,
            teaching_continuation=self.teaching_continuation,
            attempt_settlement=self.attempt_settlement,
            playback_session=self.playback_session,
            visual_transport=self.visual_transport, attempt=self.attempt,
            flow_session=self.flow_session, lesson_execution=self.lesson_execution,
            transport_timing=self.transport_timing, score_read=self.score_read,
            recovery_workflows=self.recovery_workflows,
            timed_playback=self.timed_playback, outcome_effects=self.outcome_effects)

        self.read_models = SessionReadModels(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, attempt=self.attempt,
            guided_session=self.guided_session, playback_session=self.playback_session,
            visual_transport=self.visual_transport, playback=self.playback,
            attempt_settlement=self.attempt_settlement, library=self.library,
            midi=self.midi, midi_ingress=self.midi_ingress,
            midi_key_shortcuts=self.midi_key_shortcuts, midi_calibration=self.midi_calibration,
            attempt_progression=self.attempt_progression,
            score_state_publisher=self.score_state_publisher,
            lesson_execution=self.lesson_execution, score_read=self.score_read,
            listen=self.listen, live_input=self.live_input,
            live_assessment=self.live_assessment, lock=self.lock, clock=self.now,
            phase=self._phase, elapsed_beat=self.transport_timing.elapsed_beat,
            visual_motion=self.transport_timing.visual_motion, tempo_map=self.transport_timing.active_tempo_map,
            next_count_in_beats=self.transport_timing.next_count_in_beats,
            next_count_in_meter=self.transport_timing.next_count_in_meter,
            start_rate_bpm=self.transport_timing.start_rate_bpm,
            presentation_bpm=lambda: self.transport_timing.presentation_bpm())

    def require_presentation(self) -> None:
        with self.lock:
            self.playback.enable_presentation(self.transport_timing.playback_facts())

    def playback_status(self) -> dict:
        with self.lock:
            return self.playback.status()

    def reserve_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.reserve(self.transport_timing.playback_facts(),**values)

    def present_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.present(self.transport_timing.playback_facts(),
                commit=self._commit_playback_intent,capture=self.transport_timing.playback_facts,
                abort=self._abort_playback,**values)

    def withdraw_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.withdraw(self.transport_timing.playback_facts(),**values)

    def report_playback_failure(self, **values) -> dict:
        with self.lock:
            self.playback.fail(notify_failure=self._on_playback_failure,**values)
            return {"accepted":True}

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
            tempo_map=self.transport_timing.active_tempo_map())

    def learning_history_status(self) -> dict:
        with self.lock:
            return self.history_management.status()

    def learning_statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        return self.history_management.statistics(fingerprint, query=query)

    def _retry_context(self, result, *, end_beat=None):
        return self.teaching_decisions.retry_context(result, end_beat=end_beat)

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
                changes, pause_current=self.timed_playback.pause)

    def exercise_diagnostics(self) -> dict:
        with self.lock:
            return self.settings_workflows.exercise_diagnostics(
                tempo_map=self.transport_timing.active_tempo_map())

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
                self.transport_timing.active_tempo_map(),self.playback_session.running or (self.playback_session.mode == "learn" and self.teaching is not None))
            self.midi_ingress.dispatch(
                message,facts=facts,received_at=now,
                corrected_at=corrected_at,deferred=deferred,
                midi_offset_seconds=self.library.settings["midi_offset_ms"]/1000.0,
                apply_shortcut=self._apply_midi_shortcut,
                transport_facts=self._midi_transport_facts,
                musical_seconds=self.transport_timing.musical_seconds,
                recorder=lambda: self.attempt.recorder,
                teaching=lambda: self.teaching,
                feedback_take=self.live_feedback_workflows.feedback_take)

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

    def _prepare_practice(self, *, exposure=None):
        return self.exposure_workflows.prepare_practice(exposure=exposure)

    def _apply_listen_failure(self) -> None:
        self.exposure_workflows.apply_listen_failure()

    def _prepare_listen(self):
        return self.exposure_workflows.prepare_listen()

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            return self.listen.audio_path(token)

    def _prepare_perform(self, *, scope: str = "current", exposure=None):
        return self.exposure_workflows.prepare_perform(scope=scope, exposure=exposure)

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


    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False, scheduled_deadline: float | None = None,
              presentation_lead_seconds: float = 0.0, decided: bool = False,
              count_in_plan=None):
        return self.timed_playback.start(
            from_beat=from_beat, mode=mode, loop_continuation=loop_continuation,
            scheduled_deadline=scheduled_deadline,
            presentation_lead_seconds=presentation_lead_seconds,
            decided=decided, count_in_plan=count_in_plan)

    def _resume_current_session(self, *, presentation_lead_seconds=0.0,
                                reuse_pending_score=False,
                                reuse_announced_score=False,
                                scheduled_deadline=None):
        completed = self.timed_playback.resume(
            presentation_lead_seconds=presentation_lead_seconds,
            reuse_pending_score=reuse_pending_score,
            reuse_announced_score=reuse_announced_score,
            scheduled_deadline=scheduled_deadline)
        if completed.deferred_score_revision is not None:
            self.control("score_ready", revision=completed.deferred_score_revision)
        self.timed_playback.begin_listen_if_ready()

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
                    self.read_models.prepare_score_presentation()
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
                        self.timed_playback.pause()
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
                self.timed_playback.begin_listen_if_ready()
            elif decision == "learn":
                self.teaching.start(now=self.now())
            elif decision == "practice":
                position = (self.visual_transport.pending_rewind
                    if self.visual_transport.pending_rewind is not None else self.open_from_beat)
                mode = "perform" if self.playback_session.mode == "perform" else "practice"
                if self.playback.presentation_required:
                    self.transport_timing.request_playback(action="score_ready",mode=mode,from_beat=position)
                    return
                announce = self.visual_transport.short_rest is not None or self.lesson_execution.flow_active()
                timing = self.playback_session.headless_ready_timing(
                    reserved_ms=kwargs.get("presentation_deadline_ms"),
                    count_in_beats=self.transport_timing.next_count_in_beats(),bpm=self.plan.bpm,
                    announce=announce,rest=(self.transport_timing.collect_rest_measurement(
                        from_beat=self.open_from_beat) if announce and
                        kwargs.get("presentation_deadline_ms") is None else None),
                    presentation_bpm=self.transport_timing.presentation_bpm())
                self.start(from_beat=position,mode=mode,scheduled_deadline=timing.deadline,
                    presentation_lead_seconds=timing.lead_seconds,decided=True)
                if announce:
                    self.visual_transport.scheduled_start = (
                        self.playback_session.transport_id,self.visual_transport.play_from_beat,
                        self.visual_transport.run_at,self.plan.identity,self.score_revision,None)
        elif self.playback_session.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
            self.timed_playback.begin_listen_if_ready()

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
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
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
                    self.transport_timing.request_playback( action=action,
                        mode=selected.mode, from_beat=selected.from_beat,
                        transition=transition)
            else:
                self._start_or_restart(
                    action, presentation_lead_seconds=self.transport_timing.presentation_lead(kwargs))
        elif action == "pause":
            self.timed_playback.pause(
                pending_admission=self.playback_session.suspend_admission(self.playback))
        elif action == "resume":
            self.transport_timing.update_continuous_horizon(kwargs.get("continuous_horizon_beats"))
            self.transport_timing.update_short_rest(kwargs)
            if self.playback.presentation_required:
                suspended = self.playback_session.take_suspended_admission()
                if suspended is not None:
                    self.transport_timing.request_playback(action=suspended.action,
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
                    from_beat += max(0.0, self.transport_timing.elapsed_beat(
                        self.visual_transport.paused_at
                        - self.visual_transport.run_at))
                self.transport_timing.request_playback( action="resume",
                    mode=self.playback_session.mode, from_beat=from_beat)
            else:
                self._resume_current_session(presentation_lead_seconds=self.transport_timing.presentation_lead(kwargs),
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
            self.feedback = self.outcome_effects.commit_pending() or "Assessment saved"
            if self.score_revision != revision:
                self.playback_session.await_score(self.score_revision)
            self.next_action = "Press Play when the score is ready."
            return
        if self.attempt_settlement.pending_rolling is not None:
            decision, phrase, grid, score_beat, _old_now = self.attempt_settlement.pending_rolling
            self.recovery_workflows.apply_rolling_recovery(decision, phrase, grid, score_beat, self.now())
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
            position,_,_ = self.transport_timing.visual_motion(visual_now)
            self.playback_session.prepare_retry(PreparationRequest(
                self.score_read.source_model(),selected.from_beat,sampled,position,self.feedback_seconds,
                self.transport_timing.presentation_bpm(),self.visual_transport.continuous_horizon_beats,
                reading_lead_included=presentation_lead_seconds > 0,
                short_deadline=scheduled_deadline),
                presentation_lead_seconds=presentation_lead_seconds,source_bpm=p.bpm)
            self.feedback = "Get ready to retry"
            return
        self.start(mode=selected.mode,from_beat=selected.from_beat,decided=True,
                   scheduled_deadline=scheduled_deadline,
                   presentation_lead_seconds=presentation_lead_seconds)
        return

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
                presentation_bpm=self.transport_timing.presentation_bpm(),
                rest_measurement=self.transport_timing.collect_rest_measurement(
                    from_beat=0.0,
                    source_end=self.visual_transport.run_at+duration),
                now=now,reading_horizon_beats=self.visual_transport.continuous_horizon_beats)
            self.feedback = "Timing preview - repeating after one empty measure"
            self.next_action = "Connect your MIDI piano to earn progress."
            if self.playback.presentation_required:
                # The next preview must be admitted during the rest, not at
                # the previous retry deadline after its count-in is over.
                self.timed_playback.continue_at(self.visual_transport.next_at,
                    from_beat=0.0)
            elif now >= self.visual_transport.next_at:
                self._update()
            return
        completed_visual = self.transport_timing.visual_motion(now)[0]
        completed = self.attempt_settlement.complete_take(
            phrase=phrase,hand=self.plan.hand,bpm=self.plan.bpm,
            played=(self.attempt.recorder.presses
                    if self.attempt.recorder else ()),
            from_beat=self.visual_transport.play_from_beat,end_beat=ending,
            tempo=self.transport_timing.active_tempo_map(),policies=self.assessment_policies,
            layout_for_feedback=self.score_read.completed_take_layout,
            mode=self.playback_session.mode,review_end_beat=self.attempt.review_end_beat,
            automatic_remedial_review=self.attempt.automatic_remedial_review,
            performance_review=self.outcome_effects.performance_review,
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
            stage=self.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        self.attempt.publish_completion(
            marks=assessed.marks,unmapped=assessed.unmapped)
        # The completed take's settled grades, before any transition below can
        # start another transport.
        self.live_assessment.publish(self.attempt.feedback_marks, self.live_feedback_workflows.feedback_take(),
                                     final=True)
        self.feedback = assessed.feedback
        self.playback_session.finish_take()
        self.attempt.finish_review(summary,self.plan.identity)
        self.measurement.phase_changed("feedback", now)
        effect = completed.effect
        if effect.action == "response":
            self.recovery_workflows.apply_policy_response(effect.response,now=now,visual_from=completed_visual)
        elif effect.action == "perform":
            self.outcome_effects.finish_performance_review(phrase,result)
        elif effect.action == "section_review":
            self.outcome_effects.finish_section_review(result)
        elif effect.action == "stop_review":
            self.playback_session.stop_automatic()
            self.visual_transport.cancel_preparation()
            self.visual_transport.cancel_continuation()
            self.next_action = "Review this section before starting another take."
        elif effect.action == "exposure":
            self.lesson_execution.enter_selected_exposure(effect.exposure)
        elif effect.action == "partial_recovery":
            self.outcome_effects.finish_partial_recovery(result,now,exposure=effect.exposure)
        else:
            self._finish_full_passage(result,total_beats,duration,now)


    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        publication = self.attempt_settlement.begin_full_completion(
            result,total_beats=total_beats,duration=duration)
        pending = publication.pending
        total_beats,duration = publication.total_beats,publication.duration
        self.attempt_settlement.checkpoint_failed_streak(pending,plan=self.plan,now=now)
        self.visual_transport.note_tempo(
            stage=self.plan.identity,bpm=self.transport_timing.presentation_bpm(),now=now)
        exposure = pending.decision.next_exposure
        target = exposure.from_beat if exposure is not None else self.visual_transport.play_from_beat
        completion = self.playback_session.finish_full_passage(FullPassageFacts(
            pending=pending,stage_key=self.plan.identity,bpm=self.plan.bpm,
            target_bpm=self.plan.target_bpm,
            assessed_bpm=self.attempt_settlement.pending_assessed_bpm,
            total_beats=total_beats,duration=duration,now=now,
            visual_from=self.transport_timing.visual_motion(now)[0],feedback_seconds=self.feedback_seconds,
            source_model=self.score_read.source_model(),presentation_bpm=self.transport_timing.presentation_bpm(),
            horizon_beats=self.visual_transport.continuous_horizon_beats,warmup=self.is_builtin_warmup,
            presentation_required=self.playback.presentation_required,
            short_rest_enabled=self.visual_transport.short_rest is not None,
            retry_rest=self.transport_timing.collect_rest_measurement(from_beat=target),
            repeat_rest=self.transport_timing.collect_rest_measurement(from_beat=0.0,
                source_end=self.visual_transport.run_at+duration),
            assets_ready=self.teaching_continuation.decision_assets_ready(pending,
                revision=self.score_revision,fingerprint=self.fingerprint),
            exact_repeats=self.lesson_execution.flow_active()))
        if completion.next_action is not None:
            self.next_action = completion.next_action
        if completion.advance_feedback:
            self.completion_continuations.advance_pending_feedback(now,force_early=completion.force_early)
        elif completion.update_clock:
            self.attempt_settlement.finish_full_completion(publication)
            self._update()
            return
        self.attempt_settlement.finish_full_completion(publication)

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
            self.visual_transport.advance_source_stride(self.score_read.source_model()[
                "practice_timeline"]["stride_beats"])
            self.timed_playback.continue_at(SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(deadline, 0.0),
                    now=self.now(),bpm=self.transport_timing.presentation_bpm()))
        elif decision.action == "feedback":
            publication = self.attempt_settlement.pending_full_completion
            if publication is not None:
                self._finish_full_passage(publication.result,
                    publication.total_beats,publication.duration,now)
            else:
                self.completion_continuations.advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self.attempt.guided_recovery_pending:
                self.lesson_execution.begin_learn(from_beat=self.visual_transport.pending_rewind, recovery=True,
                    exposure=self.attempt_settlement.pending.decision.next_exposure)
            else:
                target = self.visual_transport.pending_rewind
                self.timed_playback.continue_at(
                    SCHEDULER.continuation(
                    self.transport_timing.collect_continuation_measurement(self.visual_transport.next_at, target),
                    now=self.now(),bpm=self.transport_timing.presentation_bpm()),
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
        self.playback.advance(self.transport_timing.playback_facts())
        self.read_models.prepare_score_presentation()
        # Display publication must never pause the take or alter feedback text.
        try:
            self.live_feedback_workflows.publish_live()
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
            0.0, self.transport_timing.elapsed_beat(now-self.visual_transport.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.visual_transport.play_from_beat,
            run_at=self.visual_transport.run_at, next_boundary=self.visual_transport.next_boundary_beat,
            review_end=self.attempt.review_end_beat, preview=self.playback_session.preview_only,
            auto=self.playback_session.auto, mode=self.playback_session.mode,
            bpm=self.plan.bpm, gap_beats=self.visual_transport.visual_gap_beats),
            self.recovery_workflows.assess_rolling_boundary, self.transport_timing.elapsed_seconds,
            exact_repeats=self.lesson_execution.flow_active())
        self.visual_transport.next_boundary_beat = step.next_boundary
        if step.action == "recovery":
            self.recovery_workflows.apply_rolling_recovery(
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
            state = self.read_models.snapshot()
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
                self.plan.bpm,self.transport_timing.active_tempo_map()) if self.plan is not None else None)
            released_at = self.playback_session.activate_preloaded_feedback(source,
                revision=self.score_revision,fingerprint=self.fingerprint)
            if released_at is not None:
                self.completion_continuations.advance_pending_feedback(released_at)
            self.teaching_continuation.warm_more(
                self._next_stage_selection(offset=2))
            return accepted

    def semantic_score(self) -> dict:
        return self.score_read.semantic_score()

    def engraving(self) -> EngravedScore:
        return self.score_read.engraving()

    def geometry(self) -> dict:
        return self.score_read.geometry()

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.score_read.lesson_overview()
