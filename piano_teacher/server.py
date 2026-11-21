"""Embedded Piano Teacher application facade for native Godot operations.

The composition root constructs narrowly owned services. This class retains
the locked public entry, read API, musical worker and lifetime operations.
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
from .application.composition import compose_application
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
        self.__dict__.update(compose_application(
            data_dir=data_dir, enable_midi=enable_midi,
            feedback_events=feedback_events, clock=clock))

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
        """Advance the embedded native worker's monotonic application tick."""
        return self.application_worker.advance()

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
