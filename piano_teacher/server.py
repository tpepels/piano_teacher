"""Embedded Piano Teacher facade for the canonical in-process Godot runtime.

Services own practice, MIDI, grading, source, timing, score and persistent
state. This boundary exposes the stable native operations and read ports.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .application.composition import compose_application
from .application.session_events import (
    PlaybackFailed, SourceCommitted,
    FingeringCorrectionCommitted, SettingsChanged,
    DeviceSelected, MidiPortsRequested, PreloadReady, PreloadFailed, SessionClosed,
    HardwareRequested, HistoryExported,
    PieceHistoryDeleted, LearnerHistoryDeleted)
from .clock import Clock
from .feedback_events import FeedbackEventLog
from . import state_contract


class PracticeEngine:
    # Public observations of independently owned application session facts.

    # Public transport observations; only PlaybackSession stores these flags.

    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True,
                 feedback_events: FeedbackEventLog | None = None,
                 clock: Clock | None = None):
        self.__dict__.update(compose_application(
            data_dir=data_dir, enable_midi=enable_midi,
            feedback_events=feedback_events, clock=clock))

    def playback_status(self) -> dict:
        with self.lock:
            return self.transport.status(self.transport_timing.playback_facts())

    def report_playback_failure(self, **values) -> dict:
        return self.practice_session.apply(PlaybackFailed(values))

    def ports(self) -> list[str]:
        return self.practice_session.apply(MidiPortsRequested())

    def connect(self, name: str):
        return self.practice_session.apply(DeviceSelected(name))

    def hardware_diagnostics_action(self, action: str) -> dict:
        return self.practice_session.apply(HardwareRequested(action))

    def library_listing(self) -> dict:
        with self.lock:
            return self.library.scan()

    def library_health_status(self) -> dict:
        return self.library_health.snapshot()

    def start_library_health(self) -> dict:
        return self.library_health.start()

    def preferences(self) -> dict:
        with self.lock:
            return self.settings_workflows.preferences()

    def learning_history_status(self) -> dict:
        with self.lock:
            return self.history_reads.status()

    def learning_statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        return self.history_reads.statistics(fingerprint, query=query)

    def export_learning_history(self, path: str, include_detail: bool = False) -> dict:
        return self.practice_session.apply(HistoryExported(path, include_detail))

    def delete_piece_history(self, fingerprint: str, confirm: bool = False) -> dict:
        return self.practice_session.apply(PieceHistoryDeleted(fingerprint, confirm))

    def delete_learner_history(self, confirm: bool = False) -> dict:
        return self.practice_session.apply(LearnerHistoryDeleted(confirm))

    def close(self) -> None:
        """Close the session, then wait for the Listen audio worker to stop."""
        worker = self.listen.thread
        self.practice_session.apply(SessionClosed())
        if worker is not None:
            worker.join(10)
            if worker.is_alive():
                raise RuntimeError("Listen audio worker did not stop")

    def set_preferences(self, **changes) -> dict:
        return self.practice_session.apply(SettingsChanged(changes))

    def load_library(self, identifier: str) -> None:
        with self.lock:
            path = self.library.resolve(identifier)
        self.load(str(path), opened_identifier=identifier)

    def performance_diagnostics(self) -> dict:
        return self.runtime_timings.snapshot()

    def load(self, path: str, *, opened_identifier: str | None = None):
        """Commit a prepared source under one mutation guard and short lock."""
        diagnostics = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = time.perf_counter()
        with self.source_preparation.source_mutation():
            prepared = self.source_workflows.prepare(
                path, diagnostics=diagnostics)
            self.practice_session.apply(
                SourceCommitted(prepared, opened_identifier))
        if diagnostics:
            print("SCORE_LOAD_STAGE: ready",
                  round((time.perf_counter()-began)*1000,1),
                  "ms total",prepared.path.name,flush=True)

    def correct_fingering(self, source_id: str, finger: int | None,
                         *, fingerprint: str | None = None) -> None:
        identity = self.source_workflows.correction_identity(
            fingerprint=fingerprint)
        with self.source_preparation.source_mutation():
            # Preserve original-note/generation identity across inference,
            # then commit only the validated revision inside PracticeSession.
            corrected = self.source_workflows.prepare_fingering_correction(
                identity, source_id=source_id, finger=finger)
            self.practice_session.apply(FingeringCorrectionCommitted(corrected))

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            return self.listen.audio_path(token)

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
        return self.practice_session.apply(
            PreloadFailed(fingerprint, step_number, revision, error))

    def acknowledge_preloaded_stage(self, *, stage_key: str, revision: int) -> dict:
        return self.practice_session.apply(PreloadReady(stage_key, revision))

    def semantic_score(self) -> dict:
        return self.score.semantic_score()

    def geometry(self) -> dict:
        return self.score.geometry()

    def score_bundle(self) -> dict:
        return self.score.bundle()

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.score.lesson_overview()
