"""Piano practice engine embedded directly into the Godot process.

Owns the MIDI, grading, lessons, notation and persistent library state.
Communication with Godot uses an in-memory native command queue.
"""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from .learning import LearningPlan
from .application.score_artifacts import ScoreArtifacts, ScoreSelection
from .application.midi_connection import MidiConnection, MidiNotice
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
from .application.attempt_progression import AttemptProgression, AttemptTick, repeat_deadline, plan_full_passage
from .application.feedback_route import FeedbackFacts, select_feedback_route
from .application.assessment_settlement import assess_completed_take
from .application.assessment_commit import commit_assessed_result
from .application.guided_session import GuidedSession, GuidedFragment, select_fragment
from .application.tempo_map_cache import TempoMapCache
from .application.session_snapshot_builder import (
    SnapshotValues, SnapshotReadPorts, capture as capture_session_snapshot,
)
from .completion_route import completion_route
from .visual_transport import VisualTransport, TransportField
from .midi_calibration import MidiTapCalibration
from .live_event_ring import LiveEventRing
from .runtime_timings import RuntimeTimings
from .live_input_view import LiveInputView
from .instruction import next_full_attempt
from .learner_state import guided_units
from .progress_repository import ProgressRepository
from .application.learner_progress import LearnerProgress
from .lesson_settings import SETTINGS

from .practice_history import PracticePolicyService
from .fukuda_mistake_store import FukudaMistakeStore
from .remediation import RemediationPlanner, RemedialAssignment, plan_timed_remedial_review


class PracticeEngine:
    # Existing public attributes delegate to one actual transport-state owner.
    run_at = TransportField("run_at")
    play_from_beat = TransportField("play_from_beat")
    pending_rewind = TransportField("pending_rewind")
    paused = TransportField("paused")
    paused_at = TransportField("paused_at")
    next_at = TransportField("next_at")
    visual_offset_beats = TransportField("visual_offset_beats")
    _preview_loop_pending = TransportField("_preview_loop_pending")
    _visual_rewind_from = TransportField("_visual_rewind_from")
    _visual_rewind_to = TransportField("_visual_rewind_to")
    _visual_rewind_at = TransportField("_visual_rewind_at")
    _visual_rewind_seconds = TransportField("_visual_rewind_seconds")
    _retry_previous_pass = TransportField("_retry_previous_pass")
    practice_preparation = TransportField("practice_preparation")
    _preparation_pending = TransportField("_preparation_pending")
    _preparation_at = TransportField("_preparation_at")
    visual_gap_beats = TransportField("visual_gap_beats")

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
        self._deferred_score_ack: int | None = None
        self.next_action = "Open a MIDI file."
        self.retry_range: dict | None = None
        # Persistent trouble means two boundary failures in consecutive takes
        # at the same stage and source two-bar chunk. Only a clean full take
        # or explicit stage navigation resets the history.
        self._trouble_key: tuple | None = None
        self._trouble_count = 0
        self._guided_recovery_pending = False
        self._guided_return: tuple[str, float] | None = None
        self.performance_summary: dict | None = None
        self.review_stage_identity: str | None = None
        self.review_end_beat: float | None = None
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
        self.feedback_marks: list[dict] = []
        self.feedback_unmapped = 0
        self.midi = MidiConnection(enabled=enable_midi)
        self.live_input = LiveInputView()
        self.assessment = AssessmentService()
        self.assessment_policies = PracticeAssessmentPolicies.defaults(self.assessment)
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        self.library_health = LibraryHealth(self.library)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir
        self.listen = ListenSession(data_dir / "demo-audio", lock=self.lock)
        self.fingering = FingeringService(data_dir / "fingering")
        self.preprocessing = PreprocessingCache(data_dir / "preprocessed")
        self.score_artifacts = ScoreArtifacts(self.preprocessing)
        self.progress = ProgressRepository(data_dir / "progress.db")
        # Keep the public db handle for LearnerStateStore and existing clients.
        self.db = self.progress.db
        self.fukuda_mistakes = FukudaMistakeStore(self.db)
        self.learner_store = self.progress.learner_store
        self.learner_progress = LearnerProgress(self.learner_store)
        self.practice_policy = PracticePolicyService(
            self.progress.assessment_history,
            diagnosis=self.library.settings["diagnosis_strategy"],
            learner=self.library.settings["learner_strategy"])
        self.remediation_planner = RemediationPlanner()
        self._remediation_pending: RemedialAssignment | None = None
        self._remediation_active: RemedialAssignment | None = None

    def _midi_lost(self, reason: str = "device_disconnected") -> None:
        """Cancel session state after detachment and before closing the input."""
        with self.midi.disconnected(reason) as notice:
            self.live_input.clear_device()
            self._stop()
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
                    self.live_input.clear_device()
                    self._stop()
            except RuntimeError as exc:
                self.feedback = str(exc)
                raise
            self._present_midi_notice(selected.notice)
            self.library.update(midi_device=name)

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
                self.feedback = "Tap any key in time with eight clicks"
            elif action == "calibration_cancel":
                self.midi_calibration.cancel()
            elif action == "calibration_apply":
                result = self.midi_calibration.snapshot(time.monotonic())["result"]
                if not result or not result.get("reliable"):
                    raise ValueError("Finish a consistent calibration before applying it")
                self.library.update(midi_offset_ms=max(0, min(250, result["estimate_ms"])))
            elif action == "calibration_reset":
                self.midi_calibration.cancel()
                self.midi_calibration.result = None
                self.library.update(midi_offset_ms=0)
            else:
                raise ValueError("Unsupported calibration command")

    def preferences(self) -> dict:
        with self.lock:
            return self.library.public_settings()

    def set_preferences(self, **changes) -> dict:
        with self.lock:
            before = self.library.settings['music_dir']
            old_strategy = tuple(self.library.settings[key] for key in
                                 ("exercise_strategy", "timing_strategy", "tempo_strategy"))
            updated = self.library.update(**changes)
            if {"diagnosis_strategy", "learner_strategy"} & changes.keys():
                self.practice_policy = PracticePolicyService(
                    self.progress.assessment_history,
                    diagnosis=self.library.settings["diagnosis_strategy"],
                    learner=self.library.settings["learner_strategy"])
            if before != self.library.settings['music_dir']:
                self.library_health.reset()
            if (old_strategy != tuple(self.library.settings[key] for key in
                        ("exercise_strategy", "timing_strategy", "tempo_strategy"))
                    and self.plan is not None):
                old = self.plan
                self._stop()
                self._save()
                self._reset_trouble()
                self.plan = restored_strategy_plan(
                    old, settings=self.library.settings,
                    progress=self.progress, fingerprint=self.fingerprint,
                    warmup=self.is_builtin_warmup,
                    fukuda_mistakes=self.fukuda_mistakes.problematic(self.fingerprint),
                    feedback=self.fukuda_mistakes.evidence(self.fingerprint))
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
            origin = tempo.seconds_at(self.play_from_beat)
            return tempo.beat_at(origin+elapsed_seconds)-self.play_from_beat
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

    def _receive_message(self, message):
        # Timestamp in the hardware input callback, not on the rendering thread.
        now = time.monotonic()
        with self.lock:
            self.midi.observe(message, now=now)
            if self.midi_calibration.active:
                if message.type == "note_on" and message.velocity > 0:
                    self.midi_calibration.observe(now)
                return
            corrected_at = now - self.library.settings["midi_offset_ms"] / 1000.0
            # A key can reach the next attempt's musical deadline before the
            # next frame-state snapshot, even if none observed the source ending.
            # Settle only a due handoff; retain the hardware timestamp above.
            if (message.type in ("note_on", "note_off") and self.plan is not None
                    and self.mode in ("practice", "perform")
                    and not self.paused and self.awaiting_score_revision is None):
                due = (not self.running and self.next_at and now >= self.next_at
                       and (self._preview_loop_pending
                            or (self.pending_result is not None and self.auto)
                            or self.pending_rewind is not None))
                if (self.running and self.mode == "practice"
                        and self.plan.exercise.kind != "perform"
                        and self.review_end_beat is None and (self.auto or self.preview_only)):
                    phrase = self.plan.active_phrase
                    source_end = self.run_at + (self._elapsed_seconds(phrase.end-phrase.start)
                        - self._elapsed_seconds(self.play_from_beat))
                    due = now >= source_end + self.visual_gap_beats*60/self.plan.bpm
                if due:
                    self._update()
            if message.type in ("note_on", "note_off"):
                is_on = message.type == "note_on" and message.velocity > 0
                self.live_input.receive(
                    pitch=message.note, is_on=is_on, now=corrected_at,
                    phrase=self.plan.active_phrase if self.plan is not None else None,
                    hand=self.plan.hand if self.plan is not None else "both",
                    bpm=self.plan.bpm if self.plan is not None else 60.0,
                    from_beat=self.play_from_beat, run_at=self.run_at,
                    running=self.running, paused=self.paused,
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
                    self._save_guided_preparation()
                return
            if self.mode == "listen":
                return
            if self.running and not self.paused and now >= self.run_at and self.recorder:
                if message.type == "note_on":
                    self.recorder.add(message.note, message.velocity > 0, corrected_at - self.run_at)
                elif message.type == "note_off":
                    self.recorder.add(message.note, False, corrected_at - self.run_at)

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
                self._stop()
                self._reset_trouble()
                self.course_guided = False
                self.source = str(source)
                self.is_builtin_warmup = warmup
                self.open_from_beat = 0.0
                self.fingerprint = fingerprint
                self._piece_generation += 1
                self.score_artifacts.invalidate()
                self.plan = LearningPlan(piece, warmup=warmup,
                    exercise_strategy=self.library.settings['exercise_strategy'],
                    timing_strategy=self.library.settings['timing_strategy'],
                    tempo_strategy=self.library.settings['tempo_strategy'],
                    fukuda_mistakes=self.fukuda_mistakes.problematic(fingerprint),
                    feedback=self.fukuda_mistakes.evidence(fingerprint))
                if diagnostics:
                    now = time.perf_counter()
                    print("SCORE_LOAD_STAGE: curriculum", round((now-checkpoint)*1000, 1),
                          "ms", self.plan.lesson_generator.name, flush=True)
                    checkpoint = now
                self.mode = "practice"
                self.teaching = None
                self.guided_range = None
                self.score = score
                self._restore()
                self.feedback = "Press Start to practice"
                self.next_action = "Press Start to practice."
                self.score_revision += 1
                self.pending_result = None
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
        # The database deletes are atomic, scoped exclusively to this score.
        self.progress.reset_piece(fingerprint)
        self.fukuda_mistakes.reset(fingerprint)
        self._stop()
        self._reset_trouble()
        self.plan = LearningPlan(piece, warmup=warmup,
                    exercise_strategy=self.library.settings['exercise_strategy'],
                    timing_strategy=self.library.settings['timing_strategy'],
                    tempo_strategy=self.library.settings['tempo_strategy'],
                    fukuda_mistakes=self.fukuda_mistakes.problematic(fingerprint),
                    feedback=self.fukuda_mistakes.evidence(fingerprint))
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
        self._save()

    def _stop(self):
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
        self.feedback_marks=[]
        self.feedback_unmapped=0
        self.recovery_notice = None
        self.live_input.reset_attempt()
        self.retry_range=None
        self._guided_recovery_pending=False
        self._guided_return=None
        self.listen.cancel()
        self.performance_summary=None
        self.review_stage_identity=None
        self.review_end_beat=None
        self.review_session_complete=False
        self._guided_prepared=False
        self._remediation_pending = None
        self._remediation_active = None

    def _learner_saved(self, stage_key: str | None = None) -> dict:
        return self.learner_progress.saved(
            self.plan, fingerprint=self.fingerprint, stage_key=stage_key)

    def _guided_unit(self) -> dict | None:
        return self.learner_progress.guided_unit(
            self.plan, mode=self.mode, guided_range=self.guided_range)

    def _save_guided_preparation(self):
        """Record a completed guided idea once, without awarding timed mastery."""
        self.guided_session.commit_completed_preparation(
            learning=self.mode == "learn",
            remediation_active=self._remediation_active is not None,
            fingerprint=self.fingerprint,
            stage_key=self.plan.identity if self.plan is not None else "",
            current_unit=self._guided_unit,
            record_preparation=self.learner_progress.record_guided_preparation)


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
        self._stop()
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
        self._stop()
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
        self._stop()
        # An idle score selected with Open at measure N must already point
        # at that source measure. Start later uses the same origin.
        phrase = self.plan.active_phrase
        self.play_from_beat = max(0.0, min(
            self.open_from_beat, phrase.end - phrase.start - 1e-6))
        if return_context is not None and return_context[0] == self.plan.identity:
            self.pending_rewind = return_context[1]
            self.retry_range = retry_range
            self._guided_return = return_context
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
        self.play_from_beat = 0.0
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
        if (self.mode != "listen" or self.paused or self.running
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
        self.run_at = time.monotonic()+start.delay_seconds
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
        return self.assessment.review(
            phrase, result, bar_boundaries=self.plan.piece.bar_boundaries,
            played_from_beat=self.play_from_beat, bpm=self.plan.bpm)

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
        if not self.paused:
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
            self.pending_rewind = start
            self.retry_range = {"first_bar": bar, "last_bar": phrase.last_bar,
                                "start_beat": start, "end_beat": grid[-1]}
            self.next_action = f"Get ready to play from bar {bar} at {self.plan.bpm} BPM."

    def _commit_pending(self) -> str:
        """Apply a completed attempt after feedback has been shown on its own score."""
        if self.pending_result is None or self.plan is None:
            return ""
        p = self.plan
        result = self.pending_result
        # Source-specific mistakes are learned from authentic original
        # MIDI attempts, never from generated exercises or Listen previews.
        use_feedback = (p.accepts_performance_feedback
                      and p.active_variant.level=="original"
                      and not self.is_builtin_warmup
                      and bool(result.notes))
        self.pending_result = None
        if getattr(result, "passed", result.clean):
            self._reset_trouble()
            self.learner_progress.resolve_trouble(
                fingerprint=self.fingerprint, stage_key=p.identity)
        self.retry_range = None
        outcome = commit_assessed_result(
            plan=p, result=result, fingerprint=self.fingerprint,
            automatic=self.auto, mode=self.mode, warmup=self.is_builtin_warmup,
            observe=self.practice_policy.observe,
            plan_remediation=self.remediation_planner.plan)
        if use_feedback:
            # Reuse graded original source IDs through the selected generator's
            # feedback contract. No name-based algorithm dispatch in the engine.
            self.fukuda_mistakes.observe(self.fingerprint, result)
            evidence = self.fukuda_mistakes.evidence(self.fingerprint)
            failed_ids = frozenset(n.note.source_id for n in result.notes
                                   if n.status != "correct")
            accepted = getattr(result, "passed", result.clean)
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
            # Engraving depends on notation, not changes of tempo alone.
            self.score_revision += 1
            self.visual_offset_beats = 0.0
        self._save()
        return outcome.message

    def start(self, *, from_beat: float | None = None, mode: str = "practice",
              loop_continuation: bool = False):
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            if self.mode == "learn":
                self._prepare_practice()
                return
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
            self.feedback_marks = []
            self.feedback_unmapped = 0
            self.recorder = Recorder()
            self.visual_gap_beats = self._source_model()[
                "practice_timeline"]["gap"]["duration_beats"]
            position = self.open_from_beat if from_beat is None else from_beat
            scheduled = self.attempt_progression.schedule_start(
                phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
                time_signatures=self.plan.piece.time_signatures,
                bpm=self.plan.bpm, position=position,
                loop_continuation=loop_continuation,
                preview=self.preview_only, now=time.monotonic())
            self.play_from_beat = scheduled.from_beat
            self.count_in_bar_beats = scheduled.count_in_bar_beats
            self.count_in_meter = list(scheduled.count_in_meter)
            self.count_in_beats = scheduled.count_in_beats
            self.next_boundary_beat = scheduled.next_boundary_beat
            self.run_at = scheduled.run_at
            self.feedback = "Count in, then play"
            self.next_action = scheduled.next_action

    def _continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Retain polling overshoot instead of moving the musical deadline."""
        self.start(from_beat=from_beat, mode=self.mode, loop_continuation=True)
        self.run_at = deadline

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

    def _visual_motion(self, now: float) -> tuple[float, float, float]:
        """Read the one transport projection, including authored tempo and silence."""
        phrase = self.plan.active_phrase
        return self.visual_transport.position(
            now, phrase_length=phrase.end-phrase.start, bpm=self.plan.bpm,
            running=self.running,
            pending_auto_result=(self.pending_result is not None and self.auto),
            tempo_map=self._active_tempo_map())

    def control(self, action: str, **kwargs) -> None:
        """Single locked command entry; dispatch owns no engine state."""
        with self.lock:
            self._apply_listen_failure()
            route = ControlDispatcher.route(action)
            if route == "calibration":
                return self.midi_calibration_action(action)
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
                paused=self.paused, mode=self.mode,
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
                    from_beat=(self.pending_rewind if self.pending_rewind is not None
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

    def _control_transport(self, action: str, kwargs: dict) -> None:
        if action == "practice":
            self._prepare_practice()
            if kwargs.get("wait_for_player", False):
                # Listen returns to a ready score without an auto count-in.
                self.awaiting_score_revision = None
                self.feedback = "Ready to play"
                self.next_action = "Play one piano key to begin, or press Play."
        elif action == "stop":
            self._stop()
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
            visual_now = self.paused_at if self.paused else sampled
            position, _, _ = self._visual_motion(visual_now)
            target = (self.pending_rewind if self.pending_rewind is not None
                      else self.play_from_beat)
            self.paused = False
            self.paused_at = 0.0
            self.pause_context = None
            self._deferred_score_ack = None
            self.awaiting_score_revision = None
            self.pending_result = None
            self._retry_previous_pass = False
            self._guided_recovery_pending = False
            self._schedule_preparation(target, now=sampled, from_visual=position,
                                       reverse_seconds=self.feedback_seconds)
            self.feedback = "Get ready to retry"
            return
        self.start(mode="perform" if self.mode == "perform" else "practice")
        return

    def _pause_current_session(self):
        """Pause learning, playback or preparation using one sampled clock."""
        now = time.monotonic()
        context = self._phase(now) if not self.paused else ""
        require_pausable(paused=self.paused, phase=context)
        self.pause_context = context
        self.visual_transport.pause(at=now)
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.pause(now=now)
        return

    def _resume_current_session(self):
        """Resume teaching and transport from the same monotonic instant."""
        learning = self.mode == "learn" and self.teaching is not None
        shift_run_at = resume_timeline(
            paused=self.paused, learning=learning, running=self.running,
            preview_pending=self._preview_loop_pending,
            automatic_feedback=self.pending_result is not None and self.auto)
        now = time.monotonic()
        if learning:
            self.teaching.resume(now=now)
        self.visual_transport.resume(now=now, shift_run_at=shift_run_at)
        self.pause_context = None
        if self.running:
            self.feedback = "Count in" if now < self.run_at else "Playing"
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
        change = prepare_stage_change(p, action, kwargs)
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

    def _advance_pending_feedback(self, now: float):
        """Commit finished feedback and schedule exactly one next transition."""
        if self.auto and self.next_at and now >= self.next_at:
            deadline = self.next_at
            previous_revision = self.score_revision
            previous_identity = self.plan.identity
            message = self._commit_pending()
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
            if route == "remediation":
                self._start_remedial_assignment(assignment)
                return
            if route == "guided_stage":
                self._begin_course_stage()
                return
            if route == "await_score":
                # Wait until Godot has acknowledged the next score revision;
                # never consume a count-in against stale notation ink.
                self.awaiting_score_revision = self.score_revision
                self.auto = False
                self.feedback = "Preparing next passage"
                self.next_at = 0
            elif route == "continue":
                # Failed attempts reuse the existing source; clean attempts
                # append another passage with the exact authored rest gap.
                if not self._retry_previous_pass:
                    self.visual_offset_beats += self._source_model()[
                        "practice_timeline"]["stride_beats"]
                target = (self.practice_preparation["source_from_beat"]
                          if self._retry_previous_pass and self.practice_preparation else 0.0)
                self._continue_at(deadline, from_beat=target)
            else:
                self.next_at = 0
                self.auto = False
                self.feedback = message or self.feedback
        return

    def _start_remedial_assignment(self, assignment: RemedialAssignment) -> None:
        """Enter a source-bound remedial take, with no mastery from partial work."""
        if self.plan is None or assignment.stage_key != self.plan.identity:
            return
        # A malformed interval must not cancel the current session.
        review = (None if assignment.guided else plan_timed_remedial_review(
            assignment, self.plan.active_phrase, self.plan.piece.bar_boundaries))
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
        self.feedback_marks=self._live_feedback((now-self.run_at))
        if self.fingerprint:
            unit = next((unit for unit in guided_units(self.plan.active_variant, self.plan.piece.bar_boundaries)
                         if unit["start_beat"] == decision.restart_beat and unit["end_beat"] == decision.end_beat), None)
            if unit is not None:
                tempo_map = self._active_tempo_map()
                assessed = self.assessment_policies.select(tempo_map).grade(
                    phrase, hand=self.plan.hand, bpm=self.plan.bpm,
                    played=self.recorder.presses if self.recorder else [],
                    from_beat=self.play_from_beat, end_beat=decision.end_beat,
                    tempo=tempo_map)
                self.learner_progress.record_rolling_trouble(
                    fingerprint=self.fingerprint, stage_key=self.plan.identity,
                    unit=unit, assessed_notes=assessed.notes,
                    phrase_start=phrase.start)
        transition = plan_rolling_recovery(
            decision, identity=self.plan.identity, bpm=self.plan.bpm,
            previous_key=self._trouble_key, previous_count=self._trouble_count,
            grid=grid, first_bar=phrase.first_bar, now=now,
            allow_guided=self.plan.exercise_strategy.name != "coda-part")
        self.plan.streak=0
        self.plan.failures+=1
        self.plan.bpm=transition.bpm
        self._save()
        self._schedule_preparation(decision.restart_beat, now=now,
            from_visual=self.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds)
        self._trouble_key = transition.trouble_key
        self._trouble_count = transition.trouble_count
        self._guided_recovery_pending = transition.guided
        self.recovery_notice = transition.display.notice
        self.retry_range = transition.display.retry_range
        self.feedback = transition.display.feedback
        self.next_action = transition.display.next_action
        return

    def _complete_attempt(self, phrase: Phrase, ending: float,
                          total_beats: float, duration: float, now: float) -> None:
        """Apply post-performance state after the score's settlement interval.

        This method is called from the locked _update loop. Assessment and
        grading are calculated only after a completed non-preview take.
        """
        if self.preview_only:
            # A preview loops visually just like graded practice, but never
            # invents notes, clean runs, mastery or a MIDI recording.
            self.running = False
            self._preview_loop_pending = True
            self.next_at = repeat_deadline(
                run_at=self.run_at, duration=duration,
                gap_beats=self.visual_gap_beats, bpm=self.plan.bpm)
            self.feedback = "Timing preview - repeating after one empty measure"
            self.next_action = "Connect your MIDI piano to earn clean runs."
            if now >= self.next_at:
                self._update()
            return
        tempo_map = self._active_tempo_map()
        # Grading/projection uses explicit assessment inputs. The engine
        # still owns take settlement and every subsequent state mutation.
        assessed = assess_completed_take(
            phrase=phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.play_from_beat, end_beat=ending,
            tempo=tempo_map, policies=self.assessment_policies,
            layout_for_feedback=lambda: self.engraving().layout)
        result = assessed.result
        self.feedback_marks = assessed.marks
        self.feedback_unmapped = assessed.unmapped
        self.feedback = assessed.feedback
        self.running=False
        self.recorder=None
        self.performance_summary = (self._performance_review(phrase, result)
                                    if tempo_map is None else None)
        self.review_stage_identity = self.plan.identity
        route = completion_route(self.mode, self.review_end_beat, self.play_from_beat)
        if route == "perform":
            self._finish_performance_review(phrase, result)
        elif route == "section_review":
            self._finish_section_review(result)
        elif route == "partial_recovery":
            self._finish_partial_recovery(result, now)
        else:
            self._finish_full_passage(result, total_beats, duration, now)

    def _finish_performance_review(self, phrase: Phrase, result):
        """Complete finish performance review after a scored take."""
        if self.fingerprint:
            if result.clean:
                self.learner_progress.resolve_trouble(
                    fingerprint=self.fingerprint, stage_key=self.plan.identity)
            else:
                for unit in self.performance_summary["weakest_bars"]:
                    self._record_saved_trouble(phrase, result, start=unit["start_beat"],
                                              end=unit["end_beat"], errors=unit["errors"])
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
        self.pending_rewind = None
        self.retry_range = None
        self.open_from_beat = 0.0
        self.feedback = "Section review finished · " + result.summary
        self.next_action = "Review the notes or press Start for the whole passage."

    def _finish_partial_recovery(self, result, now: float):
        """Complete finish partial recovery after a scored take."""
        # A clean *partial* recovery cannot confer full passage mastery.
        self._schedule_preparation(0.0, now=now,
            from_visual=self.visual_offset_beats + self.play_from_beat
                + self._elapsed_beat(now-self.run_at),
            reverse_seconds=self.feedback_seconds)
        self.feedback = "Selected section finished · " + result.summary
        self.next_action = "Next: play the whole passage from its beginning to earn mastery."
        self.retry_range = None

    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        """Settle a full take using independent transport decisions."""
        decision = plan_full_passage(
            accepted=getattr(result, "passed", result.clean),
            automatic=self.auto, warmup=self.is_builtin_warmup,
            retry_pending=self._retry_previous_pass,
            run_at=self.run_at, duration=duration, total_beats=total_beats,
            gap_beats=self.visual_gap_beats, bpm=self.plan.bpm,
            feedback_seconds=self.feedback_seconds)
        self.pending_result = result
        if decision.rewind:
            self._retry_previous_pass = True
            self._schedule_preparation(
                self.play_from_beat, now=now,
                from_visual=self._visual_motion(now)[0],
                reverse_seconds=decision.rewind_seconds)
        if decision.failed:
            self.plan.streak = 0
            self._save()
        if decision.stop_auto:
            self.auto = False
            self.visual_transport.cancel_preparation()
        self.next_action = next_full_attempt(self.plan, result)
        if decision.deadline_action == "clear":
            self.next_at = 0
        elif decision.deadline_action == "schedule":
            self.next_at = decision.deadline_at
            if now >= self.next_at:
                self._update()

    def _assess_rolling_boundary(self, boundary: float,
                                 grid: tuple[float, ...]):
        """Grade one authored boundary under the existing session lock."""
        tempo_map = self._active_tempo_map()
        return self.assessment_policies.select(tempo_map).recover(
            self.plan.active_phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.play_from_beat, end_beat=boundary, grid=grid,
            threshold=(SETTINGS.warmup_recovery_errors
                       if self.is_builtin_warmup
                       else SETTINGS.recovery_errors_in_window),
            warmup=self.is_builtin_warmup, tempo=tempo_map)

    def _run_pre_assessment_transition(self, now: float) -> bool:
        """Apply an explicit non-grading transition under the session lock."""
        context = TransitionContext(
            has_plan=self.plan is not None,
            learning=self.mode == "learn" and self.teaching is not None,
            paused=self.paused, listening=self.mode == "listen",
            preview_pending=self._preview_loop_pending,
            preparation_pending=self._preparation_pending,
            feedback_pending=self.pending_result is not None,
            awaiting_score=self.awaiting_score_revision is not None,
            rewind_pending=self.pending_rewind is not None,
            running=self.running, run_at=self.run_at)
        decision = decide_transition(
            context, now=now, next_at=self.next_at,
            preparation_at=self._preparation_at)
        if decision.preparation_phase is not None:
            self.practice_preparation["phase"] = decision.preparation_phase
        if decision.action == "learning":
            self.guided_session.advance(connected=self.midi.connected, now=now)
            self._save_guided_preparation()
        elif decision.action == "listening":
            if self.running and self.listen.finished(now=now, run_at=self.run_at):
                self.running = False
                self.feedback = "Example complete"
                self.next_action = (
                    "Choose Learn to find the notes, or Practice to play the rhythm.")
        elif decision.action == "preview_due":
            deadline = self.next_at
            self.visual_offset_beats += self._source_model()[
                "practice_timeline"]["stride_beats"]
            self._continue_at(deadline)
        elif decision.action == "feedback":
            self._advance_pending_feedback(now)
        elif decision.action == "rewind_due":
            if self._guided_recovery_pending:
                self._begin_learn(from_beat=self.pending_rewind, recovery=True)
            else:
                self._continue_at(self.next_at, from_beat=self.pending_rewind)
        return decision.consumed

    def _update(self) -> None:
        """Advance the backend clock under its existing session lock."""
        self._poll_midi_connection()
        self._apply_listen_failure()
        now = time.monotonic()
        if self._run_pre_assessment_transition(now):
            return
        phrase = self.plan.active_phrase
        score_beat = self.play_from_beat + max(
            0.0, self._elapsed_beat(now-self.run_at))

        step = self.attempt_progression.inspect(AttemptTick(
            phrase=phrase, boundaries=self.plan.piece.bar_boundaries,
            now=now, score_beat=score_beat, from_beat=self.play_from_beat,
            run_at=self.run_at, next_boundary=self.next_boundary_beat,
            review_end=self.review_end_beat, preview=self.preview_only,
            auto=self.auto, mode=self.mode,
            coda=self.plan.exercise_strategy.name == "coda-part",
            bpm=self.plan.bpm, gap_beats=self.visual_gap_beats),
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
        if not self.paused and self.mode == "learn" and self.teaching is not None:
            teaching_phase = ("loading" if self.awaiting_score_revision is not None
                              else self.teaching.snapshot(now=now)["phase"])
        return project_phase(PhaseSnapshot(
            paused=self.paused, running=self.running, run_at=self.run_at,
            teaching_phase=teaching_phase,
            performance_complete=self.performance_summary is not None,
            preview_loop_pending=self._preview_loop_pending,
            review_complete=self.review_session_complete,
            pending_result=self.pending_result is not None,
            awaiting_score=self.awaiting_score_revision is not None,
            pending_rewind=self.pending_rewind is not None,
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
                from_beat=self.play_from_beat, elapsed_seconds=elapsed_seconds,
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
                if self.plan is None or self.paused:
                    return 250
                if (self.running or self._preview_loop_pending or self._preparation_pending
                        or self.pending_result is not None or self.pending_rewind is not None
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
            if self.plan is not None:
                beat = self.plan.active_phrase.start + self.play_from_beat
                if self.running and time.monotonic() >= self.run_at:
                    beat += self._elapsed_beat(time.monotonic() - self.run_at)
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
            state["midi_calibration"] = self.midi_calibration.snapshot(
                calibration_sample_at)
            return state

    def _set_snapshot_visual_gap(self, beats: float) -> None:
        # Engraved preparation is authoritative for loop silence.
        self.visual_gap_beats = beats

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
            next_at=self.next_at,
            open_from_beat=self.open_from_beat,
            pause_context=self.pause_context,
            paused=self.paused,
            paused_at=self.paused_at,
            pending_result=self.pending_result,
            pending_rewind=self.pending_rewind,
            performance_summary=self.performance_summary,
            persistent_hints=self.persistent_hints,
            plan=self.plan,
            play_from_beat=self.play_from_beat,
            practice_preparation=self.practice_preparation,
            preview_only=self.preview_only,
            recovery_notice=self.recovery_notice,
            retry_range=self.retry_range,
            review_end_beat=self.review_end_beat,
            run_at=self.run_at,
            running=self.running,
            score_revision=self.score_revision,
            transport_id=self.transport_id,
            visual_offset_beats=self.visual_offset_beats,
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


