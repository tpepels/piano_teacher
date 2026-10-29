"""Loopback-only practice service for the native Godot UI.

Start: python -m piano_teacher.server. No Internet, account, or Qt required.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .learning import LearningPlan
from .application.score_artifacts import ScoreArtifacts, ScoreSelection, validate_png_width
from .application.midi_connection import MidiConnection, MidiNotice
from .application.listen_session import ListenSelection, ListenSession
from .practice import Recorder, evaluate
from .importing.pieces import import_piece
from .rendering.legacy.engraving import EngravedScore
from .feedback import project_assessment
from .fingering import FingeringService
from .library import ScoreLibrary
from .preprocessing_cache import PreprocessingCache
from .library_health import LibraryHealth
from .warmups import is_warmup
from .recovery import check_rolling_two_bar_window, check_two_bar_window
from .recovery_projection import recovery_display
from .music import Phrase, source_note_id
from .notation.practice_timeline import preparation_measure_descriptor
from .lesson_timing import lead_in_beats, preparation_meter
from .measure_grid import phrase_grid, next_chunk_end, chunk_start_at_end, bar_number_at
from .course_navigation import locate_course_section
from .state_projection import (
    ActivitySnapshot, GuidedSnapshot, PhaseSnapshot,
    SessionSnapshot, TimingSnapshot, project_phase,
    project_session_state,
)
from .assessment_service import AssessmentService
from .application.lesson_snapshot import build_lesson_snapshot
from .completion_route import completion_route
from .visual_transport import VisualTransport, TransportField
from .live_input_view import LiveInputView
from .instruction import next_full_attempt
from .learner_state import guided_units, next_guided_unit, placement_candidate
from .progress_repository import ProgressRepository
from .lesson_settings import SETTINGS


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

    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True):
        self.lock = threading.RLock()
        # Whole-source inference must never block MIDI or state polling.
        # Serialize source loads and durable corrections separately instead.
        self._fingering_lock = threading.Lock()
        self._piece_generation = 0
        self.plan: LearningPlan | None = None
        self.score = None
        self.source = None
        self.is_builtin_warmup = False
        self.fingerprint = ""
        self.recorder: Recorder | None = None
        self.visual_transport = VisualTransport(
            _visual_rewind_seconds=SETTINGS.feedback_seconds)
        self.open_from_beat = 0.0  # Explicit opening measure; never an inferred clock
        self.next_boundary_beat = 0.0
        self.feedback_seconds = SETTINGS.feedback_seconds
        self.recovery_notice: dict | None = None
        self.pause_context: str | None = None
        self._deferred_score_ack: int | None = None
        self.next_action = "Open a MIDI or MusicXML file."
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
        self.feedback = "Open a MIDI or MusicXML file"
        self.score_revision = 0
        self.awaiting_score_revision: int | None = None
        self.pending_result = None
        self.feedback_marks: list[dict] = []
        self.feedback_unmapped = 0
        self.midi = MidiConnection(enabled=enable_midi)
        self.live_input = LiveInputView()
        self.assessment = AssessmentService()
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
        self.learner_store = self.progress.learner_store

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

    def preferences(self) -> dict:
        with self.lock:
            return self.library.public_settings()

    def set_preferences(self, **changes) -> dict:
        with self.lock:
            before = self.library.settings['music_dir']
            updated = self.library.update(**changes)
            if before != self.library.settings['music_dir']:
                self.library_health.reset()
            return updated

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

    def _receive(self, message):
        # Timestamp in the hardware input callback, not on the rendering thread.
        now = time.monotonic()
        with self.lock:
            self.midi.observe(message, now=now)
            # A key can reach the next attempt's musical deadline before the
            # next HTTP state poll, even if no poll observed the source ending.
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
                    source_end = self.run_at + (phrase.end-phrase.start-self.play_from_beat)*60/self.plan.bpm
                    due = now >= source_end + self.visual_gap_beats*60/self.plan.bpm
                if due:
                    self._update()
            if message.type in ("note_on", "note_off"):
                is_on = message.type == "note_on" and message.velocity > 0
                self.live_input.receive(
                    pitch=message.note, is_on=is_on, now=now,
                    phrase=self.plan.active_phrase if self.plan is not None else None,
                    hand=self.plan.hand if self.plan is not None else "both",
                    bpm=self.plan.bpm if self.plan is not None else 60.0,
                    from_beat=self.play_from_beat, run_at=self.run_at,
                    running=self.running, paused=self.paused,
                    preview=self.preview_only, mode=self.mode,
                    transport_id=self.transport_id,
                )
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
                    self.recorder.add(message.note, message.velocity > 0, now - self.run_at)
                elif message.type == "note_off":
                    self.recorder.add(message.note, False, now - self.run_at)

    def load(self, path: str, *, warmup: bool = False):
        with self._fingering_lock:
            source = Path(path).expanduser().resolve()
            fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
            piece, score = self.preprocessing.load_import(
                source, fingerprint, importer=import_piece)
            piece = replace(piece, fingering_plan=self.fingering.prepare(piece, fingerprint))
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
                self.plan = LearningPlan(piece, warmup=warmup)
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
        self._stop()
        self._reset_trouble()
        self.plan = LearningPlan(piece, warmup=warmup)
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
        if self.teaching is not None:
            self.teaching.stop()
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

    def _learner_saved(self, stage_key: str | None = None) -> dict:
        if self.fingerprint and self.plan is not None:
            return self.learner_store.read(self.fingerprint, stage_key or self.plan.identity)
        # Older in-process clients can bind an unsaved plan directly.
        return {"resume_unit": None, "completed_units": [], "trouble_units": [],
                "skip_status": "active", "skip_reason": ""}

    def _guided_unit(self) -> dict | None:
        if self.plan is None or self.mode != "learn" or self.guided_range is None:
            return None
        return next((unit for unit in guided_units(self.plan.active_variant, self.plan.piece.bar_boundaries)
                     if (unit["start_beat"], unit["end_beat"]) == self.guided_range), None)

    def _save_guided_preparation(self):
        if self._guided_prepared or self.teaching is None or self.mode != "learn":
            return
        snapshot = self.teaching.snapshot(now=time.monotonic())
        if not snapshot["completed"]:
            return
        unit = self._guided_unit()
        if unit is not None and self.fingerprint:
            self.learner_store.complete_unit(self.fingerprint, self.plan.identity, unit,
                                            assisted=snapshot["assisted_count"] > 0)
        self._guided_prepared = True

    def _learner_snapshot(self) -> dict:
        p = self.plan
        units = guided_units(p.active_variant, p.piece.bar_boundaries)
        saved = self._learner_saved()
        saved["trouble_units"] = [{key: value for key, value in spot.items() if key != "stage_key"}
                                 for spot in self._valid_trouble_spots(stage_key=p.identity)]
        current = self._guided_unit()
        completed = saved["completed_units"]
        prepared = sum(any(all(unit[field] == previous.get(field)
                               for field in ("start_beat", "end_beat", "source_indices"))
                           for previous in completed) for unit in units)
        next_state = saved if current is None else {**saved, "resume_unit": None,
                                                    "completed_units": completed+[current]}
        following = next_guided_unit(p.active_variant, p.piece.bar_boundaries, next_state)
        return {**saved, "course_guided": self.course_guided, "prepared_units": prepared,
                "total_units": len(units), "current_unit": current, "next_unit": following,
                "unit_number": next((i+1 for i, unit in enumerate(units) if unit == current), 0)}

    def _begin_course_stage(self, *, bump_revision: bool = True, explicit_learn: bool = False):
        if self.plan.exercise.kind == "perform" and not explicit_learn:
            self._prepare_perform()
            return
        unit = next_guided_unit(self.plan.active_variant, self.plan.piece.bar_boundaries, self._learner_saved())
        if unit is None and explicit_learn:
            unit = next(iter(guided_units(self.plan.active_variant, self.plan.piece.bar_boundaries)), None)
        if unit is None:
            self._prepare_practice()
        else:
            self._begin_learn(from_beat=unit["start_beat"], bump_revision=bump_revision)

    def _select_step(self, step):
        self.plan.select_step(self.plan.lesson_steps.index(step) + 1)
        self._reset_trouble()

    def _skip_stage(self, reason):
        p = self.plan
        if (p is None or not isinstance(reason, str) or not reason.strip()
                or p.lesson_step_number >= len(p.lesson_steps)):
            raise ValueError("Choose an available next step and explain the skip")
        following = p.lesson_steps[p.lesson_step_number]
        if self.fingerprint:
            self.learner_store.mark_skipped(self.fingerprint, p.identity, reason=reason)
        self._stop()
        self._select_step(following)
        self.course_guided = True
        self._begin_course_stage()
        self._save()

    def _place_original(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        p = self.plan
        candidate = placement_candidate(p)
        if candidate is None:
            raise ValueError("You are already playing the original notes")
        if self.fingerprint:
            for step in p.lesson_steps[p.lesson_step_number-1:]:
                if step.key == candidate.key:
                    break
                self.learner_store.mark_skipped(self.fingerprint, step.key,
                    reason="Student chose to try the original notes", status="placed")
        self._stop()
        self._select_step(candidate)
        self.course_guided = True
        self._begin_course_stage()
        self._save()

    def _valid_trouble_spots(self, *, stage_key: str | None = None) -> list[dict]:
        if self.plan is None or not self.fingerprint:
            return []
        p = self.plan
        steps = {step.key: step for step in p.lesson_steps}
        canonical = {}
        valid = []
        for stored in self.learner_store.trouble_for_piece(self.fingerprint):
            key = stored["stage_key"]
            step = steps.get(key)
            if step is None or (stage_key is not None and stage_key != key):
                continue
            if key not in canonical:
                variant = next((variant for variant in p._stage_variants(p.exercises[step.exercise_index], step.hand)
                                if variant.level == step.level), None)
                canonical[key] = guided_units(variant, p.piece.bar_boundaries) if variant else ()
            unit = next((unit for unit in canonical[key]
                         if all(unit[field] == stored.get(field)
                                for field in ("start_beat", "end_beat", "source_indices"))), None)
            if unit is not None:
                valid.append({**stored, **unit})
        return valid

    def _revisit_trouble(self, stage_key, start_beat):
        # Saved evidence can outlive a course revision. Validate the exact
        # current source binding before stopping or selecting another stage.
        if (self.plan is None or not self.fingerprint or not isinstance(stage_key, str)
                or isinstance(start_beat, bool) or not isinstance(start_beat, (int, float))
                or not math.isfinite(start_beat)):
            raise ValueError("Choose a saved trouble spot for this piece")
        p = self.plan
        step = next((step for step in p.lesson_steps if step.key == stage_key), None)
        stored = next((unit for unit in self._valid_trouble_spots(stage_key=stage_key)
                       if unit["stage_key"] == stage_key and unit["start_beat"] == start_beat), None)
        if step is None or stored is None:
            raise ValueError("This trouble spot is no longer available")
        unit = stored
        bpm = p.bpm
        self._stop()
        self._select_step(step)
        p.bpm = bpm
        self.learner_store.reactivate(self.fingerprint, stage_key)
        self.course_guided = True
        self.retry_range = {field: unit[field] for field in ("first_bar", "last_bar", "start_beat", "end_beat")}
        self._begin_learn(from_beat=unit["start_beat"], recovery=True)
        self._save()

    def _record_saved_trouble(self, phrase: Phrase, result, *, start: float, end: float, errors: int):
        if not self.fingerprint:
            return
        unit = next((unit for unit in guided_units(self.plan.active_variant, self.plan.piece.bar_boundaries)
                     if unit["start_beat"] == start and unit["end_beat"] == end), None)
        # An extra during a silent unit is still in the performance summary,
        # but cannot become a guided key-finding task without source attacks.
        if unit is None:
            return
        pitches = sorted({entry.note.pitch for entry in result.notes if entry.status != "correct"
                          and phrase.start+start <= entry.note.start < phrase.start+end})
        self.learner_store.record_trouble(self.fingerprint, self.plan.identity, unit,
                                         errors=errors, pitches=pitches)
        self.learner_store.save_resume(self.fingerprint, self.plan.identity, unit)

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
        grid = phrase_grid(phrase, self.plan.piece.bar_boundaries)
        first = next(i for i, beat in enumerate(grid) if abs(beat-start) < 1e-6)
        last = next(i for i, beat in enumerate(grid) if abs(beat-end) < 1e-6)
        absolute_start, absolute_end = phrase.start+start, phrase.start+end
        return Phrase(phrase.number, phrase.first_bar+first, phrase.first_bar+last-1,
                      absolute_start, absolute_end,
                      tuple(n for n in phrase.notes if absolute_start-1e-7 <= n.start < absolute_end-1e-7))

    def _begin_learn(self, *, from_beat: float = 0.0, bump_revision: bool = True,
                     recovery: bool = False):
        from .teaching import TeachingConfig, TeachingController
        if self.plan is None:
            raise ValueError("Open a piece first")
        phrase = self.plan.active_phrase
        grid = phrase_grid(phrase, self.plan.piece.bar_boundaries)
        if not math.isfinite(from_beat) or not 0 <= from_beat < grid[-1]:
            raise ValueError("Choose a measure inside the active passage")
        first = max(i for i, beat in enumerate(grid[:-1]) if beat <= from_beat+1e-7)
        # Skip empty introductory units when finding keys. Timed practice
        # still includes those source rests and the complete original ending.
        while first < len(grid)-1:
            end_index = min(first+2, len(grid)-1)
            if any(phrase.start+grid[first]-1e-7 <= n.start < phrase.start+grid[end_index]-1e-7
                   for n in phrase.notes):
                break
            first = end_index
        if first >= len(grid)-1:
            raise ValueError("No note attacks in the selected fragment")
        retry_range = self.retry_range if recovery else None
        self._stop()
        if recovery:
            self.retry_range = retry_range
            self._guided_return = (self.plan.identity, grid[first])
        self.mode = "learn"
        self.guided_range = (grid[first], grid[end_index])
        unit = self._guided_unit()
        if unit is not None and self.fingerprint:
            self.learner_store.save_resume(self.fingerprint, self.plan.identity, unit)
        if bump_revision:
            self.score_revision += 1
        self.transport_id += 1
        if self.teaching is None:
            self.teaching = TeachingController(TeachingConfig(persistent_hints=self.persistent_hints))
        self.teaching.bind(stage_key=self.plan.identity, revision=self.score_revision,
            variant=self.plan.active_variant, fragment_start=grid[first], fragment_end=grid[end_index],
            now=time.monotonic(), connected=self.midi.connected)
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing a short idea to learn"
        self.next_action = (f"Learn bars {self.display_phrase().first_bar}-{self.display_phrase().last_bar} "
                            "at your own pace, then retry the rhythm.")
        self._save()

    def _guided_marks(self, snapshot: dict) -> list[dict]:
        if self.plan is None:
            return []
        selected = self._score_selection()
        engraving = self.score_artifacts.cached_layout(selected)
        if engraving is None:
            return []
        source = {f"{self.plan.identity}:{index}": note for index, note in
                  zip(self.plan.active_variant.source_indices, self.plan.active_variant.notes)}
        phrase = selected.phrase
        layout = engraving.layout
        glyphs = {glyph["id"]: glyph for glyph in layout.get("notes", [])}
        local_indices = {id(note): index for index, note in enumerate(phrase.notes)}
        settled = {entry["id"]: entry for entry in snapshot.get("note_feedback", [])}
        for entry in snapshot.get("expected_notes", []):
            if settled.get(entry["id"], {}).get("status") != "wrong":
                settled[entry["id"]] = {**entry, "status": "expected"}
        marks = []
        for identifier, entry in settled.items():
            note = source.get(identifier)
            if note is None:
                continue
            local_index = local_indices.get(id(note))
            if local_index is None:
                continue
            canonical_id = source_note_id(note, local_index)
            glyph = glyphs.get(layout.get("attack_map", {}).get(canonical_id))
            if (glyph is not None and glyph.get("is_attack")
                    and glyph.get("pitch") == note.pitch and glyph.get("hand") == note.hand):
                marks.append({**glyph, "target_id": identifier, "status": entry["status"],
                              "hint_used": bool(entry.get("hint_used", False))})
        return marks

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
            time_signatures=self.plan.piece.time_signatures))

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
        if (self.plan is None or self.review_stage_identity != self.plan.identity
                or not self.performance_summary or type(first_bar) is not int
                or type(last_bar) is not int):
            raise ValueError("Finish an assessed attempt before retrying a section")
        selected = next((section for section in self.performance_summary["sections"]
                         if section["first_bar"] == first_bar and section["last_bar"] == last_bar), None)
        if selected is None or selected["errors"] <= 0:
            raise ValueError("Choose a difficult section from the latest assessment")
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
        self.pending_result = None
        if result.correct == len(result.notes) and result.extra_notes == 0:
            self._reset_trouble()
            if self.fingerprint:
                self.learner_store.resolve_trouble(self.fingerprint, p.identity)
        self.retry_range = None
        before = (p.identity, p.bpm)
        message = p.apply_result(correct=result.correct,
                                 total=len(result.notes), extras=result.extra_notes)
        if p.identity == before[0] and p.bpm > before[1]:
            self.recovery_notice = {
                "kind": "speedup", "errors": 0,
                "from_bpm": before[1], "to_bpm": p.bpm,
                "first_bar": p.active_phrase.first_bar,
                "last_bar": p.active_phrase.last_bar,
                "expires_at": time.monotonic() + 7.0,
            }
        if p.identity != before[0]:
            self.open_from_beat = 0.0
            self.performance_summary = None
            self.review_stage_identity = None
        # Native engraving depends on source notation, not playback BPM.
        # Do not discard the score model at every successful tempo increment.
        if p.identity != before[0]:
            self.score_revision += 1
            self.visual_offset_beats = 0.0
        self._save()
        return message

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
            # A user must be able to watch the time-driven score without a
            # connected instrument. Only actual MIDI input enables assessment.
            self.preview_only = not self.midi.connected
            phrase=self.plan.active_phrase
            position = self.open_from_beat if from_beat is None else from_beat
            self.play_from_beat=max(0.0,min(float(position),phrase.end-phrase.start-1e-6))
            self.visual_transport.begin_take(loop_continuation=loop_continuation)
            self.transport_id+=1
            self.live_input.reset_attempt()
            self.running=True
            self.auto=mode == "practice" and not self.preview_only
            self.awaiting_score_revision=None
            self.pending_result=None
            self.feedback_marks=[]
            self.feedback_unmapped=0
            self.recorder=Recorder()
            grid=phrase_grid(phrase,self.plan.piece.bar_boundaries)
            active_bar = max(0, min(len(grid)-2,
                next((i for i in range(len(grid)-1) if grid[i] <= self.play_from_beat < grid[i+1]), len(grid)-2)))
            self.count_in_bar_beats = grid[active_bar + 1] - grid[active_bar]
            self.count_in_meter = [max(1, round(self.count_in_bar_beats)), 4]
            source_beat = phrase.start + self.play_from_beat
            meter = next(((numerator, denominator) for beat, numerator, denominator
                          in sorted(self.plan.piece.time_signatures, reverse=True)
                          if beat <= source_beat + 1e-7), None)
            meter = preparation_meter(
                meter, self.plan.piece.time_signatures, source_beat)
            if meter is not None:
                self.count_in_meter = list(meter)
                self.count_in_bar_beats = meter[0] * 4 / meter[1]
            # The empty staff measure BETWEEN loops already provides the
            # preparation interval. Do not prepend another count-in measure.
            self.visual_gap_beats = self._source_model()["practice_timeline"]["gap"]["duration_beats"]
            self.count_in_beats = (0.0 if loop_continuation else
                lead_in_beats(self.count_in_bar_beats, self.plan.bpm))
            self.next_boundary_beat=next_chunk_end(grid,self.play_from_beat)
            self.run_at=time.monotonic()+self.count_in_beats*60/self.plan.bpm
            self.feedback="Count in, then play"
            self.next_action = ("Watch the moving score; connect a piano for feedback." if self.preview_only
                else f"Play from bar {bar_number_at(grid,self.play_from_beat,phrase.first_bar)} at {self.plan.bpm} BPM.")

    def _continue_at(self, deadline: float, *, from_beat: float = 0.0):
        """Retain polling overshoot instead of moving the musical deadline."""
        self.start(from_beat=from_beat, mode=self.mode, loop_continuation=True)
        self.run_at = deadline

    def _schedule_preparation(self, target: float, *, now: float,
                              from_visual: float, reverse_seconds: float):
        """Reverse on this pass, then traverse one semantic rest into target."""
        model = self._source_model()
        context_index = max(index for index,measure in enumerate(model["measures"])
                            if measure["start_beat"] <= target + 1e-7)
        context = model["measures"][context_index]
        following = (model["measures"][context_index+1]
                     if context_index+1 < len(model["measures"]) else None)
        measure = preparation_measure_descriptor(context,0.0,model["staff_order"],
                                                 following_measure=following)
        self.visual_transport.schedule_preparation(
            measure, source_from_beat=target, from_visual=from_visual,
            now=now, reverse_seconds=reverse_seconds, bpm=self.plan.bpm)
        self.running = False
        self.recorder = None
        self.count_in_beats = 0.0

    def _visual_motion(self, now: float) -> tuple[float, float, float]:
        """Project the current transport snapshot without changing any clocks."""
        phrase = self.plan.active_phrase
        return self.visual_transport.position(
            now, phrase_length=phrase.end-phrase.start, bpm=self.plan.bpm,
            running=self.running,
            pending_auto_result=(self.pending_result is not None and self.auto))


    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            self._apply_listen_failure()
            # Explicit navigation, Stop and Restart abandon the current
            # attempt. Only the timed feedback lifecycle commits assessment.
            # Otherwise Stop during feedback could accidentally earn mastery.
            if action == "reset_path":
                self._reset_current_path(
                    fingerprint=kwargs.get("fingerprint"),
                    confirm=kwargs.get("confirm") is True)
                return
            if action == "score_ready":
                revision = int(kwargs.get("revision", -1))
                # Ignore delayed PNG acknowledgements from older passages.
                if self.awaiting_score_revision == revision and revision == self.score_revision:
                    if self.paused:
                        self._deferred_score_ack = revision
                        return
                    if self.mode == "listen":
                        self.listen.acknowledge_score(revision)
                        self._start_listen_if_ready()
                    elif self.mode == "learn" and self.teaching is not None:
                        self.awaiting_score_revision = None
                        self.teaching.start(now=time.monotonic())
                    else:
                        self.start(from_beat=self.pending_rewind if self.pending_rewind is not None
                                   else self.open_from_beat,
                                   mode="perform" if self.mode == "perform" else "practice")
                return
            if action == "demo_ready":
                # The token identifies unchanged PCM even when a fingering
                # correction advances the score revision during download.
                # Stop, tempo changes and navigation discard that token.
                if self.mode == "listen" and self.listen.acknowledge_audio(kwargs.get("token")):
                    self._start_listen_if_ready()
                return
            if action == "listen":
                self._prepare_listen()
                return
            if action == "perform":
                self._prepare_perform(scope=str(kwargs.get("scope", "current")))
                return
            if action == "practice_weak":
                self._practice_weak()
                return
            if action == "review_retry":
                self._review_retry(kwargs.get("first_bar"), kwargs.get("last_bar"))
                return
            if action == "seek":
                self._seek(kwargs.get("bar"))
                return
            if action == "learn_next":
                if (self.mode != "learn" or self.teaching is None
                        or not self.teaching.snapshot(now=time.monotonic())["completed"]):
                    raise ValueError("Find the current notes before continuing to the next idea")
                self._save_guided_preparation()
                if self._guided_return is not None:
                    self._prepare_practice()
                else:
                    self._begin_course_stage()
                return
            if action == "skip_stage":
                if self.is_builtin_warmup:
                    raise ValueError("Warm-up stages unlock after three clean runs, not skips")
                self._skip_stage(kwargs.get("reason"))
                return
            if action == "place_original":
                if self.is_builtin_warmup:
                    raise ValueError("Warm-up stages unlock after three clean runs")
                self._place_original()
                return
            if action == "revisit_trouble":
                self._revisit_trouble(kwargs.get("stage_key"), kwargs.get("start_beat"))
                return
            if action in ("learn", "learn_retry"):
                if action == "learn":
                    self.course_guided = True
                    if "from_beat" not in kwargs:
                        self._begin_course_stage(explicit_learn=True)
                        return
                previous_start = self.guided_range[0] if self.guided_range else 0.0
                self._begin_learn(from_beat=float(kwargs.get("from_beat", previous_start if action == "learn_retry" else 0.0)),
                                  recovery=self._guided_return is not None and action == "learn_retry")
                return
            if action == "open_at":
                return self._open_selected_measure(kwargs)
            if action == "practice":
                self._prepare_practice()
                if kwargs.get("wait_for_player", False):
                    # Returning from Listen must not start a count-in simply
                    # because the renderer completed. Wait for a fresh piano
                    # note or the central Play action.
                    self.awaiting_score_revision = None
                    self.feedback = "Ready to play"
                    self.next_action = "Play one piano key to begin, or press Play."
                return
            if action == "hints":
                self.persistent_hints = bool(kwargs.get("enabled", False))
                if self.teaching is not None:
                    self.teaching.set_hints(self.persistent_hints, now=time.monotonic())
                return
            if action == "stop":
                self._stop()
                self.feedback="Stopped"
                self.next_action="Start when you are ready."
                return
            if action in ("start", "restart"):
                return self._start_or_restart(action)
            if action == "pause":
                return self._pause_current_session()
            if action == "resume":
                return self._resume_current_session()
            return self._change_stage(action, kwargs)

    def _open_selected_measure(self, kwargs: dict):
        """Open a source measure using the existing lesson navigation policy."""
        # Select a source measure across the entire imported piece,
        # then enter the existing learning or timed-practice flow.
        # No score is awarded simply by changing the starting point.
        if self.plan is None:
            raise ValueError("Open a piece first")
        if self.is_builtin_warmup:
            raise ValueError("Warm-ups use their own hand progression")
        bar = kwargs.get("bar")
        last_bar = len(self.plan.piece.bar_boundaries) - 1
        if type(bar) is not int or not 1 <= bar <= last_bar:
            raise ValueError(f"Choose a whole measure between 1 and {last_bar}")
        requested_mode = kwargs.get("mode", "learn")
        if requested_mode not in ("learn", "practice"):
            raise ValueError("Choose Learn Notes or Practice Rhythm")
        plan = self.plan
        index, section, selected_bar = locate_course_section(plan, bar)
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
        if self.mode == "listen":
            self._prepare_listen()
            return
        if self.mode == "learn":
            self.control("practice")
            return
        if (self.plan is not None
                and self.score_artifacts.source_bpm_changed(self.plan.piece.bpm)):
            # Only a genuinely different source engraving needs a
            # new model. Tempo changes reuse the exact same score
            # with a different transport speed.
            self._stop()
            self.score_revision += 1
            self.awaiting_score_revision = self.score_revision
            self.feedback = "Preparing sheet music"
            return
        if (action == "restart" and self.plan is not None
                and self.mode == "practice" and self.plan.exercise.kind != "perform"):
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
        """Pause learning, playback or preparation using the current clock."""
        if self.paused:
            raise ValueError("Cannot pause an exercise that is already paused")
        context = self._phase(time.monotonic())
        if context not in ("playing", "count_in", "feedback", "recovering", "loading", "guided_wait", "preview_gap"):
            raise ValueError("Cannot pause unless an exercise is playing or preparing")
        self.pause_context = context
        self.visual_transport.pause(at=time.monotonic())
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.pause(now=time.monotonic())
        return

    def _resume_current_session(self):
        """Resume the teaching controller and shift owned transport deadlines."""
        if not self.paused:
            raise ValueError("Cannot resume unless an exercise is paused")
        # Sample once; the transport owner shifts every active deadline by the
        # same duration, preserving preparation and backward-recovery motion.
        now = time.monotonic()
        learning = self.mode == "learn" and self.teaching is not None
        if learning:
            self.teaching.resume(now=time.monotonic())
        self.visual_transport.resume(
            now=now,
            shift_run_at=(not learning and (
                self.running or self._preview_loop_pending
                or (self.pending_result is not None and self.auto))),
        )
        self.pause_context = None
        if self.running:
            self.feedback = "Count in" if time.monotonic() < self.run_at else "Playing"
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
        if action == "select_step":
            number = kwargs.get("number")
            # Retain integer strings/whole floats, without truncating a step.
            if (isinstance(number, bool) or not isinstance(number, (int, float, str))
                    or (isinstance(number, float) and not number.is_integer())):
                raise ValueError("Choose a whole lesson step number")
            try:
                number = int(number)
            except ValueError:
                raise ValueError("Choose a whole lesson step number") from None
            if not 1 <= number <= len(p.lesson_steps):
                raise ValueError("Lesson step out of bounds")
        was_guided = self.mode == "learn"
        guided_start = self.guided_range[0] if self.guided_range is not None else 0.0
        guided_return = self._guided_return
        guided_retry_range = self.retry_range
        self._stop()
        self._reset_trouble()
        if action == "select_step":
            self.open_from_beat = 0.0
            p.select_step(number)
        elif action == "next":
            self.open_from_beat = 0.0
            p.jump(1)
        elif action == "previous":
            self.open_from_beat = 0.0
            p.jump(-1)
        elif action == "hand":
            requested = str(kwargs.get("hand", "both"))
            if self.is_builtin_warmup and requested in p.hands and p.hands.index(requested) > p.hand_index:
                previous_step = p.lesson_steps[p.hands.index(requested) - 1]
                if previous_step.key not in p.mastered:
                    raise ValueError("Complete three clean passes to unlock the next hand")
            p.set_hand(requested)
            self.open_from_beat = 0.0
        elif action == "tempo":
            p.set_bpm(int(kwargs["bpm"]))
        elif action == "tempo_up":
            p.increase_tempo()
        elif action == "tempo_down":
            p.decrease_tempo()
        else:
            raise ValueError(f"Unsupported action: {action}")
        # Native notation is engraved in source coordinates: changing
        # only playback BPM must not invalidate the score/reload Godot.
        if action not in ("tempo", "tempo_up", "tempo_down"):
            self.score_revision+=1
        self.feedback="Ready"
        self.next_action="Start when you are ready."
        if was_guided:
            if action in ("tempo", "tempo_up", "tempo_down"):
                recovery = guided_return is not None and guided_return[0] == p.identity
                if recovery:
                    self.retry_range = guided_retry_range
                self._begin_learn(from_beat=guided_start, bump_revision=False, recovery=recovery)
            elif self.course_guided:
                self._begin_course_stage(bump_revision=False, explicit_learn=action == "hand")
            else:
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
            if self.auto and message != "Piece mastered":
                if self.course_guided and self.plan.identity != previous_identity:
                    self._begin_course_stage()
                    return
                if self.score_revision != previous_revision:
                    # Never consume the next count-in while Godot is still
                    # rendering the newly selected score and its note map.
                    self.awaiting_score_revision = self.score_revision
                    self.auto = False
                    self.feedback = "Preparing next passage"
                    self.next_at = 0
                else:
                    # Clean takes advance to the appended copy. Failed
                    # takes rewind the SAME copy (already animated during
                    # feedback); there is no jump/re-engrave on retry.
                    if not self._retry_previous_pass:
                        self.visual_offset_beats += self._source_model()["practice_timeline"]["stride_beats"]
                    target = (self.practice_preparation["source_from_beat"]
                              if self._retry_previous_pass and self.practice_preparation else 0.0)
                    self._continue_at(deadline, from_beat=target)
            else:
                self.next_at=0
                self.auto=False
                self.feedback = message or self.feedback
        return

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
                assessed = evaluate(Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                    phrase.start+self.play_from_beat, phrase.end,
                    tuple(note for note in phrase.notes if note.start >= phrase.start+self.play_from_beat)),
                    self.plan.hand, self.plan.bpm, self.recorder.presses if self.recorder else [])
                # Rolling detection can include the preceding idea;
                # saved trouble describes only this canonical unit.
                unit_errors = [entry for entry in assessed.notes
                    if entry.status in ("missed", "wrong")
                    and phrase.start+decision.restart_beat <= entry.note.start < phrase.start+decision.end_beat]
                pitches = sorted({entry.note.pitch for entry in unit_errors})
                self.learner_store.record_trouble(self.fingerprint, self.plan.identity, unit,
                                                 errors=len(unit_errors), pitches=pitches)
                self.learner_store.save_resume(self.fingerprint, self.plan.identity, unit)
        self.plan.streak=0
        self.plan.failures+=1
        before=self.plan.bpm
        self.plan.bpm=max(SETTINGS.minimum_bpm,round(before*SETTINGS.recovery_tempo_multiplier))
        self._save()
        self._schedule_preparation(decision.restart_beat, now=now,
            from_visual=self.visual_offset_beats + score_beat,
            reverse_seconds=self.feedback_seconds)
        key = (self.plan.identity, decision.restart_beat, decision.end_beat)
        self._trouble_count = self._trouble_count + 1 if key == self._trouble_key else 1
        self._trouble_key = key
        self._guided_recovery_pending = self._trouble_count >= SETTINGS.guided_recovery_after_failures
        recovery = recovery_display(
            decision, grid=grid, first_bar=phrase.first_bar,
            before_bpm=before, after_bpm=self.plan.bpm,
            now=now, guided=self._guided_recovery_pending)
        self.recovery_notice = recovery.notice
        self.retry_range = recovery.retry_range
        self.feedback = recovery.feedback
        self.next_action = recovery.next_action
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
            gap_seconds = self.visual_gap_beats * 60 / self.plan.bpm
            self.next_at = self.run_at + duration + gap_seconds
            self.feedback = "Timing preview - repeating after one empty measure"
            self.next_action = "Connect your MIDI piano to earn clean runs."
            if now >= self.next_at:
                self._update()
            return
        result = self.assessment.assess_take(
            phrase, hand=self.plan.hand, bpm=self.plan.bpm,
            played=self.recorder.presses if self.recorder else [],
            from_beat=self.play_from_beat, end_beat=ending,
            evaluator=evaluate)
        # Keep the just-played score visible for feedback. Curriculum changes
        # are applied only after the display interval, never mid-feedback.
        try:
            projection = project_assessment(result, phrase, self.plan.bpm,
                                            self.engraving().layout, played_from_beat=self.play_from_beat)
            self.feedback_marks = projection["marks"]
            self.feedback_unmapped = projection["unmapped"]
        except (ValueError, RuntimeError, KeyError) as exc:
            self.feedback_marks = []
            self.feedback_unmapped = len(result.notes)
            self.feedback = f"Engraving feedback unavailable: {exc}"
        else:
            self.feedback = result.summary
        self.running=False
        self.recorder=None
        self.performance_summary = self._performance_review(phrase, result)
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
                self.learner_store.resolve_trouble(self.fingerprint, self.plan.identity)
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
                + (now-self.run_at)*self.plan.bpm/60,
            reverse_seconds=self.feedback_seconds)
        self.feedback = "Selected section finished · " + result.summary
        self.next_action = "Next: play the whole passage from its beginning to earn mastery."
        self.retry_range = None

    def _finish_full_passage(self, result, total_beats: float, duration: float, now: float):
        """Complete finish full passage after a scored take."""
        self.pending_result=result
        if not result.clean and self.auto:
            # Repeated wrong takes traverse backward over the visible source
            # instead of teleporting to beat zero or appending failed copies.
            self._retry_previous_pass = True
            self._schedule_preparation(self.play_from_beat, now=now,
                from_visual=self.visual_offset_beats + self.play_from_beat
                    + (now-self.run_at)*self.plan.bpm/60,
                reverse_seconds=max(self.feedback_seconds,
                    min(4.0, total_beats * 60.0 / self.plan.bpm / 3.0)))
        if not result.clean:
            # Failure breaks consecutive clean takes immediately, even if
            # Start/Restart/Stop discards this feedback before its commit.
            # Success and mastery still wait until the feedback interval ends.
            self.plan.streak = 0
            self._save()
            if self.is_builtin_warmup:
                self.auto = False  # Keep the beginner-study review available.
                self._preparation_pending = False
                self.practice_preparation = None
                self.pending_rewind = None
                self._visual_rewind_from = None
                self._visual_rewind_to = None
        self.next_action=next_full_attempt(self.plan, result)
        if not self.auto:
            self.next_at = 0
        elif not self._retry_previous_pass:
            self.next_at = self.run_at + duration + self.visual_gap_beats*60/self.plan.bpm
            if now >= self.next_at:
                self._update()

    def _update(self):
        self._poll_midi_connection()
        self._apply_listen_failure()
        if not self.plan:
            return
        now=time.monotonic()
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.set_connected(self.midi.connected, now=now)
            self.teaching.tick(now=now)
            self._save_guided_preparation()
            return
        if self.paused:
            return
        if self.mode == "listen":
            if self.running and self.listen.finished(now=now, run_at=self.run_at):
                self.running = False
                self.feedback = "Example complete"
                self.next_action = "Choose Learn to find the notes, or Practice to play the rhythm."
            return
        if self._preview_loop_pending:
            if self.next_at and now >= self.next_at:
                deadline = self.next_at
                self.visual_offset_beats += self._source_model()["practice_timeline"]["stride_beats"]
                self._continue_at(deadline)
            return
        if self._preparation_pending:
            self.practice_preparation["phase"] = (
                "reverse" if now < self._preparation_at else "preparing")
        if self.pending_result is not None:
            self._advance_pending_feedback(now)
            return
        if self.awaiting_score_revision is not None:
            return
        if self.pending_rewind is not None:
            if now >= self.next_at:
                if self._guided_recovery_pending:
                    self._begin_learn(from_beat=self.pending_rewind, recovery=True)
                else:
                    self._continue_at(self.next_at, from_beat=self.pending_rewind)
            return
        if not self.running or self.paused or now < self.run_at:
            return
        phrase=self.plan.active_phrase
        total_beats=phrase.end-phrase.start
        elapsed_beats=max(0.0,(now-self.run_at)*self.plan.bpm/60)
        score_beat=self.play_from_beat+elapsed_beats
        grid=phrase_grid(phrase,self.plan.piece.bar_boundaries)
        beats_per_bar=grid[1]-grid[0]
        # Detect rolling five-error windows at the completed two-bar boundary. Silent
        # previews never generate failure, assessment or mastery.
        while (self.mode == "practice" and self.review_end_beat is None and not self.preview_only
               and self.next_boundary_beat and score_beat >= self.next_boundary_beat):
            if self.is_builtin_warmup:
                decision=check_two_bar_window(phrase,self.plan.hand,self.plan.bpm,
                    self.recorder.presses if self.recorder else [],
                    from_beat=self.play_from_beat, end_beat=self.next_boundary_beat,
                    beats_per_bar=beats_per_bar, threshold=SETTINGS.warmup_recovery_errors,
                    window_start_beat=chunk_start_at_end(grid,self.next_boundary_beat))
            else:
                decision=check_rolling_two_bar_window(phrase,self.plan.hand,self.plan.bpm,
                    self.recorder.presses if self.recorder else [],
                    from_beat=self.play_from_beat, end_beat=self.next_boundary_beat, grid=grid,
                    threshold=SETTINGS.recovery_errors_in_window)
            if decision is not None:
                self._apply_rolling_recovery(decision, phrase, grid, score_beat, now)
                return
            previous_boundary=self.next_boundary_beat
            self.next_boundary_beat=next_chunk_end(grid,previous_boundary)
            if self.next_boundary_beat <= previous_boundary + 1e-7:
                self.next_boundary_beat=0.0
        ending = (min(total_beats, self.review_end_beat)
                  if self.review_end_beat is not None else total_beats)
        duration=(ending-self.play_from_beat)*60/self.plan.bpm
        # Settlement belongs inside the musical rest, including very short
        # explicit meters. It must never extend the next attempt's deadline.
        settlement = .20
        if self.preview_only or (self.auto and self.review_end_beat is None):
            settlement = min(settlement, self.visual_gap_beats*60/self.plan.bpm)
        if now < self.run_at+duration+settlement:
            return
        self._complete_attempt(phrase, ending, total_beats, duration, now)

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
        return self.assessment.live_marks(
            phrase=p.active_phrase, hand=p.hand, bpm=p.bpm,
            played=self.recorder.presses if self.recorder else [],
            played_from_beat=self.play_from_beat, elapsed_seconds=elapsed_seconds,
            bar_boundaries=p.piece.bar_boundaries,
            layout=engraving.layout, projector=project_assessment)

    def state(self) -> dict:
        with self.lock:
            self._update()
            return project_session_state(self._capture_session_snapshot())

    def _capture_session_snapshot(self) -> SessionSnapshot:
        """Capture values under the session lock, including stateful read adapters.

        Clock reads retain their original order and purpose. Teaching snapshots
        may tick the controller; all such work finishes before pure projection.
        """
        p = self.plan
        seek_grid = self._seek_grid()
        activity = ActivitySnapshot(
            sampled_at=time.monotonic(),
            learner=self._learner_snapshot() if p is not None else None,
            placement_available=(not self.is_builtin_warmup and placement_candidate(p) is not None) if p is not None else False,
            skip_available=(not self.is_builtin_warmup and p.lesson_step_number < len(p.lesson_steps)) if p is not None else False,
            seek_available=self.paused and seek_grid is not None,
            seek_range=({"first_bar": p.active_phrase.first_bar, "last_bar": p.active_phrase.last_bar}
                        if seek_grid is not None else None),
            next_action=self.next_action,
            transition_now=((self.paused_at if self.paused else time.monotonic())
                if self.next_at and (self.pending_result is not None or self.pending_rewind is not None) else 0.0),
            next_at=self.next_at,
            pending_transition=self.pending_result is not None or self.pending_rewind is not None,
            retry_range=self.retry_range,
            notice_now=time.monotonic() if self.recovery_notice is not None else 0.0,
            recovery_notice=self.recovery_notice,
            guided_recovery=self._guided_recovery_pending or self._guided_return is not None,
            pause_context=self.pause_context,
            demo=self.listen.snapshot(),
            performance_summary=self.performance_summary,
            review_pending=self.review_end_beat is not None,
            midi_input_count=self.midi.input_count,
            midi_input_note=self.midi.input_note,
            midi_now=time.monotonic() if self.midi.input_at is not None else 0.0,
            midi_input_at=self.midi.input_at,
            metronome=self.library.settings["metronome"],
            hints_enabled=self.persistent_hints,
            fingering=p.piece.fingering_plan.summary()
                if p is not None and p.piece.fingering_plan is not None else None,
        )
        visual_now = self.paused_at if self.paused else time.monotonic()
        visual_beat = self.play_from_beat
        if self.running and visual_now >= self.run_at and p is not None:
            visual_beat += (visual_now-self.run_at)*p.bpm/60.0
        activity = replace(activity, midi_display=self.live_input.snapshot(
            now=time.monotonic(),
            phrase=p.active_phrase if p is not None else None,
            hand=p.hand if p is not None else "both", beat=visual_beat,
            playing=(p is not None and self.mode in ("practice", "perform")
                     and (self.running or self._phase(visual_now) == "ready")),
        ))
        if p is None:
            return SessionSnapshot(mode=self.mode, feedback=self.feedback,
                device=self.midi.device, revision=self.score_revision,
                transport_id=self.transport_id, activity=activity)
        practice_timeline = self._source_model()["practice_timeline"]
        self.visual_gap_beats = practice_timeline["gap"]["duration_beats"]
        ex, variant = p.exercise, p.active_variant
        lesson_steps = tuple((step.exercise_index, step.hand, step.key) for step in p.lesson_steps)
        sampled_at = time.monotonic()
        now = self.paused_at if self.paused else sampled_at
        elapsed = now-self.run_at
        phase = self._phase(now)
        live_marks = self._live_feedback(elapsed) if phase == "playing" else []
        visual_motion = self._visual_motion(now)
        lesson = build_lesson_snapshot(
            p, ex, variant, fingerprint=self.fingerprint,
            warmup=self.is_builtin_warmup, lesson_steps=lesson_steps)
        timing = TimingSnapshot(
            sampled_at=sampled_at, now=now, run_at=self.run_at,
            running=self.running, paused=self.paused, auto=self.auto,
            preview_only=self.preview_only, play_from_beat=self.play_from_beat,
            open_from_beat=self.open_from_beat, pending_rewind=self.pending_rewind,
            review_end_beat=self.review_end_beat,
            awaiting_score_revision=self.awaiting_score_revision,
            count_in_beats=self.count_in_beats,
            count_in_bar_beats=self.count_in_bar_beats, count_in_meter=self.count_in_meter,
            midi_notes=len(self.recorder.presses) if self.recorder is not None else 0,
            visual_offset_beats=self.visual_offset_beats,
            visual_gap_beats=self.visual_gap_beats, visual_motion=visual_motion,
            practice_timeline=practice_timeline, practice_preparation=self.practice_preparation,
            take_result=({"clean": bool(self.pending_result.clean),
                          "correct": self.pending_result.correct,
                          "total": len(self.pending_result.notes)}
                         if self.mode == "practice" and self.pending_result is not None else None),
            feedback_marks=self.feedback_marks, live_marks=live_marks,
            feedback_unmapped=self.feedback_unmapped,
            scoring_available=(not self.preview_only and self.midi.connected
                               and self.mode in ("practice", "perform")),
        )
        guided = None
        if self.mode == "learn" and self.teaching is not None:
            teaching = self.teaching.snapshot(now=time.monotonic())
            phrase = self.display_phrase()
            guided = GuidedSnapshot(
                teaching=teaching,
                fragment={"first_bar": phrase.first_bar, "last_bar": phrase.last_bar,
                          "start_beat": self.guided_range[0], "end_beat": self.guided_range[1]},
                phase=self._phase(now),
                has_more_units=activity.learner["next_unit"] is not None and self._guided_return is None,
                returning=bool(self._guided_return), required_notes=len(phrase.notes),
                duration_beats=phrase.end-phrase.start,
                feedback_marks=self._guided_marks(teaching),
            )
        return SessionSnapshot(mode=self.mode, feedback=self.feedback,
            device=self.midi.device, revision=self.score_revision,
            transport_id=self.transport_id, phase=phase, activity=activity,
            lesson=lesson, timing=timing, guided=guided)

    def _score_selection(self) -> ScoreSelection:
        """Capture the selected source under the application lock."""
        if self.plan is None:
            raise ValueError("No piece loaded")
        p = self.plan
        return ScoreSelection(piece=p.piece, phrase=self.display_phrase(),
            hand=p.hand, stage_key=p.identity, revision=self.score_revision,
            fingerprint=self.fingerprint)

    def _source_model(self) -> dict:
        with self.lock:
            return self.score_artifacts.source_model(self._score_selection())

    def semantic_score(self) -> dict:
        with self.lock:
            return self.score_artifacts.semantic_score(self._score_selection())

    def engraving(self) -> EngravedScore:
        with self.lock:
            return self.score_artifacts.engraving(self._score_selection())

    def engraved(self, page: int = 0) -> str:
        with self.lock:
            return self.score_artifacts.engraved(self._score_selection(), page)

    def engraved_png(self, page: int = 0, *, width: int = 2000) -> bytes:
        # Preserve invalid-width validation even when no piece is loaded.
        validate_png_width(width)
        with self.lock:
            return self.score_artifacts.engraved_png(self._score_selection(), page, width=width)

    def geometry(self, *, native_notes: bool = True) -> dict:
        with self.lock:
            return self.score_artifacts.geometry(self._score_selection(), native_notes=native_notes)

    def lesson_overview(self) -> dict:
        """Full readable curriculum, with unique per-hand/per-level progress."""
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            p = self.plan
            return {
                "trouble_spots": self._valid_trouble_spots(),
                "route_version": p.route_version,
                "piece_fingerprint": self.fingerprint,
                "current_step": p.lesson_step_number,
                "total_steps": len(p.lesson_steps),
                "completed_steps": p.lesson_steps_mastered,
                "steps": [
                    {"number": i+1, "exercise": step.exercise_index+1,
                     "hand": step.hand, "level": step.level, "key": step.key,
                     "kind": step.kind, "first_bar": step.first_bar,
                     "last_bar": step.last_bar, "required_notes": step.required_notes,
                     "completed": step.key in p.mastered,
                     "skip_status": self._learner_saved(step.key)["skip_status"],
                     "skip_reason": self._learner_saved(step.key)["skip_reason"]}
                    for i, step in enumerate(p.lesson_steps)
                ],
            }


# Keep the original public Handler import stable for clients and tests.
from .transport.http import Handler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--no-midi",action="store_true",help="Test server without an attached MIDI device")
    args=parser.parse_args()
    Handler.engine=PracticeEngine(enable_midi=not args.no_midi)
    # The service must never bind to a public interface.
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Piano Teacher backend: http://127.0.0.1:{args.port}",flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        Handler.engine.connect("")
        Handler.engine.db.close()

if __name__=="__main__":
    main()
