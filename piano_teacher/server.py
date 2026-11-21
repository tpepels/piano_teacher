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
from .application.practice_timeline import PracticeTimeline
from .application.practice_controls import PracticeControls
from .application.midi_application_input import MidiApplicationInput
from .application.score_preload_workflow import ScorePreloadWorkflow
from .application.session_phase import SessionPhase
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

        self.session_phase = SessionPhase(
            visual_transport=self.visual_transport,
            playback_session=self.playback_session,
            guided_session=self.guided_session, midi_ingress=self.midi_ingress,
            attempt=self.attempt, attempt_settlement=self.attempt_settlement)

        self.timed_playback = TimedPlayback(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, playback_session=self.playback_session,
            playback=self.playback, attempt_settlement=self.attempt_settlement,
            session_commands=self.session_commands, teaching_decisions=self.teaching_decisions,
            exposure_workflows=self.exposure_workflows, guided_session=self.guided_session,
            visual_transport=self.visual_transport, midi=self.midi,
            score_read=self.score_read, evidence_context=self.evidence_context,
            transport_timing=self.transport_timing, lesson_execution=self.lesson_execution,
            clock=self.now, lock=self.lock, phase=self.session_phase.at)

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

        self.score_preload = ScorePreloadWorkflow(
            source_identity=self.source_identity, lock=self.lock,
            playback_session=self.playback_session,
            teaching_continuation=self.teaching_continuation,
            attempt_settlement=self.attempt_settlement,
            transport_timing=self.transport_timing,
            completion_continuations=self.completion_continuations)

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
            phase=self.session_phase.at, elapsed_beat=self.transport_timing.elapsed_beat,
            visual_motion=self.transport_timing.visual_motion, tempo_map=self.transport_timing.active_tempo_map,
            next_count_in_beats=self.transport_timing.next_count_in_beats,
            next_count_in_meter=self.transport_timing.next_count_in_meter,
            start_rate_bpm=self.transport_timing.start_rate_bpm,
            presentation_bpm=lambda: self.transport_timing.presentation_bpm())

        self.practice_controls = PracticeControls(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, lock=self.lock, session_commands=self.session_commands,
            playback_session=self.playback_session, playback=self.playback,
            attempt=self.attempt, attempt_settlement=self.attempt_settlement,
            timed_playback=self.timed_playback, transport_timing=self.transport_timing,
            score_read=self.score_read, score_artifact_registry=self.score_artifact_registry,
            guided_session=self.guided_session, flow_session=self.flow_session,
            listen=self.listen, midi=self.midi, midi_key_shortcuts=self.midi_key_shortcuts,
            teaching_decisions=self.teaching_decisions,
            exposure_workflows=self.exposure_workflows, lesson_execution=self.lesson_execution,
            outcome_effects=self.outcome_effects, recovery_workflows=self.recovery_workflows,
            completion_continuations=self.completion_continuations,
            history_management=self.history_management,
            device_workflows=self.device_workflows, settings_workflows=self.settings_workflows,
            measurement=self.measurement, visual_transport=self.visual_transport,
            progress=self.progress, lifecycle=self.session_lifecycle,
            read_models=self.read_models, clock=self.now,
            feedback_seconds=self.feedback_seconds)

        self.midi_application_input = MidiApplicationInput(
            source_identity=self.source_identity, visual_transport=self.visual_transport,
            playback_session=self.playback_session, attempt_settlement=self.attempt_settlement,
            attempt=self.attempt, playback=self.playback, midi=self.midi, lock=self.lock,
            runtime_timings=self.runtime_timings, device_workflows=self.device_workflows,
            teaching_decisions=self.teaching_decisions,
            settings_workflows=self.settings_workflows, library=self.library,
            midi_ingress=self.midi_ingress, transport_timing=self.transport_timing,
            live_feedback_workflows=self.live_feedback_workflows,
            guided_session=self.guided_session, practice_controls=self.practice_controls,
            timed_playback=self.timed_playback, clock=self.now)

        self.practice_timeline = PracticeTimeline(
            source_identity=self.source_identity, lesson_cursor=self.lesson_cursor,
            notices=self.notices, visual_transport=self.visual_transport,
            playback_session=self.playback_session, playback=self.playback,
            attempt_settlement=self.attempt_settlement, attempt=self.attempt,
            transport_timing=self.transport_timing, timed_playback=self.timed_playback,
            score_read=self.score_read, outcome_effects=self.outcome_effects,
            lesson_execution=self.lesson_execution, recovery_workflows=self.recovery_workflows,
            completion_continuations=self.completion_continuations,
            live_feedback_workflows=self.live_feedback_workflows,
            live_assessment=self.live_assessment, measurement=self.measurement,
            policy_registry=self.policy_registry, library=self.library,
            teaching_decisions=self.teaching_decisions,
            guided_session=self.guided_session, flow_session=self.flow_session,
            midi=self.midi, listen=self.listen, midi_ingress=self.midi_ingress,
            midi_calibration=self.midi_calibration,
            attempt_progression=self.attempt_progression, read_models=self.read_models,
            teaching_continuation=self.teaching_continuation,
            exposure_workflows=self.exposure_workflows,
            clock=self.now, poll_midi=self.midi_application_input.poll_midi_connection,
            feedback_seconds=self.feedback_seconds)

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
                commit=self.practice_controls.commit_playback_intent,capture=self.transport_timing.playback_facts,
                abort=self.practice_controls.abort_playback,**values)

    def withdraw_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.withdraw(self.transport_timing.playback_facts(),**values)

    def report_playback_failure(self, **values) -> dict:
        with self.lock:
            self.playback.fail(notify_failure=self.practice_controls.on_playback_failure,**values)
            return {"accepted":True}

    def ports(self) -> list[str]:
        return self.midi_application_input.ports()

    def connect(self, name: str):
        return self.midi_application_input.connect(name)

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
                midi=self.midi, progress=self.progress, receive=self.midi_application_input.receive)

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

    def control(self, action: str, **kwargs) -> None:
        return self.practice_controls.control(action, **kwargs)

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
                self.practice_timeline.update()
                while self.midi_ingress.deferred:
                    message, received_at, corrected_at, _transport = self.midi_ingress.deferred.popleft()
                    self.midi_application_input.receive_message(message, received_at=received_at,
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

    def next_stage_score(self) -> bytes:
        return self.score_preload.next_stage_score()

    def report_preload_failure(self, *, fingerprint: str, step_number: int,
                               revision: int, error: str) -> dict:
        return self.score_preload.report_preload_failure(
            fingerprint=fingerprint, step_number=step_number,
            revision=revision, error=error)

    def acknowledge_preloaded_stage(self, *, stage_key: str, revision: int) -> dict:
        return self.score_preload.acknowledge_preloaded_stage(
            stage_key=stage_key, revision=revision)

    def semantic_score(self) -> dict:
        return self.score_read.semantic_score()

    def engraving(self) -> EngravedScore:
        return self.score_read.engraving()

    def geometry(self) -> dict:
        return self.score_read.geometry()

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.score_read.lesson_overview()
