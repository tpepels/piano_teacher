"""Embedded Piano Teacher facade for the canonical in-process Godot runtime.

Services own practice, MIDI, grading, source, timing, score and persistent
state. This boundary exposes the stable native operations and read ports.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .application.composition import compose_application
from .application.session_events import (
    PlaybackFailed, SourceCommitted,
    FingeringCorrectionCommitted, SettingsChanged,
    DeviceSelected, MidiPortsRequested, SessionClosed,
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
                 clock: Clock | None = None, *, shutdown_requested=None):
        self.__dict__.update(compose_application(
            data_dir=data_dir, enable_midi=enable_midi,
            feedback_events=feedback_events, clock=clock,
            shutdown_requested=shutdown_requested))

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
            listing = self.library.scan()
            if self.startup_notice:
                listing["notice"] = self.startup_notice
        # Hashing every file can take a while on a large first scan: never
        # while holding the lock that state polls and MIDI delivery need.
        self.library.add_fingerprints(listing)
        with self.lock:
            saved = self.progress.summaries()
        for piece in listing["pieces"]:
            summary = saved.get(piece.get("fingerprint", ""))
            if summary is not None:
                piece["progress"] = summary
        return listing

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
        """Reap the score process and close the session and Listen worker."""
        self.score_read.process.close()
        worker = self.listen.thread
        self.practice_session.apply(SessionClosed())
        if worker is not None:
            worker.join(10)
            if worker.is_alive():
                raise RuntimeError("Listen audio worker did not stop")

    def set_preferences(self, **changes) -> dict:
        return self.practice_session.apply(SettingsChanged(changes))

    def load_library(self, identifier: str, *, cancelled=None, commit=None) -> None:
        with self.lock:
            path = self.library.resolve(identifier)
        self.load(str(path), opened_identifier=identifier, cancelled=cancelled, commit=commit)

    def start_sight_reading(self, level: int, tempo: str, *, cancelled=None, commit=None) -> None:
        from .sight_reading import new_round
        from .application.source_preparation_session import PreparedSource
        with self.source_preparation.source_mutation(cancelled):
            plan, fingerprint = new_round(level, tempo)
            self._commit_source(SourceCommitted(
                PreparedSource(Path("Sight reading " + fingerprint + ".mid"),
                               fingerprint,plan,False)), commit)

    def performance_diagnostics(self) -> dict:
        return self.runtime_timings.snapshot()

    def load(self, path: str, *, opened_identifier: str | None = None, cancelled=None, commit=None):
        """Commit a prepared source under one mutation guard and short lock."""
        diagnostics = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = time.perf_counter()
        with self.source_preparation.source_mutation(cancelled):
            prepared = self.source_workflows.prepare(
                path, diagnostics=diagnostics)
            self._commit_source(SourceCommitted(prepared, opened_identifier), commit)
        if diagnostics:
            print("SCORE_LOAD_STAGE: ready",
                  round((time.perf_counter()-began)*1000,1),
                  "ms total",prepared.path.name,flush=True)

    def correct_fingering(self, source_id: str, finger: int | None,
                         *, fingerprint: str | None = None, commit=None) -> None:
        identity = self.source_workflows.correction_identity(
            fingerprint=fingerprint)
        with self.source_preparation.source_mutation():
            # Preserve original-note/generation identity across inference,
            # then commit only the validated revision inside PracticeSession.
            corrected = self.source_workflows.prepare_fingering_correction(
                identity, source_id=source_id, finger=finger)
            self._commit_source(FingeringCorrectionCommitted(corrected), commit)

    def _commit_source(self, event, commit):
        if commit is not None:
            commit(event)
        else:
            with self.lock:
                self.source_preparation.checkpoint()
                self.practice_session.apply(event)

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

    def report_placement(self, facts: dict) -> None:
        """Godot's current score placement facts, sent with each poll."""
        unknown = set(facts) - {"ink_ahead_beats", "free_travel_beats",
                                "placement_revision", "presented_segment"}
        if unknown:
            raise ValueError("Unknown placement facts: " + ", ".join(sorted(unknown)))
        presented = facts.get("presented_segment", "")
        if type(presented) is not str:
            raise ValueError("Presented segment must be a string")
        with self.lock:
            self.transport_timing.update_placement_facts(facts)
            if (presented and facts.get("placement_revision") == self.lesson.revision
                    and self.transport.running and not self.transport.paused):
                self.transport.confirm_presentation(presented, now=self.now())

    def poll_state(self) -> dict:
        """The per-frame snapshot: the full state minus static values."""
        state = self.state()
        for key in state_contract.STATIC_KEYS:
            state.pop(key, None)
        return state

    def score_bundle(self, expected: dict | None = None) -> dict:
        status, response = self.score_read.prepare("score.bundle", expected or {})
        document = json.loads(response)
        if status:
            raise ValueError(document["error"])
        return document

    def lesson_overview(self) -> dict:
        with self.lock:
            return self.score.lesson_overview()
