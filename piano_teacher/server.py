"""Embedded Piano Teacher facade for the canonical in-process Godot runtime.

Services own practice, MIDI, grading, source, timing, score and persistent
state. This boundary exposes the stable native operations and read ports.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .application.composition import compose_application
from .application.practice_assessment import PracticeAssessmentPolicies
from .application.score_artifacts import ScoreArtifacts
from .clock import Clock
from .feedback_events import FeedbackEventLog
from .learning import LearningPlan
from .practice_history import PracticePolicyService
from .engraving.engraving import EngravedScore
from .music import Phrase
from .warmups import is_warmup
from . import state_contract


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
                commit=self.transport_commands.commit_playback_intent,capture=self.transport_timing.playback_facts,
                abort=self.transport_commands.abort_playback,**values)

    def withdraw_playback(self, **values) -> dict:
        with self.lock:
            return self.playback.withdraw(self.transport_timing.playback_facts(),**values)

    def report_playback_failure(self, **values) -> dict:
        with self.lock:
            self.playback.fail(notify_failure=self.transport_commands.on_playback_failure,**values)
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

    def learning_history_status(self) -> dict:
        with self.lock:
            return self.history_management.status()

    def learning_statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        return self.history_management.statistics(fingerprint, query=query)

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

    @property
    def flow(self) -> practice_flow.FlowState | None:
        return self.flow_session.state

    def display_phrase(self) -> Phrase:
        return self.lesson_execution.display_phrase()

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            return self.listen.audio_path(token)

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
        return self.practice_session.control(action, **kwargs)

    def advance_clock(self) -> int:
        """Advance the embedded native worker's monotonic application tick."""
        return self.practice_session.advance()

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
