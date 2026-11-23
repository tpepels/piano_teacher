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

from .attempt_progression import AttemptProgression
from .attempt_runtime import AttemptRuntime
from .attempt_settlement import AttemptSettlement
from .completion_continuations import TakeCompletion
from .settlement_continuation import SettlementContinuation
from .take_grading import TakeGrading
from .mistake_responses import resolve_mistake_policy
from .device_workflows import DeviceWorkflows
from .exposure_workflows import ExposureWorkflows
from .flow_course_session import PracticeFlowCourseSession
from .future_score import FutureScore
from .guided_session import GuidedSession
from .history_management import HistoryManagement, HistoryReads, PlanReinstallation
from .learner_progress import LearnerProgress
from .learning_capture import LearningCapture
from .learning_evidence_session import LearningEvidenceSession
from .lesson_cursor import LessonCursor
from .course_flow import CourseFlow, LessonNavigation
from .listen_session import ListenSession
from .live_feedback_workflows import LiveFeedbackWorkflows
from .midi_application_input import MidiCallback, MidiDelivery, MidiDeviceConnection
from .midi_connection import MidiConnection
from .midi_ingress import MidiIngress
from .midi_key_shortcuts import MidiKeyShortcuts
from .playback_coordinator import PlaybackCoordinator
from .playback_session import PlaybackSession
from .policy_registry import PolicyRegistry
from .practice_session import PracticeSession
from .command_router import CommandRouter
from .midi_epoch import MidiEpoch
from .session_routes import command_routes, event_handlers
from .tick_worker import TickWorker
from .tick_observations import TickObservations
from .pre_assessment_transitions import PreAssessmentTransitions
from .take_progression import TakeProgression
from .tick_publisher import TickPublisher
from .transport_actions import (
    PlaybackAuthorization, RetainedResultReplay, RouteCommands, TransportCommands)
from .learning_actions import LearningActions
from .practice_timeline import PracticeTimeline
from .recovery_streak import RecoveryStreak
from .recovery_workflows import SelectedRecovery, RollingRecovery
from .score_artifact_registry import ScoreArtifactRegistry
from .score_artifacts import ScoreArtifacts
from .score_preload_workflow import ScorePreloadWorkflow
from .score_read_services import ScoreReadServices
from .score_state_publisher import ScoreStatePublisher
from .session_evidence_context import SessionEvidenceContext
from .session_lifecycle import SessionLifecycle
from .session_notices import SessionNotices
from .session_phase import SessionPhase
from .session_read_models import (
    SessionCapture, ScorePresentation, SnapshotExtras, SessionReadModels)
from .session_snapshot_builder import SnapshotReadPorts
from .settings_workflows import SettingsWorkflows
from .source_identity import SourceIdentity
from .source_preparation_session import SourcePreparationSession
from .source_workflows import SourcePreparationWorkflow, SourceInstallation, LibraryOpening
from .listen_outcomes import ListenOutcomes
from .teaching_continuation import TeachingContinuation
from .teaching_workflows import TeachingDecisions
from .tempo_map_cache import TempoMapCache
from .timed_playback import TimedStart, PlaybackContinuation, PauseResume
from .lesson import Lesson
from .midi_input import MidiInput
from .score import Score
from .take import Take
from .transport import Transport
from .transport_timing import TransportTiming



def compose_application(data_dir: Path | None = None, enable_midi: bool = True,
                        feedback_events: FeedbackEventLog | None = None,
                        clock: Clock | None = None) -> dict:
    """Assemble the graph in dependency order, one cohesive stage at a time."""
    r = SimpleNamespace()
    _session_state(r, clock=clock, feedback_events=feedback_events)
    _devices_library_and_score(r, enable_midi=enable_midi, data_dir=data_dir)
    _persistence_and_settlement(r)
    _lesson_source_and_settings_workflows(r)
    _transport_and_completion(r)
    _event_boundary(r)
    return vars(r).copy()


def _session_state(r, *, clock, feedback_events) -> None:
    """Clock, lock and the authoritative session/transport state holders."""
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
    r.transport = Transport(timeline=r.visual_transport,
        session=r.playback_session, admission=r.playback)
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
    r.flow_session = PracticeFlowCourseSession(r.now, r.source_identity)
    # Lesson's decision owner needs settlement and evidence services; it is
    # attached once below, before any event can reach the session.
    r.lesson = Lesson(source=r.source_identity, cursor=r.lesson_cursor,
        guided=r.guided_session, flow=r.flow_session)
    # One short on-screen message at a time: (serial, text, engine time).
    r.guided_session.clear_selection()
    r.guided_session.set_hints(False,now=r.now())


def _devices_library_and_score(r, *, enable_midi, data_dir) -> None:
    """MIDI device, library and settings, Listen audio and score artifacts."""
    r.midi = MidiConnection(enabled=enable_midi, clock=r.now)
    r.live_input = LiveInputView()
    r.assessment = AssessmentService()
    r.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
    r.mistake_policy = lambda: resolve_mistake_policy(
        r.library.settings["mistake_response_strategy"])
    r.midi_key_shortcuts = MidiKeyShortcuts(r.library.settings["midi_key_ranges"])
    r.midi_input = MidiInput(midi=r.midi, shortcuts=r.midi_key_shortcuts,
        calibration=r.midi_calibration, live=r.live_input)
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
    r.score = Score(artifacts=r.score_artifact_registry,
        successor=r.teaching_continuation, publisher=r.score_state_publisher,
        tempo_maps=r.tempo_map_cache)


def _persistence_and_settlement(r) -> None:
    """One SQLite connection: progress, evidence, learner state, settlement."""
    r.progress = ProgressRepository(r._data_dir / "progress.db")
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
    r.midi_input.attach_ingress(r.midi_ingress)
    r.attempt_settlement = AttemptSettlement(r.progress, r.measurement,
        r.fukuda_mistakes, r.learner_progress)
    r.take = Take(runtime=r.attempt, settlement=r.attempt_settlement)
    r.learning_evidence = LearningEvidenceSession(
        r.progress, r.library, r.measurement, r.midi,
        r.midi_calibration)
    r.source_preparation = SourcePreparationSession()
    r.playback_session.bind_transport(transport=r.visual_transport,
        take=r.take, score=r.score, midi_input=r.midi_input,
        measurement=r.measurement, assessment=r.live_assessment,
        progression=r.attempt_progression, listen=r.listen, clock=r.now)
    r.session_lifecycle = SessionLifecycle(
        transport=r.transport, take=r.take, midi_input=r.midi_input,
        score=r.score, lesson=r.lesson, listen=r.listen,
        measurement=r.measurement, clock=r.now, progress=r.progress)


def _lesson_source_and_settings_workflows(r) -> None:
    """Lesson decisions, exposures, source/settings/device workflows."""
    r.plans = PlanReinstallation(
        lesson=r.lesson, recovery_streak=r.recovery_streak,
        transport=r.transport, score=r.score)
    r.history_reads = HistoryReads(
        lesson=r.lesson, learning_evidence=r.learning_evidence,
        progress=r.progress, data_dir=r._data_dir)
    r.history_management = HistoryManagement(
        lesson=r.lesson, notices=r.notices, progress=r.progress,
        measurement=r.measurement, lifecycle=r.session_lifecycle,
        take=r.take, transport=r.transport,
        plans=r.plans,
        reads=r.history_reads, clock=r.now)
    r.listen_outcomes = ListenOutcomes(
        listen=r.listen, transport=r.transport, notices=r.notices)
    r.source_workflows = SourcePreparationWorkflow(
        lesson=r.lesson, source_preparation=r.source_preparation,
        preprocessing=r.preprocessing, fingering=r.fingering,
        progress=r.progress, fukuda_mistakes=r.fukuda_mistakes,
        library=r.library, listen_outcomes=r.listen_outcomes, lock=r.lock)
    r.source_installation = SourceInstallation(
        lesson=r.lesson, notices=r.notices, lifecycle=r.session_lifecycle,
        plans=r.plans, transport=r.transport,
        source_preparation=r.source_preparation, score=r.score, take=r.take,
        listen=r.listen, listen_outcomes=r.listen_outcomes)
    r.library_opening = LibraryOpening(
        lesson=r.lesson, notices=r.notices, transport=r.transport,
        progress=r.progress, library=r.library)
    r.settings_workflows = SettingsWorkflows(
        library=r.library, measurement=r.measurement,
        lifecycle=r.session_lifecycle, notices=r.notices,
        policy_registry=r.policy_registry, midi_input=r.midi_input,
        transport=r.transport, progress=r.progress,
        library_health=r.library_health, lesson=r.lesson)
    r.device_workflows = DeviceWorkflows(
        midi_input=r.midi_input, lifecycle=r.session_lifecycle,
        lesson=r.lesson, notices=r.notices, transport=r.transport,
        library=r.library, clock=r.now)
    r.teaching_decisions = TeachingDecisions(
        source_identity=r.source_identity, lesson_cursor=r.lesson_cursor,
        take=r.take, measurement=r.measurement, transport=r.transport,
        guided_session=r.guided_session, recovery_streak=r.recovery_streak,
        policy_registry=r.policy_registry, library=r.library,
        fukuda_mistakes=r.fukuda_mistakes, learner_progress=r.learner_progress,
        learning_evidence=r.learning_evidence, clock=r.now)
    r.lesson.attach_decisions(r.teaching_decisions)
    r.evidence_context = SessionEvidenceContext(
        lesson=r.lesson, transport=r.transport,
        learning_evidence=r.learning_evidence)
    r.exposure_workflows = ExposureWorkflows(
        lesson=r.lesson, take=r.take, score=r.score, transport=r.transport,
        listen=r.listen, notices=r.notices, lifecycle=r.session_lifecycle,
        learner_progress=r.learner_progress, progress=r.progress,
        midi_input=r.midi_input, evidence_context=r.evidence_context,
        clock=r.now)

    r.course = CourseFlow(
        lesson=r.lesson, notices=r.notices,
        exposure_workflows=r.exposure_workflows, transport=r.transport,
        take=r.take, progress=r.progress, measurement=r.measurement,
        recovery_streak=r.recovery_streak, mistake_policy=r.mistake_policy,
        clock=r.now)
    r.navigation = LessonNavigation(
        lesson=r.lesson, notices=r.notices,
        exposure_workflows=r.exposure_workflows, transport=r.transport,
        take=r.take, learner_progress=r.learner_progress,
        progress=r.progress, lifecycle=r.session_lifecycle, course=r.course)

    r.score_read = ScoreReadServices(
        lesson=r.lesson, take=r.take, transport=r.transport,
        score_artifact_registry=r.score_artifact_registry,
        learner_progress=r.learner_progress, lock=r.lock)
    r.score.attach_read(r.score_read)

    r.transport_timing = TransportTiming(
        lesson=r.lesson, transport=r.transport, score=r.score,
        attempt_progression=r.attempt_progression, take=r.take,
        midi_input=r.midi_input, clock=r.now)

    r.session_phase = SessionPhase(
        transport=r.transport, lesson=r.lesson, midi_input=r.midi_input,
        take=r.take)



def _transport_and_completion(r) -> None:
    """Timed playback, live feedback, recovery, completion and read models."""
    r.timed_start = TimedStart(
        lesson=r.lesson, notices=r.notices, transport=r.transport, take=r.take,
        exposure_workflows=r.exposure_workflows, midi_input=r.midi_input,
        score=r.score, evidence_context=r.evidence_context,
        transport_timing=r.transport_timing, lock=r.lock)
    r.continuation = PlaybackContinuation(
        lesson=r.lesson, transport=r.transport,
        transport_timing=r.transport_timing, score=r.score,
        notices=r.notices, clock=r.now)
    r.pause_resume = PauseResume(
        lesson=r.lesson, transport=r.transport,
        transport_timing=r.transport_timing, midi_input=r.midi_input,
        listen_outcomes=r.listen_outcomes, notices=r.notices,
        phase=r.session_phase.at, clock=r.now)

    r.live_feedback_workflows = LiveFeedbackWorkflows(
        lesson=r.lesson, transport=r.transport, score=r.score,
        policy_registry=r.policy_registry, library=r.library, take=r.take,
        live_assessment=r.live_assessment, transport_timing=r.transport_timing,
        clock=r.now)

    r.take_grading = TakeGrading(
        lesson=r.lesson, take=r.take, transport=r.transport,
        transport_timing=r.transport_timing, score=r.score,
        policy_registry=r.policy_registry, mistake_policy=r.mistake_policy,
        assessment=r.assessment,
        live_feedback_workflows=r.live_feedback_workflows,
        measurement=r.measurement)
    r.selected_recovery = SelectedRecovery(
        lesson=r.lesson, notices=r.notices, take=r.take, transport=r.transport,
        transport_timing=r.transport_timing, continuation=r.continuation,
        course=r.course,
        exposure_workflows=r.exposure_workflows, clock=r.now)
    r.rolling_recovery = RollingRecovery(
        lesson=r.lesson, notices=r.notices, take=r.take, transport=r.transport,
        transport_timing=r.transport_timing, grading=r.take_grading,
        recovery_streak=r.recovery_streak,
        live_feedback_workflows=r.live_feedback_workflows, clock=r.now)

    r.settlement = SettlementContinuation(
        lesson=r.lesson, notices=r.notices, score=r.score, take=r.take,
        transport=r.transport, course=r.course,
        transport_timing=r.transport_timing,
        selected_recovery=r.selected_recovery,
        continuation=r.continuation,
        mistake_policy=r.take_grading.mistake_policy)
    r.completion_continuations = TakeCompletion(
        lesson=r.lesson, notices=r.notices, take=r.take, transport=r.transport,
        transport_timing=r.transport_timing, continuation=r.continuation,
        selected_recovery=r.selected_recovery,
        course=r.course, grading=r.take_grading,
        settlement=r.settlement)

    r.score_preload = ScorePreloadWorkflow(
        lesson=r.lesson, lock=r.lock, transport=r.transport, score=r.score,
        take=r.take, transport_timing=r.transport_timing,
        settlement=r.settlement)

    r.session_capture = SessionCapture(
        lesson=r.lesson, notices=r.notices, take=r.take, transport=r.transport,
        library=r.library, midi_input=r.midi_input, score=r.score,
        ports=SnapshotReadPorts(
            seek_grid=r.navigation.seek_grid,
            learner_snapshot=r.navigation.learner_snapshot,
            elapsed_beat=r.transport_timing.elapsed_beat,
            phase=r.session_phase.at,
            source_model=r.score.source_model,
            live_feedback=r.live_feedback_workflows.latest_marks,
            visual_motion=r.transport_timing.visual_motion,
            active_tempo_map=r.transport_timing.active_tempo_map,
            display_phrase=lambda: r.lesson.display_phrase(
                learning=r.transport.mode == "learn"),
            guided_marks=r.score.guided_marks,
            listen_snapshot=r.listen.snapshot,
            live_input_snapshot=r.midi_input.live_input_snapshot,
            preparation_schedule=r.transport.preparation_schedule,
            teaching_snapshot=None, clock=r.now),
        clock=r.now)
    r.score_presentation = ScorePresentation(
        lesson=r.lesson, transport=r.transport, timing=r.transport_timing, score=r.score,
        capture=r.session_capture, clock=r.now)
    r.read_models = SessionReadModels(
        lesson=r.lesson, transport=r.transport, timing=r.transport_timing,
        score=r.score, course=r.course,
        capture=r.session_capture, presentation=r.score_presentation,
        extras=SnapshotExtras(
            lesson=r.lesson, take=r.take, transport=r.transport,
            timing=r.transport_timing, library=r.library,
            midi_input=r.midi_input),
        lock=r.lock, clock=r.now)



def _event_boundary(r) -> None:
    """Command routers, MIDI input, the transition worker and PracticeSession."""
    r.learning_commands = LearningActions(
        lesson=r.lesson, transport=r.transport, course=r.course,
        navigation=r.navigation, exposure_workflows=r.exposure_workflows,
        measurement=r.measurement, clock=r.now)
    r.playback_authorization = PlaybackAuthorization(
        lesson=r.lesson, transport=r.transport,
        transport_timing=r.transport_timing, timed_start=r.timed_start,
        pause_resume=r.pause_resume,
        lifecycle=r.session_lifecycle, listen=r.listen,
        presentation=r.score_presentation, notices=r.notices, clock=r.now)
    r.retained_replay = RetainedResultReplay(
        lesson=r.lesson, take=r.take, transport=r.transport,
        settlement=r.settlement, rolling_recovery=r.rolling_recovery,
        notices=r.notices, clock=r.now)
    r.route_commands = RouteCommands(
        lesson=r.lesson, transport=r.transport,
        exposure_workflows=r.exposure_workflows,
        course=r.course, lifecycle=r.session_lifecycle,
        notices=r.notices)
    r.transport_commands = TransportCommands(
        lesson=r.lesson, transport=r.transport,
        transport_timing=r.transport_timing, pause_resume=r.pause_resume,
        score=r.score, routes=r.route_commands, replay=r.retained_replay,
        authorization=r.playback_authorization)

    r.midi_callback = MidiCallback(
        runtime_timings=r.runtime_timings, clock=r.now)
    r.midi_delivery = MidiDelivery(
        lesson=r.lesson, transport=r.transport, take=r.take,
        midi_input=r.midi_input, score=r.score, library=r.library,
        transport_timing=r.transport_timing,
        live_feedback_workflows=r.live_feedback_workflows,
        notices=r.notices, apply_shortcut=r.midi_callback.apply_shortcut)
    r.midi_device = MidiDeviceConnection(
        lesson=r.lesson, midi_input=r.midi_input,
        device_workflows=r.device_workflows,
        settings_workflows=r.settings_workflows,
        pause_resume=r.pause_resume,
        receive=r.midi_callback.receive, lock=r.lock)

    r.practice_timeline = PracticeTimeline(
        observations=TickObservations(
            lesson=r.lesson, transport=r.transport, take=r.take,
            midi_input=r.midi_input, listen_outcomes=r.listen_outcomes,
            measurement=r.measurement,
            poll_midi=r.midi_device.poll_midi_connection,
            clock=r.now),
        transitions=PreAssessmentTransitions(
            lesson=r.lesson, transport=r.transport, take=r.take,
            midi_input=r.midi_input, course=r.course,
            listen_outcomes=r.listen_outcomes,
            continuation=r.continuation, settlement=r.settlement),
        progression=TakeProgression(
            lesson=r.lesson, transport=r.transport, take=r.take,
            midi_input=r.midi_input, transport_timing=r.transport_timing,
            attempt_progression=r.attempt_progression,
            rolling_recovery=r.rolling_recovery,
            completion=r.completion_continuations,))
    r.tick_publisher = TickPublisher(
        transport=r.transport, transport_timing=r.transport_timing,
        presentation=r.score_presentation,
        live_feedback_workflows=r.live_feedback_workflows)
    r.midi_epoch = MidiEpoch(
        lesson=r.lesson, transport=r.transport, take=r.take,
        midi_input=r.midi_input,
        corrected_time=r.midi_delivery.corrected_time)
    r.command_router = CommandRouter(
        lesson=r.lesson, transport=r.transport, take=r.take,
        read_models=r.read_models,
        presentation=r.score_presentation, measurement=r.measurement,
        listen_outcomes=r.listen_outcomes,
        routes=command_routes(
            device_workflows=r.device_workflows,
            settings_workflows=r.settings_workflows, midi_input=r.midi_input,
            transport=r.transport, pause_resume=r.pause_resume,
            history_management=r.history_management,
            transport_commands=r.transport_commands,
            playback_authorization=r.playback_authorization,
            learning_commands=r.learning_commands,
            navigation=r.navigation))
    r.tick_worker = TickWorker(
        timeline=r.practice_timeline, publisher=r.tick_publisher,
        transport=r.transport, take=r.take,
        lesson=r.lesson, midi_input=r.midi_input, epoch=r.midi_epoch,
        deliver=r.midi_delivery.deliver, notices=r.notices,
        clock=r.now)
    r.practice_session = PracticeSession(
        lock=r.lock, epoch=r.midi_epoch,
        runtime_timings=r.runtime_timings, clock=r.now)
    r.practice_session.bind_handlers(event_handlers(
        commands=r.command_router, tick=r.tick_worker, epoch=r.midi_epoch,
        midi_input=r.midi_input,
        midi_delivery=r.midi_delivery, midi_device=r.midi_device,
        midi_callback=r.midi_callback,
        settings_workflows=r.settings_workflows,
        pause_resume=r.pause_resume,
        playback_authorization=r.playback_authorization,
        source_installation=r.source_installation,
        library_opening=r.library_opening, lesson=r.lesson,
        course=r.course, score_preload=r.score_preload,
        device_workflows=r.device_workflows,
        history_management=r.history_management,
        history_reads=r.history_reads,
        lifecycle=r.session_lifecycle))
    r.midi_callback.bind_session(r.practice_session)
