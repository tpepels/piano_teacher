"""Construct the single embedded application graph and its explicit owners.

This is a composition root only. The temporary namespace exists solely while
objects are wired and is returned as initial facade attributes. It is never
injected into a domain, playback, engraving or grading service: each service
continues receiving its own explicit constructor dependencies.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import threading
import time

from ..assessment_service import AssessmentService
from ..clock import Clock
from ..clock import monotonic
from ..feedback_events import FeedbackEventLog
from ..fingering import FingeringService
from ..fukuda_mistake_store import FukudaMistakeStore
from ..lesson_settings import SETTINGS
from ..library import ScoreLibrary
from ..library_health import LibraryHealth
from ..live_assessment_publisher import LiveAssessmentPublisher
from ..live_input_view import LiveInputView
from ..midi_calibration import MidiTapCalibration
from ..preprocessing_cache import PreprocessingCache
from ..progress_repository import ProgressRepository
from ..runtime_timings import RuntimeTimings
from ..visual_transport import VisualTransport

from .application_worker import ApplicationWorker
from .attempt_progression import AttemptProgression
from .attempt_runtime import AttemptRuntime
from .attempt_settlement import AttemptSettlement
from .completion_continuations import CompletionContinuations
from .device_workflows import DeviceWorkflows
from .exposure_installer import ExposureInstaller
from .exposure_workflows import ExposureWorkflows
from .flow_course_session import PracticeFlowCourseSession
from .future_score import FutureScore
from .guided_session import GuidedSession
from .history_management import HistoryManagement
from .learner_progress import LearnerProgress
from .learning_capture import LearningCapture
from .learning_evidence_session import LearningEvidenceSession
from .lesson_cursor import LessonCursor
from .lesson_execution import LessonExecution
from .listen_session import ListenSession
from .live_feedback_workflows import LiveFeedbackWorkflows
from .midi_application_input import MidiApplicationInput
from .midi_connection import MidiConnection
from .midi_ingress import MidiIngress
from .midi_key_shortcuts import MidiKeyShortcuts
from .playback_coordinator import PlaybackCoordinator
from .playback_session import PlaybackSession
from .policy_registry import PolicyRegistry
from .post_assessment_effects import PostAssessmentEffects
from .practice_controls import PracticeControls
from .transport_actions import TransportActions
from .learning_actions import LearningActions
from .practice_timeline import PracticeTimeline
from .recovery_streak import RecoveryStreak
from .recovery_workflows import RecoveryWorkflows
from .score_artifact_registry import ScoreArtifactRegistry
from .score_artifacts import ScoreArtifacts
from .score_preload_workflow import ScorePreloadWorkflow
from .score_read_services import ScoreReadServices
from .score_state_publisher import ScoreStatePublisher
from .session_commands import SessionCommands
from .session_evidence_context import SessionEvidenceContext
from .session_lifecycle import SessionLifecycle
from .session_notices import SessionNotices
from .session_phase import SessionPhase
from .session_read_models import SessionReadModels
from .settings_workflows import SettingsWorkflows
from .source_identity import SourceIdentity
from .source_preparation_session import SourcePreparationSession
from .source_workflows import SourceWorkflows
from .teaching_continuation import TeachingContinuation
from .teaching_workflows import TeachingDecisions
from .tempo_map_cache import TempoMapCache
from .timed_playback import TimedPlayback
from .transport_timing import TransportTiming


def compose_application(data_dir: Path | None = None, enable_midi: bool = True,
                        feedback_events: FeedbackEventLog | None = None,
                        clock: Clock | None = None) -> dict:
    r = SimpleNamespace()
    # The one monotonic clock of this session; collaborators receive it.
    r.now: Clock = clock if clock is not None else monotonic
    r.lock = threading.RLock()
    r.guided_session = GuidedSession(clock=r.now)
    r.attempt = AttemptRuntime()
    r.recovery_streak = RecoveryStreak()
    r.source_identity = SourceIdentity()
    r.lesson_cursor = LessonCursor()
    r.notices = SessionNotices()
    r.visual_transport = VisualTransport(
        _visual_rewind_seconds=SETTINGS.feedback_seconds)
    r.playback = PlaybackCoordinator()
    r.playback_session = PlaybackSession()
    r.tempo_map_cache = TempoMapCache()
    r.attempt_progression = AttemptProgression()
    r.feedback_seconds = SETTINGS.feedback_seconds
    r.midi_calibration = MidiTapCalibration()
    # The single acknowledged note-feedback channel to the score: provisional
    # attack/release events and authoritative per-note assessments.
    r.feedback_events = (feedback_events if feedback_events is not None
                            else FeedbackEventLog())
    r.live_assessment = LiveAssessmentPublisher(r.feedback_events)
    r.runtime_timings = RuntimeTimings()
    r.flow_session = PracticeFlowCourseSession(r.now)
    # One short on-screen message at a time: (serial, text, engine time).
    r.guided_session.clear_selection()
    r.guided_session.set_hints(False,now=r.now())
    r.midi = MidiConnection(enabled=enable_midi, clock=r.now)
    r.live_input = LiveInputView()
    r.assessment = AssessmentService()
    r.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
    r.midi_key_shortcuts = MidiKeyShortcuts(r.library.settings["midi_key_ranges"])
    r.library_health = LibraryHealth(r.library)
    data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
    data_dir.mkdir(parents=True, exist_ok=True)
    r._data_dir = data_dir
    r.listen = ListenSession(data_dir / "demo-audio", lock=r.lock)
    r.fingering = FingeringService(data_dir / "fingering")
    r.preprocessing = PreprocessingCache(data_dir / "preprocessed")
    r.score_artifact_registry = ScoreArtifactRegistry(ScoreArtifacts(r.preprocessing))
    future_score = FutureScore(data_dir / "preprocessed", clock=r.now)
    r.teaching_continuation = TeachingContinuation(future_score,r.visual_transport)
    # The untimed guided engine owns repeat presentation epochs; no
    # Godot-side guess about missed notes or lesson progression.
    r.score_state_publisher = ScoreStatePublisher()
    r.progress = ProgressRepository(data_dir / "progress.db")
    # Keep the public db handle for LearnerStateStore and existing clients.
    r.db = r.progress.db
    r.measurement = LearningCapture(r.progress.ledger, clock=r.now)
    r.progress.ledger.prune(days=r.library.settings["evidence_retention_days"],
                               budget_mib=r.library.settings["evidence_budget_mib"])
    r.fukuda_mistakes = FukudaMistakeStore(r.db)
    r.learner_store = r.progress.learner_store
    r.learner_progress = LearnerProgress(r.learner_store)
    r.policy_registry = PolicyRegistry(
        assessment=r.assessment, ledger=r.progress.ledger,
        settings=r.library.settings)
    r.midi_ingress = MidiIngress(r.midi,r.midi_calibration,r.midi_key_shortcuts,
        r.live_input,r.measurement,r.feedback_events)
    r.session_commands = SessionCommands()
    r.attempt_settlement = AttemptSettlement(r.progress, r.measurement,
        r.fukuda_mistakes, r.learner_progress)
    r.learning_evidence = LearningEvidenceSession(
        r.progress, r.library, r.measurement, r.midi,
        r.midi_calibration)
    r.source_preparation = SourcePreparationSession()
    r.playback_session.bind_transport(transport=r.visual_transport,
        midi=r.midi_ingress,attempt=r.attempt,
        settlement=r.attempt_settlement,measurement=r.measurement,
        continuation=r.teaching_continuation,live_input=r.live_input,
        assessment=r.live_assessment,progression=r.attempt_progression,
        listen=r.listen,clock=r.now)
    r.session_lifecycle = SessionLifecycle(
        playback=r.playback, playback_session=r.playback_session,
        attempt=r.attempt, settlement=r.attempt_settlement,
        midi_ingress=r.midi_ingress, visual_transport=r.visual_transport,
        continuation=r.teaching_continuation,
        guided_session=r.guided_session, live_input=r.live_input,
        listen=r.listen, measurement=r.measurement, clock=r.now)
    r.history_management = HistoryManagement(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, progress=r.progress, measurement=r.measurement,
        recovery_streak=r.recovery_streak, lifecycle=r.session_lifecycle,
        attempt_settlement=r.attempt_settlement, attempt=r.attempt,
        playback_session=r.playback_session, guided_session=r.guided_session,
        score_artifact_registry=r.score_artifact_registry,
        learning_evidence=r.learning_evidence, clock=r.now,
        data_dir=r._data_dir)
    r.source_workflows = SourceWorkflows(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, lifecycle=r.session_lifecycle,
        recovery_streak=r.recovery_streak,
        visual_transport=r.visual_transport,
        source_preparation=r.source_preparation,
        playback_session=r.playback_session, guided_session=r.guided_session,
        score_artifact_registry=r.score_artifact_registry,
        attempt=r.attempt, listen=r.listen,
        preprocessing=r.preprocessing, fingering=r.fingering,
        progress=r.progress, fukuda_mistakes=r.fukuda_mistakes,
        library=r.library, library_health=r.library_health,
        flow_session=r.flow_session, lock=r.lock)
    r.settings_workflows = SettingsWorkflows(
        library=r.library, measurement=r.measurement,
        lifecycle=r.session_lifecycle, notices=r.notices,
        policy_registry=r.policy_registry,
        midi_key_shortcuts=r.midi_key_shortcuts,
        playback_session=r.playback_session,
        visual_transport=r.visual_transport, progress=r.progress,
        library_health=r.library_health, source_identity=r.source_identity)
    r.device_workflows = DeviceWorkflows(
        midi=r.midi, shortcuts=r.midi_key_shortcuts,
        live_input=r.live_input, lifecycle=r.session_lifecycle,
        guided_session=r.guided_session, notices=r.notices,
        playback_session=r.playback_session,
        calibration=r.midi_calibration, library=r.library,
        clock=r.now)
    r.teaching_decisions = TeachingDecisions(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        attempt=r.attempt, attempt_settlement=r.attempt_settlement,
        measurement=r.measurement, playback_session=r.playback_session,
        visual_transport=r.visual_transport,
        guided_session=r.guided_session, recovery_streak=r.recovery_streak,
        policy_registry=r.policy_registry, library=r.library,
        fukuda_mistakes=r.fukuda_mistakes,
        learner_progress=r.learner_progress,
        session_commands=r.session_commands,
        learning_evidence=r.learning_evidence, clock=r.now)
    r.evidence_context = SessionEvidenceContext(
        source_identity=r.source_identity, playback_session=r.playback_session,
        guided_session=r.guided_session, learning_evidence=r.learning_evidence)
    r.exposure_installer = ExposureInstaller(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, lifecycle=r.session_lifecycle,
        learner_progress=r.learner_progress, progress=r.progress,
        score_state_publisher=r.score_state_publisher,
        attempt=r.attempt, playback_session=r.playback_session,
        guided_session=r.guided_session, visual_transport=r.visual_transport,
        midi=r.midi, listen=r.listen, evidence_context=r.evidence_context,
        session_commands=r.session_commands, clock=r.now)
    r.exposure_workflows = ExposureWorkflows(
        source_identity=r.source_identity, flow_session=r.flow_session,
        teaching_decisions=r.teaching_decisions, session_commands=r.session_commands,
        guided_session=r.guided_session, attempt=r.attempt,
        tempo_map_cache=r.tempo_map_cache, playback_session=r.playback_session,
        listen=r.listen, notices=r.notices, installer=r.exposure_installer)

    r.lesson_execution = LessonExecution(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, teaching_decisions=r.teaching_decisions,
        exposure_workflows=r.exposure_workflows,
        exposure_installer=r.exposure_installer, flow_session=r.flow_session,
        playback_session=r.playback_session, guided_session=r.guided_session,
        attempt=r.attempt, learner_progress=r.learner_progress,
        progress=r.progress, lifecycle=r.session_lifecycle,
        recovery_streak=r.recovery_streak, visual_transport=r.visual_transport,
        attempt_settlement=r.attempt_settlement, measurement=r.measurement,
        library=r.library, clock=r.now, session_commands=r.session_commands)

    r.score_read = ScoreReadServices(
        source_identity=r.source_identity, attempt=r.attempt,
        lesson_execution=r.lesson_execution,
        guided_session=r.guided_session,
        score_artifact_registry=r.score_artifact_registry,
        learner_progress=r.learner_progress, lock=r.lock)

    r.transport_timing = TransportTiming(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        playback_session=r.playback_session,
        visual_transport=r.visual_transport, tempo_map_cache=r.tempo_map_cache,
        attempt_progression=r.attempt_progression,
        attempt_settlement=r.attempt_settlement, score_read=r.score_read,
        midi_ingress=r.midi_ingress, playback=r.playback, clock=r.now)

    r.session_phase = SessionPhase(
        visual_transport=r.visual_transport,
        playback_session=r.playback_session,
        guided_session=r.guided_session, midi_ingress=r.midi_ingress,
        attempt=r.attempt, attempt_settlement=r.attempt_settlement)

    r.timed_playback = TimedPlayback(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, playback_session=r.playback_session,
        playback=r.playback, attempt_settlement=r.attempt_settlement,
        session_commands=r.session_commands, teaching_decisions=r.teaching_decisions,
        exposure_workflows=r.exposure_workflows, guided_session=r.guided_session,
        visual_transport=r.visual_transport, midi=r.midi,
        score_read=r.score_read, evidence_context=r.evidence_context,
        transport_timing=r.transport_timing, lesson_execution=r.lesson_execution,
        clock=r.now, lock=r.lock, phase=r.session_phase.at)

    r.live_feedback_workflows = LiveFeedbackWorkflows(
        source_identity=r.source_identity, playback_session=r.playback_session,
        visual_transport=r.visual_transport,
        score_artifact_registry=r.score_artifact_registry,
        score_read=r.score_read, policy_registry=r.policy_registry,
        library=r.library, attempt=r.attempt,
        live_assessment=r.live_assessment,
        transport_timing=r.transport_timing, clock=r.now)

    r.outcome_effects = PostAssessmentEffects(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, attempt_settlement=r.attempt_settlement,
        teaching_decisions=r.teaching_decisions, clock=r.now,
        teaching_continuation=r.teaching_continuation, library=r.library,
        visual_transport=r.visual_transport, attempt=r.attempt,
        lesson_execution=r.lesson_execution, playback_session=r.playback_session,
        score_artifact_registry=r.score_artifact_registry,
        transport_timing=r.transport_timing, assessment=r.assessment,
        feedback_seconds=r.feedback_seconds)

    r.recovery_workflows = RecoveryWorkflows(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, attempt=r.attempt,
        playback_session=r.playback_session, visual_transport=r.visual_transport,
        transport_timing=r.transport_timing, timed_playback=r.timed_playback,
        lesson_execution=r.lesson_execution,
        exposure_workflows=r.exposure_workflows,
        attempt_settlement=r.attempt_settlement, policy_registry=r.policy_registry,
        library=r.library, recovery_streak=r.recovery_streak,
        live_feedback_workflows=r.live_feedback_workflows,
        live_assessment=r.live_assessment,
        teaching_decisions=r.teaching_decisions,
        clock=r.now, feedback_seconds=r.feedback_seconds)

    r.completion_continuations = CompletionContinuations(
        source_identity=r.source_identity, notices=r.notices,
        teaching_continuation=r.teaching_continuation,
        attempt_settlement=r.attempt_settlement,
        playback_session=r.playback_session,
        visual_transport=r.visual_transport, attempt=r.attempt,
        flow_session=r.flow_session, lesson_execution=r.lesson_execution,
        transport_timing=r.transport_timing, score_read=r.score_read,
        recovery_workflows=r.recovery_workflows,
        timed_playback=r.timed_playback, outcome_effects=r.outcome_effects)

    r.score_preload = ScorePreloadWorkflow(
        source_identity=r.source_identity, lock=r.lock,
        playback_session=r.playback_session,
        teaching_continuation=r.teaching_continuation,
        attempt_settlement=r.attempt_settlement,
        transport_timing=r.transport_timing,
        completion_continuations=r.completion_continuations)

    r.read_models = SessionReadModels(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        notices=r.notices, attempt=r.attempt,
        guided_session=r.guided_session, playback_session=r.playback_session,
        visual_transport=r.visual_transport, playback=r.playback,
        attempt_settlement=r.attempt_settlement, library=r.library,
        midi=r.midi, midi_ingress=r.midi_ingress,
        midi_key_shortcuts=r.midi_key_shortcuts, midi_calibration=r.midi_calibration,
        attempt_progression=r.attempt_progression,
        score_state_publisher=r.score_state_publisher,
        lesson_execution=r.lesson_execution, score_read=r.score_read,
        listen=r.listen, live_input=r.live_input,
        live_assessment=r.live_assessment, lock=r.lock, clock=r.now,
        phase=r.session_phase.at, elapsed_beat=r.transport_timing.elapsed_beat,
        visual_motion=r.transport_timing.visual_motion, tempo_map=r.transport_timing.active_tempo_map,
        next_count_in_beats=r.transport_timing.next_count_in_beats,
        next_count_in_meter=r.transport_timing.next_count_in_meter,
        start_rate_bpm=r.transport_timing.start_rate_bpm,
        presentation_bpm=r.transport_timing.presentation_bpm)

    r.learning_commands = LearningActions(
        attempt=r.attempt, attempt_settlement=r.attempt_settlement, clock=r.now,
        exposure_workflows=r.exposure_workflows, flow_session=r.flow_session, guided_session=r.guided_session,
        lesson_cursor=r.lesson_cursor, lesson_execution=r.lesson_execution, lifecycle=r.session_lifecycle,
        measurement=r.measurement, notices=r.notices, playback_session=r.playback_session,
        progress=r.progress, session_commands=r.session_commands, source_identity=r.source_identity,
        teaching_decisions=r.teaching_decisions)

    r.transport_commands = TransportActions(
        attempt=r.attempt, attempt_settlement=r.attempt_settlement, clock=r.now,
        exposure_workflows=r.exposure_workflows, feedback_seconds=r.feedback_seconds, guided_session=r.guided_session,
        lesson_cursor=r.lesson_cursor, lesson_execution=r.lesson_execution, lifecycle=r.session_lifecycle,
        listen=r.listen, notices=r.notices, outcome_effects=r.outcome_effects,
        playback=r.playback, playback_session=r.playback_session, read_models=r.read_models,
        recovery_workflows=r.recovery_workflows, score_artifact_registry=r.score_artifact_registry, score_read=r.score_read,
        session_commands=r.session_commands, source_identity=r.source_identity, teaching_decisions=r.teaching_decisions,
        timed_playback=r.timed_playback, transport_timing=r.transport_timing, visual_transport=r.visual_transport)

    r.practice_controls = PracticeControls(
        attempt=r.attempt, attempt_settlement=r.attempt_settlement, device_workflows=r.device_workflows,
        exposure_workflows=r.exposure_workflows, history_management=r.history_management, learning_commands=r.learning_commands,
        lock=r.lock, measurement=r.measurement, midi=r.midi,
        midi_key_shortcuts=r.midi_key_shortcuts, playback_session=r.playback_session, read_models=r.read_models,
        session_commands=r.session_commands, settings_workflows=r.settings_workflows, source_identity=r.source_identity,
        teaching_decisions=r.teaching_decisions, timed_playback=r.timed_playback, transport_commands=r.transport_commands,
        visual_transport=r.visual_transport)

    r.midi_application_input = MidiApplicationInput(
        source_identity=r.source_identity, visual_transport=r.visual_transport,
        playback_session=r.playback_session, attempt_settlement=r.attempt_settlement,
        attempt=r.attempt, playback=r.playback, midi=r.midi, lock=r.lock,
        runtime_timings=r.runtime_timings, device_workflows=r.device_workflows,
        teaching_decisions=r.teaching_decisions,
        settings_workflows=r.settings_workflows, library=r.library,
        midi_ingress=r.midi_ingress, transport_timing=r.transport_timing,
        live_feedback_workflows=r.live_feedback_workflows,
        guided_session=r.guided_session, practice_controls=r.practice_controls,
        timed_playback=r.timed_playback, clock=r.now)

    r.practice_timeline = PracticeTimeline(
        source_identity=r.source_identity, notices=r.notices, visual_transport=r.visual_transport,
        playback_session=r.playback_session, playback=r.playback,
        attempt_settlement=r.attempt_settlement, attempt=r.attempt,
        transport_timing=r.transport_timing, timed_playback=r.timed_playback,
        score_read=r.score_read, outcome_effects=r.outcome_effects,
        lesson_execution=r.lesson_execution, recovery_workflows=r.recovery_workflows,
        completion_continuations=r.completion_continuations,
        live_feedback_workflows=r.live_feedback_workflows,
        live_assessment=r.live_assessment, measurement=r.measurement,
        policy_registry=r.policy_registry, library=r.library,
        teaching_decisions=r.teaching_decisions,
        guided_session=r.guided_session, flow_session=r.flow_session,
        midi=r.midi, listen=r.listen, midi_ingress=r.midi_ingress,
        midi_calibration=r.midi_calibration,
        attempt_progression=r.attempt_progression, read_models=r.read_models,
        teaching_continuation=r.teaching_continuation,
        exposure_workflows=r.exposure_workflows,
        clock=r.now, poll_midi=r.midi_application_input.poll_midi_connection,
        feedback_seconds=r.feedback_seconds)
    r.application_worker = ApplicationWorker(
        lock=r.lock, timeline=r.practice_timeline,
        midi_ingress=r.midi_ingress,
        midi_application_input=r.midi_application_input,
        source_identity=r.source_identity,
        visual_transport=r.visual_transport,
        playback_session=r.playback_session,
        attempt_settlement=r.attempt_settlement,
        runtime_timings=r.runtime_timings)
    return vars(r).copy()
