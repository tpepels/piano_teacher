"""Loopback-only practice service for the native Godot UI.

Start: python -m piano_teacher.server. No Internet, account, or Qt required.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .learning import LearningPlan, build_exercises
from .exercise_generator import generate_variants
from .practice import Recorder, evaluate
from .importing.pieces import import_piece
from .score import render_layout, EngravedScore
from .feedback import project_assessment
from .library import ScoreLibrary
from .preprocessing_cache import PreprocessingCache
from .library_health import LibraryHealth
from .warmups import is_warmup
from .raster import rasterize_score
from .recovery import check_rolling_two_bar_window, check_two_bar_window
from .music import Phrase, source_note_id, note_name
from .notation.lesson import build_lesson_score, infer_piece_clefs
from .notation.model import build_score_model
from .lesson_validation import require_lesson_alignment
from .lesson_timing import lead_in_beats, preparation_meter
from .measure_grid import phrase_grid, next_chunk_end, chunk_start_at_end, bar_number_at, two_bar_chunks
from .live_feedback import settled_assessment, expired_attack_misses
from .live_input_view import LiveInputView
from .hardware_probe import HardwareProbe
from .instruction import next_full_attempt
from .learner_state import LearnerStateStore, guided_units, next_guided_unit, placement_candidate
from .lesson_settings import SETTINGS


class PracticeEngine:
    def __init__(self, data_dir: Path | None = None, enable_midi: bool = True):
        self.lock = threading.RLock()
        self.plan: LearningPlan | None = None
        self.score = None
        self.source = None
        self.is_builtin_warmup = False
        self.fingerprint = ""
        self.recorder: Recorder | None = None
        self.run_at = 0.0
        self.play_from_beat = 0.0
        self.open_from_beat = 0.0  # Explicit opening measure; never an inferred clock
        self.next_boundary_beat = 0.0
        self.pending_rewind: float | None = None
        self._rewind_requires_layout = False
        self.feedback_seconds = SETTINGS.feedback_seconds
        self.recovery_notice: dict | None = None
        self.paused = False
        self.paused_at = 0.0
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
        self.demo: dict | None = None
        self._demo_audio = None
        self._demo_cache = None
        self._demo_thread: threading.Thread | None = None
        self._demo_score_ready = False
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
        self._layout_cache: EngravedScore | None = None
        self._layout_revision = -1
        self._layout_bpm: float | None = None
        self._layout_cache_key: str | None = None
        self._page_png: dict[tuple[int, int], bytes] = {}
        self.next_at = 0.0
        self.awaiting_score_revision: int | None = None
        self.pending_result = None
        self.feedback_marks: list[dict] = []
        self.feedback_unmapped = 0
        self.midi_port = None
        self.midi_device = ""
        # Phase 8K: bounded reconnect of the explicitly saved MIDI preference.
        # Never infer another device or resume an interrupted take.
        self._midi_next_scan_at = 0.0
        self._midi_retry_after = 0.0
        self.midi_input_count = 0
        self.midi_input_note = None
        self.midi_input_at = None
        self.live_input = LiveInputView()
        self.hardware_probe = HardwareProbe()
        self.enable_midi = enable_midi
        self.library = ScoreLibrary(config_dir=(data_dir / 'config') if data_dir is not None else None)
        self.library_health = LibraryHealth(self.library)
        data_dir = data_dir or Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "piano-teacher"
        data_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = data_dir
        self.preprocessing = PreprocessingCache(data_dir / "preprocessed")
        self.db = sqlite3.connect(data_dir / "progress.db", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER)")
        columns={row[1] for row in self.db.execute("PRAGMA table_info(sessions)")}
        if "target_bpm" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN target_bpm INTEGER")
        if "variant_index" not in columns:
            self.db.execute("ALTER TABLE sessions ADD COLUMN variant_index INTEGER NOT NULL DEFAULT 0")
        for column, declaration in (("route_version", "INTEGER"), ("step_key", "TEXT"),
                                    ("first_bar", "INTEGER"), ("last_bar", "INTEGER"),
                                    ("level", "TEXT"), ("exercise_kind", "TEXT")):
            if column not in columns:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {column} {declaration}")
        self.db.execute("CREATE TABLE IF NOT EXISTS mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY (fingerprint, exercise))")
        self.db.execute("""CREATE TABLE IF NOT EXISTS stage_tempos (
            fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
            bpm INTEGER NOT NULL,
            PRIMARY KEY (fingerprint,stage_key))""")
        self.db.commit()
        self.learner_store = LearnerStateStore(self.db)

    MIDI_SCAN_SECONDS = 3.0
    MIDI_RETRY_SECONDS = 4.0

    def _midi_lost(self, reason: str = "device_disconnected") -> None:
        """Cancel every active/pending take before allowing reconnection."""
        old_name, old_port = self.midi_device, self.midi_port
        self.midi_device = ""
        self.midi_port = None
        self.live_input.clear_device()
        # The last key shown in the HUD must not survive a USB loss.
        self.midi_input_note = None
        self.midi_input_at = None
        self.hardware_probe.stop(reason)
        self._stop()
        if self.teaching is not None:
            self.teaching.set_connected(False, now=time.monotonic())
        if old_port is not None:
            try:
                old_port.close()
            except Exception:
                pass  # ALSA may have already released an unplugged port.
        self._midi_retry_after = time.monotonic() + self.MIDI_RETRY_SECONDS
        self.feedback = f"MIDI piano disconnected: {old_name}. Reconnect it, then press Start."
        self.next_action = "Reconnect your piano, then press Start."

    def ports(self) -> list[str]:
        """Discover input names and cautiously restore the chosen device.

        Only the explicitly stored preferred device may reconnect. Discovery
        failure never destroys a known healthy connection. Neither successful
        reconnection nor startup with a remembered piano starts gameplay.
        """
        if not self.enable_midi:
            return []
        with self.lock:
            try:
                import mido
                names = list(mido.get_input_names())
            except Exception as exc:
                if self.midi_device and (self.midi_port is None
                        or getattr(self.midi_port, "closed", False)):
                    self._midi_lost()
                self.feedback = (
                    f"Cannot list MIDI input devices: {exc}. "
                    "Check your MIDI backend and connection.")
                raise RuntimeError(self.feedback) from exc
            if self.midi_device and (self.midi_port is None
                    or getattr(self.midi_port, "closed", False)
                    or self.midi_device not in names):
                self._midi_lost()
            preferred = self.library.settings.get("midi_device", "")
            now = time.monotonic()
            if (preferred and not self._piano_connected()
                    and preferred in names and now >= self._midi_retry_after):
                try:
                    port = mido.open_input(preferred, callback=self._receive)
                except Exception as exc:
                    self._midi_retry_after = now + self.MIDI_RETRY_SECONDS
                    self.feedback = (
                        f"Cannot reconnect MIDI piano {preferred}: {exc}. "
                        "Check the USB connection or select a device in Settings.")
                    self.next_action = "Reconnect your piano, then press Start."
                else:
                    self.midi_port = port
                    self.midi_device = preferred
                    if self.teaching is not None:
                        self.teaching.set_connected(True, now=now)
                    self.feedback = (
                        f"MIDI piano reconnected: {preferred}. Press Start when ready.")
                    self.next_action = "Press Start when you are ready."
            return names

    def connect(self, name: str):
        with self.lock:
            port = self.midi_port
            self.midi_port = None
            self.midi_device = ""
            self.live_input.clear_device()
            self.midi_input_note = None
            self.midi_input_at = None
            self.hardware_probe.stop("device_changed")
            self._stop()
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass  # Failure closing a lost device must not retain it.
            self._midi_retry_after = 0.0
            self._midi_next_scan_at = time.monotonic() + self.MIDI_SCAN_SECONDS
            if not isinstance(name, str):
                raise ValueError("MIDI input name must be text")
            if name:
                if not self.enable_midi:
                    raise ValueError("MIDI input is disabled")
                try:
                    import mido
                    self.midi_port = mido.open_input(name, callback=self._receive)
                except Exception as exc:
                    self.feedback = f"Cannot connect to MIDI input {name}: {exc}. Check the device and try again."
                    raise RuntimeError(self.feedback) from exc
                self.midi_device = name
                self.feedback = f"MIDI piano connected: {name}. Press Start when ready."
            else:
                self.feedback = "MIDI piano disconnected. Connect a device to enable scoring."
            if self.teaching is not None:
                self.teaching.set_connected(self.midi_port is not None, now=time.monotonic())
            self.next_action = "Press Start when you are ready." if name else "Connect your piano for feedback."
            self.library.update(midi_device=name)

    def hardware_diagnostics(self) -> dict:
        with self.lock:
            return self.hardware_probe.snapshot()

    def hardware_diagnostics_action(self, action: str) -> dict:
        with self.lock:
            if action == "start":
                if not self._piano_connected():
                    raise RuntimeError("Connect a MIDI piano in Settings before testing")
                if self.running:
                    raise RuntimeError("Stop the current practice attempt before testing MIDI input")
                return self.hardware_probe.start(self.midi_device)
            if action == "stop":
                return self.hardware_probe.stop()
            raise ValueError("Hardware diagnostics action must be start or stop")

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
            self.hardware_probe.receive(message, now=now)
            if message.type == "note_on" and message.velocity > 0:
                self.midi_input_count += 1
                self.midi_input_note = message.note
                self.midi_input_at = now
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
                if (self.teaching is not None and self._piano_connected()
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

    def _piano_connected(self) -> bool:
        return self.midi_port is not None and not getattr(self.midi_port, "closed", False)

    def load(self, path: str, *, warmup: bool = False):
        source = Path(path).expanduser().resolve()
        fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        piece, score = self.preprocessing.load_import(
            source, fingerprint, importer=import_piece)
        with self.lock:
            self._stop()
            self._reset_trouble()
            self.course_guided = False
            self.source = str(Path(path).resolve())
            self.is_builtin_warmup = warmup
            self.open_from_beat = 0.0
            self.fingerprint = fingerprint
            self._layout_cache = None
            self._layout_revision = -1
            self._layout_cache_key = None
            self._page_png.clear()
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

    def _restore(self):
        p = self.plan
        if p is None:
            return
        row = self.db.execute("SELECT exercise,hand,bpm,streak,target_bpm,variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind FROM sessions WHERE fingerprint=?",(self.fingerprint,)).fetchone()
        legacy_exercises = None
        if row:
            exact = next((step for step in p.lesson_steps if step.key == row[7]), None)
            if exact is not None:
                p.restore_location(kind=exact.kind, first_bar=exact.first_bar, last_bar=exact.last_bar,
                                   hand=exact.hand, level=exact.level)
                equivalent = True
            elif row[6] and row[8] is not None and row[9] is not None:
                p.restore_location(kind=row[11] or "learn", first_bar=int(row[8]), last_bar=int(row[9]),
                                   hand=row[1], level=row[10] or "original")
                equivalent = False
            else:
                # Old integer positions refer to the old two-bar route. Never
                # interpret them as positions in the new consolidated course.
                legacy_exercises = build_exercises(p.piece, consolidate=False)
                old = legacy_exercises[min(max(0, int(row[0])), len(legacy_exercises) - 1)]
                hand = row[1] if row[1] in ("right", "left", "both") else "both"
                old_variants = generate_variants(old.phrase, hand)
                if not old_variants:
                    hand = "both"
                    old_variants = generate_variants(old.phrase, hand)
                old_variant = old_variants[min(max(0, int(row[5] or 0)), len(old_variants) - 1)]
                p.restore_location(kind=old.kind, first_bar=old.phrase.first_bar, last_bar=old.phrase.last_bar,
                                   hand=hand, level=old_variant.level)
                equivalent = (row[1] == hand and p.hand == hand and p.active_variant.level == old_variant.level
                              and p.active_phrase.start == old_variant.phrase.start
                              and p.active_phrase.end == old_variant.phrase.end
                              and p.active_phrase.notes == old_variant.notes
                              # Old unversioned whole-performance rows did
                              # not record whether the final sustained note
                              # or previously silent measures were included.
                              # Reuse their tempo, but never an unverifiable
                              # target-speed clean streak.
                              and old.kind != "perform")
            p.set_bpm(max(SETTINGS.minimum_bpm, min(SETTINGS.maximum_bpm, int(row[4] or p.piece.bpm))))
            p.bpm = max(SETTINGS.minimum_bpm, min(p.target_bpm, int(row[2])))
            p.streak = min(SETTINGS.clean_runs_to_master-1, max(0, int(row[3]))) if equivalent else 0
        for key,bpm in self.db.execute("SELECT stage_key,bpm FROM stage_tempos WHERE fingerprint=?",(self.fingerprint,)):
            if any(step.key == key for step in p.lesson_steps):
                p.stage_tempos[key] = max(SETTINGS.minimum_bpm,
                                          min(p.target_bpm,int(bpm)))
        # A current session may predate per-stage tempos; retain its exact
        # judged tempo, but only when the stage can be identified reliably.
        if row is not None:
            p.stage_tempos[p.identity] = p.bpm
        for key,bpm in self.db.execute("SELECT exercise,bpm FROM mastery WHERE fingerprint=?",(self.fingerprint,)):
            p.mastered[key]=bpm
        # Preserve legacy rows, and recognize them only when the exact same
        # hand, level and source events still form an individual course stage.
        legacy_mastery = [(key, bpm) for key, bpm in p.mastered.items() if not key.startswith("course:")]
        if legacy_mastery:
            legacy_exercises = legacy_exercises or build_exercises(p.piece, consolidate=False)
            for old in legacy_exercises:
                for hand in ("right", "left", "both"):
                    for variant in generate_variants(old.phrase, hand):
                        legacy_key = f"{old.key}:{hand}:{variant.level}"
                        if legacy_key not in p.mastered:
                            continue
                        new_key = p._stage_key(old, hand, variant)
                        if any(step.key == new_key for step in p.lesson_steps):
                            p.mastered[new_key] = p.mastered[legacy_key]

    def _save(self):
        p=self.plan
        if p is None:
            return
        self.db.execute("INSERT OR REPLACE INTO sessions (fingerprint,exercise,hand,bpm,streak,target_bpm,variant_index,route_version,step_key,first_bar,last_bar,level,exercise_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (self.fingerprint,p.index,p.hand,p.bpm,p.streak,p.target_bpm,p.variant_index,
                         p.route_version,p.identity,p.exercise.phrase.first_bar,p.exercise.phrase.last_bar,
                         p.active_variant.level,p.exercise.kind))
        p.stage_tempos[p.identity] = p.bpm
        for key, bpm in p.stage_tempos.items():
            self.db.execute("INSERT OR REPLACE INTO stage_tempos VALUES (?,?,?)",
                            (self.fingerprint,key,bpm))
        for key, bpm in p.mastered.items():
            self.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)", (self.fingerprint,key,bpm))
        self.db.commit()

    def _stop(self):
        if self.teaching is not None:
            self.teaching.stop()
        self.paused=False
        self.paused_at=0.0
        self.pause_context=None
        self._deferred_score_ack=None
        self.running=False
        self.auto=False
        self.preview_only=False
        self.count_in_beats=0
        self.next_at=0
        self.awaiting_score_revision=None
        self.pending_rewind=None
        self._rewind_requires_layout=False
        self.play_from_beat=0.0
        self.recorder=None
        self.pending_result=None
        self.feedback_marks=[]
        self.feedback_unmapped=0
        self.recovery_notice = None
        self.live_input.reset_attempt()
        self.retry_range=None
        self._guided_recovery_pending=False
        self._guided_return=None
        self.demo=None
        self._demo_audio=None
        self._demo_score_ready=False
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
        p = self.plan
        p.select(step.exercise_index)
        p.hand_index = p.hands.index(step.hand)
        p.variant_index = next(i for i, variant in enumerate(p.variants) if variant.level == step.level)
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
            now=time.monotonic(), connected=self._piano_connected())
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing a short idea to learn"
        self.next_action = (f"Learn bars {self.display_phrase().first_bar}-{self.display_phrase().last_bar} "
                            "at your own pace, then retry the rhythm.")
        self._save()

    def _guided_marks(self, snapshot: dict) -> list[dict]:
        if (self.plan is None or self._layout_revision != self.score_revision
                or self._layout_cache is None):
            return []
        source = {f"{self.plan.identity}:{index}": note for index, note in
                  zip(self.plan.active_variant.source_indices, self.plan.active_variant.notes)}
        phrase = self.display_phrase()
        layout = self._layout_cache.layout
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

    def _prepare_listen(self):
        if self.plan is None:
            raise ValueError("Open a piece first")
        from .demo import DemoAudioCache
        self._stop()
        # Listen's WAV is rendered from the beginning of the active phrase.
        # Reset a previous seek/recovery location so the moving notation
        # also starts at the first note of that exact same phrase.
        self.play_from_beat = 0.0
        self.mode = "listen"
        self.teaching = None
        self.guided_range = None
        self.score_revision += 1
        self.awaiting_score_revision = self.score_revision
        self.feedback = "Preparing an audible example"
        self.next_action = "Listen to the notes, then choose Learn or Practice."
        if self._demo_cache is None:
            self._demo_cache = DemoAudioCache(self._data_dir / "demo-audio")
        variant, bpm = self.plan.active_variant, self.plan.bpm
        audio_end = max(variant.phrase.end, max((note.end for note in variant.notes), default=variant.phrase.end))
        token = uuid.uuid4().hex
        self.demo = {"token": token, "url": "", "audio_available": False,
                     "instrument": "Preparing piano audio",
                     "duration_seconds": (audio_end-variant.phrase.start)*60/bpm, "ready": False,
                     "stage_key": self.plan.identity,
                     "source_ids": [f"{self.plan.identity}:{index}"
                                    for index in variant.source_indices],
                     "canonical_source_ids": [source_note_id(note, index)
                                              for index, note in enumerate(variant.notes)]}
        revision, cache = self.score_revision, self._demo_cache
        # Waveform synthesis never holds the transport/MIDI lock. Immutable
        # inputs and the token+revision guard make Stop/navigation authoritative
        # even when an obsolete render finishes much later.
        def render():
            try:
                audio = cache.render(variant, bpm)
            except Exception as exc:
                with self.lock:
                    if self.demo is not None and self.demo["token"] == token and self.score_revision == revision:
                        self.awaiting_score_revision = None
                        self.feedback = f"Listen audio could not be prepared: {exc}"
                        self.next_action = self.feedback
                        self.demo["error"] = self.feedback
                return
            with self.lock:
                if self.demo is not None and self.demo["token"] == token and self.score_revision == revision:
                    self._demo_audio = audio
                    self.demo.update(url=f"/demo.wav?token={token}", audio_available=True,
                                     duration_seconds=audio.duration_seconds,
                                     instrument=audio.instrument,
                                     sampled=audio.instrument != "Basic synthesized piano")
        self._demo_thread = threading.Thread(target=render, name="piano-demo-render", daemon=True)
        self._demo_thread.start()

    def demo_audio(self, token: str) -> Path:
        with self.lock:
            if self.demo is None or token != self.demo["token"] or self._demo_audio is None:
                raise ValueError("This audio example is no longer current")
            return self._demo_audio.path

    def _start_listen_if_ready(self):
        if (self.mode != "listen" or self.demo is None or self.paused or self.running
                or self.awaiting_score_revision != self.score_revision
                or self._demo_audio is None or not self._demo_score_ready or not self.demo["ready"]):
            return
        self.awaiting_score_revision = None
        self.transport_id += 1
        self.running = True
        # Listen also needs a real, visible lead-in. Starting the transport
        # immediately at zero allowed HTTP/audio buffer latency to skip the
        # first piano attack. The PCM remains untrimmed and begins at beat 0.
        phrase = self.plan.active_phrase
        grid = phrase_grid(phrase, self.plan.piece.bar_boundaries)
        self.count_in_bar_beats = grid[1] - grid[0]
        meter = next(((num, den) for beat, num, den in
            sorted(self.plan.piece.time_signatures, reverse=True)
            if beat <= phrase.start + 1e-7), None)
        # A 1/8 pickup belongs in the score but makes an unusably short
        # count-in. Use the next complete measure solely for preparation.
        meter = preparation_meter(
            meter, self.plan.piece.time_signatures, phrase.start)
        self.count_in_meter = list(meter) if meter is not None else [
            max(1, round(self.count_in_bar_beats)), 4]
        if meter is not None:
            self.count_in_bar_beats = meter[0] * 4 / meter[1]
        self.count_in_beats = lead_in_beats(self.count_in_bar_beats, self.plan.bpm)
        self.run_at = time.monotonic() + self.count_in_beats * 60 / self.plan.bpm
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
        """Review real scored attacks by source measure, including chord pitches.

        Every recommended retry corresponds to an existing two-bar source
        interval. No independent note judgement or synthetic timing is used.
        """
        grid = phrase_grid(phrase, self.plan.piece.bar_boundaries)
        weaknesses = []
        sections = []
        for start, end in two_bar_chunks(grid):
            issues = []
            counts = {status: 0 for status in
                      ("missed", "wrong", "early", "late", "short", "long", "extra")}
            for entry in result.notes:
                local = entry.note.start - phrase.start
                if entry.status == "correct" or not start-1e-7 <= local < end-1e-7:
                    continue
                counts[entry.status] += 1
                issue = {"bar": bar_number_at(grid, local, phrase.first_bar),
                         "status": entry.status,
                         "pitch": entry.note.pitch,
                         "name": note_name(entry.note.pitch),
                         "hand": entry.note.hand,
                         "source_id": entry.note.source_id}
                if entry.played_pitch is not None:
                    issue["played_pitch"] = entry.played_pitch
                    issue["played_name"] = note_name(entry.played_pitch)
                issues.append(issue)
            for note in result.unmatched_played:
                local = self.play_from_beat + note.onset * self.plan.bpm / 60
                if start-1e-7 <= local < end-1e-7:
                    counts["extra"] += 1
                    issues.append({"bar": bar_number_at(grid, local, phrase.first_bar),
                                   "status": "extra", "pitch": note.pitch,
                                   "name": note_name(note.pitch), "hand": "unknown"})
            errors = sum(counts.values())
            if not errors:
                continue
            first = next(i for i, beat in enumerate(grid) if abs(beat-start) < 1e-6)
            last = next(i for i, beat in enumerate(grid) if abs(beat-end) < 1e-6)
            section = {"first_bar": phrase.first_bar+first, "last_bar": phrase.first_bar+last-1,
                       "start_beat": start, "end_beat": end, "errors": errors,
                       "counts": counts,
                       "issues": sorted(issues, key=lambda issue:
                           (issue["bar"], issue["pitch"], issue["status"]))}
            weaknesses.append({key: section[key] for key in
                               ("first_bar", "last_bar", "start_beat", "end_beat", "errors")})
            sections.append(section)
        ordering = lambda entry: (-entry["errors"], entry["first_bar"])
        timing = {status: sum(entry.status == status for entry in result.notes)
                  for status in ("early", "late", "short", "long")}
        return {"accuracy_percent": round(100*result.correct/max(1, len(result.notes)), 1),
                "correct": result.correct, "total": len(result.notes), **timing, "timing": timing,
                "missed_pitches": sorted({entry.note.pitch for entry in result.notes if entry.status == "missed"}),
                "missed": sum(entry.status == "missed" for entry in result.notes),
                "wrong": sum(entry.status == "wrong" for entry in result.notes),
                "extra_notes": result.extra_notes,
                "sections": sorted(sections, key=ordering),
                "weakest_bars": sorted(weaknesses, key=ordering)}

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
        if (p.identity, p.bpm) != before:
            self.score_revision += 1
        self._save()
        return message

    def start(self, *, from_beat: float | None = None, mode: str = "practice"):
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
            self.preview_only = not self._piano_connected()
            phrase=self.plan.active_phrase
            position = self.open_from_beat if from_beat is None else from_beat
            self.play_from_beat=max(0.0,min(float(position),phrase.end-phrase.start-1e-6))
            self.paused=False
            self.paused_at=0.0
            self.transport_id+=1
            self.live_input.reset_attempt()
            self.running=True
            self.auto=mode == "practice" and not self.preview_only
            self.next_at=0
            self.awaiting_score_revision=None
            self.pending_result=None
            self.pending_rewind=None
            self._rewind_requires_layout=False
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
            self.count_in_beats = lead_in_beats(self.count_in_bar_beats, self.plan.bpm)
            self.next_boundary_beat=next_chunk_end(grid,self.play_from_beat)
            self.run_at=time.monotonic()+self.count_in_beats*60/self.plan.bpm
            self.feedback="Count in, then play"
            self.next_action = ("Watch the moving score; connect a piano for feedback." if self.preview_only
                else f"Play from bar {bar_number_at(grid,self.play_from_beat,phrase.first_bar)} at {self.plan.bpm} BPM.")

    def control(self, action: str, **kwargs) -> None:
        with self.lock:
            # Explicit navigation, Stop and Restart abandon the current
            # attempt. Only the timed feedback lifecycle commits assessment.
            # Otherwise Stop during feedback could accidentally earn mastery.
            if action == "score_ready":
                revision = int(kwargs.get("revision", -1))
                # Ignore delayed PNG acknowledgements from older passages.
                if self.awaiting_score_revision == revision and revision == self.score_revision:
                    if self.paused:
                        self._deferred_score_ack = revision
                        return
                    if self.mode == "listen":
                        self._demo_score_ready = True
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
                if (self.mode == "listen" and self.demo is not None
                        and self.demo["audio_available"]
                        and kwargs.get("token") == self.demo["token"]
                        and int(kwargs.get("revision", -1)) == self.score_revision):
                    self.demo["ready"] = True
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
                # A requested measure can be silent even inside a consolidated
                # course section. Start at the next source measure with a real
                # attack, rather than opening an empty teaching fragment.
                next_attacks = [note.start for note in plan.piece.notes
                                if note.start >= plan.piece.bar_boundaries[bar-1]-1e-7]
                if not next_attacks:
                    raise ValueError("No playable notes at or after that measure")
                playable_bar = bar_number_at(plan.piece.bar_boundaries,
                                             min(next_attacks), 1)
                bar = max(bar, playable_bar)
                # Find the smallest course 'learn' section containing that
                # measure; the original source grid controls all positions.
                candidates = [(i, ex) for i, ex in enumerate(plan.exercises)
                              if ex.kind == "learn" and ex.phrase.first_bar <= bar <= ex.phrase.last_bar]
                if not candidates:
                    candidates = [(i, ex) for i, ex in enumerate(plan.exercises)
                                  if ex.kind == "learn" and ex.phrase.first_bar > bar]
                if not candidates:
                    raise ValueError("No playable notes at or after that measure")
                index, section = min(candidates, key=lambda item:
                    (item[1].phrase.first_bar if item[1].phrase.first_bar > bar else bar,
                     item[1].phrase.last_bar-item[1].phrase.first_bar))
                self._stop()
                self._reset_trouble()
                plan.select(index)
                self.course_guided = requested_mode == "learn"
                selected_bar = max(bar, section.phrase.first_bar)
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
                if self.mode == "listen":
                    self._prepare_listen()
                    return
                if self.mode == "learn":
                    self.control("practice")
                    return
                if (self.plan is not None and self._layout_cache is not None
                        and self._layout_bpm != self.plan.bpm):
                    # Restart can interrupt slower-tempo feedback before its
                    # scheduled retry. Render that spacing before its clock.
                    self._stop()
                    self.score_revision += 1
                    self.awaiting_score_revision = self.score_revision
                    self.feedback = "Preparing sheet music"
                    return
                self.start(mode="perform" if self.mode == "perform" else "practice")
                return
            if action == "pause":
                if self.paused:
                    raise ValueError("Cannot pause an exercise that is already paused")
                context = self._phase(time.monotonic())
                if context not in ("playing", "count_in", "feedback", "recovering", "loading", "guided_wait"):
                    raise ValueError("Cannot pause unless an exercise is playing or preparing")
                self.pause_context = context
                self.paused_at = time.monotonic()
                if self.mode == "learn" and self.teaching is not None:
                    self.teaching.pause(now=time.monotonic())
                    self.paused = True
                    return
                self.paused = True
                return
            if action == "resume":
                if not self.paused:
                    raise ValueError("Cannot resume unless an exercise is paused")
                duration = time.monotonic() - self.paused_at
                if self.mode == "learn" and self.teaching is not None:
                    self.teaching.resume(now=time.monotonic())
                    self.paused = False
                elif self.running:
                    # MIDI timestamps and the visual clock share this origin.
                    self.run_at += duration
                if self.next_at:
                    self.next_at += duration
                self.paused_at = 0.0
                self.paused = False
                self.pause_context = None
                if self.running:
                    self.feedback = "Count in" if time.monotonic() < self.run_at else "Playing"
                if self._deferred_score_ack is not None:
                    revision = self._deferred_score_ack
                    self._deferred_score_ack = None
                    self.control("score_ready", revision=revision)
                self._start_listen_if_ready()
                return
            p=self.plan
            if not p:
                raise ValueError("Open a piece first")
            was_guided = self.mode == "learn"
            guided_start = self.guided_range[0] if self.guided_range is not None else 0.0
            guided_return = self._guided_return
            guided_retry_range = self.retry_range
            self._stop()
            self._reset_trouble()
            if action == "next":
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
            else:
                raise ValueError(f"Unsupported action: {action}")
            self.score_revision+=1
            self.feedback="Ready"
            self.next_action="Start when you are ready."
            if was_guided:
                if action in ("tempo", "tempo_up"):
                    recovery = guided_return is not None and guided_return[0] == p.identity
                    if recovery:
                        self.retry_range = guided_retry_range
                    self._begin_learn(from_beat=guided_start, bump_revision=False, recovery=recovery)
                elif self.course_guided:
                    self._begin_course_stage(bump_revision=False, explicit_learn=action == "hand")
                else:
                    self._begin_learn(bump_revision=False)
            self._save()

    def _update(self):
        # State polling is frequent, so enumerate ALSA inputs only once per
        # interval. This works even if the USB device vanishes without the
        # driver marking the existing port object as closed.
        if self.midi_port is not None and getattr(self.midi_port, "closed", False):
            self._midi_lost()
        now = time.monotonic()
        if (self.enable_midi and now >= self._midi_next_scan_at and (
                self.midi_device or self.library.settings.get("midi_device"))):
            self._midi_next_scan_at = now + self.MIDI_SCAN_SECONDS
            try:
                self.ports()
            except RuntimeError:
                # Preserve readable feedback; a temporary ALSA discovery
                # error must not turn the entire /state endpoint into a 400.
                pass
        if not self.plan:
            return
        now=time.monotonic()
        if self.mode == "learn" and self.teaching is not None:
            self.teaching.set_connected(self._piano_connected(), now=now)
            self.teaching.tick(now=now)
            self._save_guided_preparation()
            return
        if self.paused:
            return
        if self.mode == "listen":
            if self.running and self.demo is not None and now >= self.run_at+self.demo["duration_seconds"]:
                self.running = False
                self.feedback = "Example complete"
                self.next_action = "Choose Learn to find the notes, or Practice to play the rhythm."
            return
        if self.pending_result is not None:
            if self.auto and self.next_at and now >= self.next_at:
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
                        self.start()
                else:
                    self.next_at=0
                    self.auto=False
                    self.feedback = message or self.feedback
            return
        if self.awaiting_score_revision is not None:
            return
        if self.pending_rewind is not None:
            if now >= self.next_at:
                if self._guided_recovery_pending:
                    self._begin_learn(from_beat=self.pending_rewind, recovery=True)
                elif self._rewind_requires_layout:
                    self.score_revision += 1
                    self.awaiting_score_revision = self.score_revision
                    self._rewind_requires_layout = False
                    self.next_at = 0
                    self.feedback = "Preparing retry"
                else:
                    self.start(from_beat=self.pending_rewind)
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
                self._rewind_requires_layout = self.plan.bpm != before
                self._save()
                self.pending_rewind=decision.restart_beat
                self.recovery_notice = {
                    "kind": "slowdown", "errors": decision.errors,
                    "missed": decision.missed, "wrong": decision.wrong,
                    "from_bpm": before, "to_bpm": self.plan.bpm,
                    "first_bar": bar_number_at(grid, decision.restart_beat, phrase.first_bar),
                    "last_bar": bar_number_at(grid, max(decision.restart_beat, decision.end_beat-1e-6), phrase.first_bar),
                    "expires_at": now + 9.0,
                }
                key = (self.plan.identity, decision.restart_beat, decision.end_beat)
                self._trouble_count = self._trouble_count + 1 if key == self._trouble_key else 1
                self._trouble_key = key
                self._guided_recovery_pending = self._trouble_count >= SETTINGS.guided_recovery_after_failures
                self.retry_range = {
                    "first_bar": bar_number_at(grid, decision.restart_beat, phrase.first_bar),
                    "last_bar": phrase.first_bar + next(i for i, beat in enumerate(grid)
                        if abs(beat-decision.end_beat) < 1e-6)-1,
                    "start_beat": decision.restart_beat, "end_beat": decision.end_beat}
                self.running=False
                self.recorder=None
                self.next_at=now+self.feedback_seconds
                self.feedback=(f"{decision.errors} wrong or missed notes - retrying from "
                               f"measure {bar_number_at(grid,decision.restart_beat,phrase.first_bar)} "
                               f"at {self.plan.bpm} BPM")
                bars = f"{self.retry_range['first_bar']}-{self.retry_range['last_bar']}"
                self.next_action = (f"Learn bars {bars} slowly, then retry the rhythm." if self._guided_recovery_pending
                    else f"Retry bars {bars} at {self.plan.bpm} BPM.")
                return
            previous_boundary=self.next_boundary_beat
            self.next_boundary_beat=next_chunk_end(grid,previous_boundary)
            if self.next_boundary_beat <= previous_boundary + 1e-7:
                self.next_boundary_beat=0.0
        ending = (min(total_beats, self.review_end_beat)
                  if self.review_end_beat is not None else total_beats)
        duration=(ending-self.play_from_beat)*60/self.plan.bpm
        if now < self.run_at+duration+0.20:
            return
        if self.preview_only:
            # Never grade an empty MIDI recording or retry forever simply
            # because the user's piano has not been connected yet.
            self._stop()
            self.feedback = "Timing preview complete - connect a USB MIDI piano for scoring"
            self.next_action = "Connect your piano to learn and receive feedback."
            return
        active_phrase=Phrase(phrase.number,phrase.first_bar,phrase.last_bar,
            phrase.start+self.play_from_beat,phrase.start+ending,
            tuple(n for n in phrase.notes
                  if phrase.start+self.play_from_beat-1e-7 <= n.start < phrase.start+ending-1e-7))
        result=evaluate(active_phrase,self.plan.hand,self.plan.bpm,self.recorder.presses if self.recorder else [])
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
        if self.mode == "perform":
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
            return
        if self.review_end_beat is not None:
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
            return
        if self.play_from_beat>1e-6:
            # A clean *partial* recovery cannot confer full passage mastery.
            self.pending_rewind=0.0
            self.feedback = "Selected section finished · " + result.summary
            self.next_action = "Next: play the whole passage from its beginning to earn mastery."
            self.retry_range = None
            self.next_at=now+self.feedback_seconds
            return
        self.pending_result=result
        if not result.clean:
            # Failure breaks consecutive clean takes immediately, even if
            # Start/Restart/Stop discards this feedback before its commit.
            # Success and mastery still wait until the feedback interval ends.
            self.plan.streak = 0
            self._save()
            if self.is_builtin_warmup:
                self.auto = False  # Keep the beginner-study review available.
        self.next_action=next_full_attempt(self.plan, result)
        self.next_at=now+self.feedback_seconds if self.auto else 0

    def _phase(self, now: float) -> str:
        if self.paused:
            return "paused"
        if self.mode == "learn" and self.teaching is not None:
            return "loading" if self.awaiting_score_revision is not None else self.teaching.snapshot(now=now)["phase"]
        if self.running:
            return "count_in" if now < self.run_at else "playing"
        if self.mode == "perform" and self.performance_summary is not None:
            return "performance_complete"
        if self.mode == "practice" and self.review_session_complete and self.performance_summary is not None:
            return "review"
        return ("feedback" if self.pending_result is not None else "loading" if self.awaiting_score_revision is not None
                else "recovering" if self.pending_rewind is not None else "ready")

    def _live_feedback(self, elapsed_seconds: float) -> list[dict]:
        """Live notehead marks: each missing chord pitch is handled separately.

        Slow held notes do not delay missing-pitch feedback until their
        release, and notes inside the allowable late-onset window are never
        prematurely marked wrong. Assessment and playback clocks are unchanged.
        """
        p=self.plan
        if (p is None or self.preview_only or not self.running
                or self._layout_revision != self.score_revision or self._layout_cache is None):
            return []
        phrase=p.active_phrase
        total=phrase.end-phrase.start
        if total<=0 or elapsed_seconds<0:
            return []
        per_bar=total/max(1,phrase.last_bar-phrase.first_bar+1)
        now_beat=self.play_from_beat+elapsed_seconds*p.bpm/60
        played=self.recorder.presses if self.recorder else []
        settled=settled_assessment(phrase,p.hand,p.bpm,played,
                                  from_beat=self.play_from_beat,
                                  until_beat=now_beat,beats_per_bar=per_bar)
        grid=phrase_grid(phrase,p.piece.bar_boundaries)
        active_bar=max(index for index, bar_beat in enumerate(grid)
                       if bar_beat <= now_beat + 1e-7)
        window_start=grid[max(0, active_bar-2)]
        missed=expired_attack_misses(phrase,p.hand,p.bpm,played,
                                     from_beat=self.play_from_beat,
                                     until_beat=now_beat,
                                     window_start_beat=window_start)
        if settled is None and missed is None:
            return []
        try:
            layout=self._layout_cache.layout
            marks=[]
            if settled is not None:
                marks=project_assessment(settled,phrase,p.bpm,layout,
                                         played_from_beat=self.play_from_beat)["marks"]
            if missed is not None:
                existing={m.get("note_id") for m in marks}
                new=project_assessment(missed,phrase,p.bpm,layout,
                                       played_from_beat=self.play_from_beat)["marks"]
                marks.extend(m for m in new if m.get("note_id") not in existing)
            return marks
        except (ValueError, RuntimeError, KeyError):
            return []

    def state(self) -> dict:
        with self.lock:
            self._update()
            p=self.plan
            seek_grid = self._seek_grid()
            input_activity = {
                "clock_sampled_at_ms": time.monotonic() * 1000.0,
                "learner": self._learner_snapshot() if p is not None else None,
                "placement_available": (not self.is_builtin_warmup and placement_candidate(p) is not None) if p is not None else False,
                "skip_available": (not self.is_builtin_warmup and p.lesson_step_number < len(p.lesson_steps)) if p is not None else False,
                "seek_available": self.paused and seek_grid is not None,
                "seek_range": ({"first_bar": p.active_phrase.first_bar, "last_bar": p.active_phrase.last_bar}
                               if seek_grid is not None else None),
                "next_action": self.next_action,
                "transition_in_seconds": (max(0.0, self.next_at-(self.paused_at if self.paused else time.monotonic()))
                    if self.next_at and (self.pending_result is not None or self.pending_rewind is not None) else None),
                "retry_range": self.retry_range,
                "recovery_notice": ({key: value for key, value in self.recovery_notice.items()
                                     if key != "expires_at"}
                                    if self.recovery_notice is not None and
                                    time.monotonic() < self.recovery_notice["expires_at"] else None),
                "guided_recovery": self._guided_recovery_pending or self._guided_return is not None,
                "pause_context": self.pause_context,
                "demo": dict(self.demo) if self.demo is not None else None,
                "performance_summary": self.performance_summary,
                "review_range": self.retry_range if self.review_end_beat is not None else None,
                "midi_input_count": self.midi_input_count,
                "midi_input_note": self.midi_input_note,
                "midi_input_age": (max(0.0, time.monotonic() - self.midi_input_at)
                                   if self.midi_input_at is not None else None),
                "metronome": self.library.settings["metronome"],
                "hints_enabled": self.persistent_hints,
            }
            visual_now = self.paused_at if self.paused else time.monotonic()
            visual_beat = self.play_from_beat
            if self.running and visual_now >= self.run_at and p is not None:
                visual_beat += (visual_now - self.run_at) * p.bpm / 60.0
            input_activity.update(self.live_input.snapshot(
                now=time.monotonic(),
                phrase=p.active_phrase if p is not None else None,
                hand=p.hand if p is not None else "both",
                beat=visual_beat,
                playing=(p is not None and self.mode in ("practice", "perform")
                         and (self.running or self._phase(visual_now) == "ready")),
            ))
            if not p:
                return {**input_activity,"mode":self.mode,"teaching":None,"loaded":False,"running":False,"paused":False,"transport_id":self.transport_id,
                        "clock_beat":0.0,"feedback":self.feedback,"device":self.midi_device,"revision":self.score_revision}
            ex=p.exercise
            variant=p.active_variant
            hand_stages = []
            if ex.kind in ("learn", "warmup"):
                for hand in ("right", "left", "both"):
                    steps = [step for step in p.lesson_steps
                             if step.exercise_index == p.index and step.hand == hand]
                    if not steps:
                        continue
                    finished = all(step.key in p.mastered for step in steps)
                    available = hand in p.hands
                    locked = (self.is_builtin_warmup and hand != "right"
                              and not all(previous["complete"] for previous in hand_stages))
                    hand_stages.append({"hand": hand, "active": hand == p.hand,
                                        "complete": finished, "locked": locked,
                                        "available": available})
            sampled_at = time.monotonic()
            now=self.paused_at if self.paused else sampled_at
            total_beats = ex.phrase.end-ex.phrase.start
            practice_end = min(total_beats, self.review_end_beat) if self.review_end_beat is not None else total_beats
            start_beat = self.play_from_beat if self.review_end_beat is not None else 0.0
            seconds=(practice_end-start_beat)*60/p.bpm
            elapsed=now-self.run_at
            exercise_beat=self.play_from_beat+max(0.0,elapsed*p.bpm/60)
            progress=min(1.0,max(0.0,
                (exercise_beat-start_beat)/max(1e-6, practice_end-start_beat))) if self.running else 0.0
            phase=self._phase(now)
            live_marks=self._live_feedback(elapsed) if phase == "playing" else []
            # Also publish the recent error in a stable HUD field. Engraved
            # marks travel with the moving score and can leave the viewport
            # before the student notices them.
            live_errors = [mark for mark in live_marks
                           if mark.get("status") in ("missed", "wrong")]
            latest_error = max(live_errors, key=lambda mark: (mark.get("beat", -1), mark.get("pitch", -1)),
                               default=None)
            live_note_feedback = ({
                "status": latest_error["status"],
                "pitch": latest_error["pitch"],
                "name": note_name(int(latest_error["pitch"])),
                "count": len(live_errors),
                "source_id": latest_error.get("source_id", ""),
            } if latest_error is not None else None)
            result = {**input_activity,"mode":self.mode,"teaching":None,"loaded":True,"title":p.piece.title,"kind":ex.kind,
                    "clock_sampled_at_ms": sampled_at * 1000.0,
                    "first_bar":ex.phrase.first_bar,"last_bar":ex.phrase.last_bar,
                    "current_bar":bar_number_at(
                        phrase_grid(p.active_phrase, p.piece.bar_boundaries),
                        exercise_beat if self.running else self.play_from_beat,
                        ex.phrase.first_bar),
                    "exercise":p.index+1,"exercise_count":len(p.exercises),
                    "lesson_level":variant.level,"lesson_level_number":p.variant_index+1,
                    "lesson_level_count":len(p.variants),"required_notes":len(variant.notes),
                    "warmup":self.is_builtin_warmup,
                    "piece_last_bar":len(p.piece.bar_boundaries)-1,
                    "selected_start_bar": (bar_number_at(
                        phrase_grid(p.active_phrase, p.piece.bar_boundaries),
                        self.open_from_beat, p.active_phrase.first_bar)),
                    "hand_stages":hand_stages,
                    "measure_boundaries":list(phrase_grid(
                        p.active_phrase, p.piece.bar_boundaries)),
                    "import_warnings": list(p.piece.import_warnings),
                    "lesson_step":p.lesson_step_number,"lesson_steps":len(p.lesson_steps),
                    "lesson_steps_mastered":p.lesson_steps_mastered,
                    "hand":p.hand,"hands":list(p.hands),"bpm":p.bpm,"original_bpm":p.piece.bpm,"target_bpm":p.target_bpm,
                    "streak":p.streak,"clean_runs_required":SETTINGS.clean_runs_to_master,
                    "manual_tempo_step_bpm":SETTINGS.manual_tempo_step_bpm,
                    "minimum_bpm":SETTINGS.minimum_bpm,
                    "maximum_bpm":SETTINGS.maximum_bpm,
                    "can_increase_tempo":p.bpm < p.target_bpm,
                    "mastered":len(p.mastered),"phase":phase,
                    "auto":self.auto,
                    "take_result": ({"clean": bool(self.pending_result.clean),
                                     "correct": self.pending_result.correct,
                                     "total": len(self.pending_result.notes)}
                                    if self.mode == "practice" and self.pending_result is not None
                                    else None),
                    "countdown":max(0,-elapsed) if self.running else 0,
                    "lead_in_bars":1,"play_from_beat":self.play_from_beat,
                    "recovery_beat":self.pending_rewind,
                    "clock_beat":elapsed*p.bpm/60 if self.running else 0.0,
                    "paused":self.paused,"transport_id":self.transport_id,
                    "awaiting_score_revision":self.awaiting_score_revision,
                    "count_in_beats":self.count_in_beats if self.running else 0,
                    "count_in_bar_beats":self.count_in_bar_beats,
                    "count_in_meter":self.count_in_meter,
                    "midi_notes":len(self.recorder.presses) if self.recorder is not None else 0,
                    "preview_only":self.preview_only,
                    "progress":progress,"duration":seconds,"beat":exercise_beat if self.running else 0.0,
                    "duration_beats":ex.phrase.end - ex.phrase.start,"running":self.running,
                    "device":self.midi_device,"feedback":"Paused" if self.paused else self.feedback,"revision":self.score_revision,
                    "feedback_marks":self.feedback_marks if (self.pause_context if self.paused else phase) in ("feedback", "recovering", "performance_complete", "review") else live_marks,
                    "live_note_feedback": live_note_feedback,
                    "scoring_available": (not self.preview_only and self._piano_connected()
                                          and self.mode in ("practice", "perform")),
                    "feedback_unmapped":self.feedback_unmapped if (self.pause_context if self.paused else phase) in ("feedback", "recovering", "performance_complete") else 0}
            if self.mode == "learn" and self.teaching is not None:
                teaching = self.teaching.snapshot(now=time.monotonic())
                phrase = self.display_phrase()
                teaching["fragment"] = {"first_bar": phrase.first_bar, "last_bar": phrase.last_bar,
                    "start_beat": self.guided_range[0], "end_beat": self.guided_range[1]}
                teaching["session_id"] = self.transport_id
                teaching["has_more_units"] = (result["learner"]["next_unit"] is not None
                                               and self._guided_return is None)
                phase = self._phase(now)
                feedback = str(teaching.get("feedback", "Find the highlighted notes at your own pace."))
                if phase == "loading":
                    feedback = "Preparing a short idea to learn"
                elif phase == "disconnected":
                    feedback = "No piano connected — timed preview only. Connect your piano in Settings to learn notes."
                    result["next_action"] = "Connect your piano in Settings to learn notes."
                elif phase == "guided_complete":
                    feedback = "You found every note. Ready to add rhythm?"
                    result["next_action"] = "Retry rhythm from these bars." if self._guided_return else "Ready to add rhythm? Choose Practice."
                    if teaching["has_more_units"]:
                        feedback = "You found this idea. Continue with the next short idea."
                        result["next_action"] = "Choose Next idea to learn the next part of the passage."
                elif phase == "paused":
                    feedback = "Paused — resume when you are ready."
                elif phase == "guided_wait":
                    labels = list(dict.fromkeys(n["label"] for n in teaching.get("expected_notes", [])))
                    keys = " + ".join(labels)
                    together = " together" if len(labels) > 1 else ""
                    feedback = f"Play {keys}{together}. Take your time."
                    if teaching.get("hint_reason") == "wrong_note":
                        feedback = f"Find {keys} on the keyboard below, then try again."
                    elif teaching.get("target_index", 0) > 0:
                        feedback = "Good. Next: " + keys + together + "."
                result.update(teaching=teaching, phase=phase, running=False,
                    paused=phase == "paused", clock_beat=0.0, countdown=0.0,
                    first_bar=phrase.first_bar, last_bar=phrase.last_bar,
                    required_notes=len(phrase.notes), duration_beats=phrase.end-phrase.start,
                    progress=teaching.get("target_index", 0)/max(1, teaching.get("target_count", 0)),
                    feedback=feedback, feedback_marks=self._guided_marks(teaching), feedback_unmapped=0)
            return result

    def semantic_score(self) -> dict:
        """Phase A: source-accurate notation contract, without Verovio/SVG.

        Built from the same immutable active Phrase used for MIDI grading.
        It does NOT depend on the legacy engraving cache or selected BPM.
        """
        with self.lock:
            if self.plan is None:
                raise ValueError("No piece loaded")
            p = self.plan
            phrase = self.display_phrase()
            notation = build_lesson_score(
                phrase, boundaries=p.piece.bar_boundaries,
                time_signatures=p.piece.time_signatures,
                key_signatures=p.piece.key_signatures,
                clef_changes=p.piece.clef_changes,
                default_clefs=infer_piece_clefs(p.piece.notes),
                barlines=p.piece.barlines)
            return build_score_model(
                notation, boundaries=p.piece.bar_boundaries,
                hand=p.hand, revision=self.score_revision)

    def engraving(self) -> EngravedScore:
        with self.lock:
            if not self.plan:
                raise ValueError("No piece loaded")
            p=self.plan
            # Keep every feedback mark on the exact score just performed.
            # The retry revision is queued only once its reading time ends.
            if (self.pending_rewind is not None and self._rewind_requires_layout
                    and self._layout_revision == self.score_revision and self._layout_cache is not None):
                return self._layout_cache
            if (self._layout_revision != self.score_revision or self._layout_cache is None
                    or self._layout_bpm != p.bpm):
                phrase=self.display_phrase()
                notation=build_lesson_score(phrase, boundaries=p.piece.bar_boundaries,
                                            time_signatures=p.piece.time_signatures,
                                            key_signatures=p.piece.key_signatures,
                                            clef_changes=p.piece.clef_changes,
                                            default_clefs=infer_piece_clefs(p.piece.notes),
                                            barlines=p.piece.barlines)
                # Short lessons are freshly engraved as a continuous system.
                # This avoids raster-copying printed Verovio lines together.
                # Large works retain paginated rendering to bound GPU memory.
                compact_exercise = (
                    phrase.last_bar - phrase.first_bar + 1 <= 12
                    and phrase.end - phrase.start <= 48
                )
                # Cache by immutable source bytes, curriculum stage, rendered
                # phrase, hand, BPM and engraver version, not ephemeral revision.
                # Never share one stage's PNG/geometry with another.
                self._layout_cache_key = self.preprocessing.key(
                    "engraving", self.fingerprint, p.identity,
                    phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
                    p.hand, p.bpm, compact_exercise,
                    tuple((n.source_id, n.start, n.end, n.pitch, n.hand)
                          for n in phrase.notes))
                cached = self.preprocessing.read_json("engraving", self._layout_cache_key)
                layout = None
                if cached is not None:
                    try:
                        pages = cached["pages"]
                        geometry = cached["layout"]
                        if (not isinstance(pages, list) or not pages or
                                not all(isinstance(page, str) for page in pages) or
                                not isinstance(geometry, dict)):
                            raise ValueError("Invalid preprocessed score")
                        candidate = EngravedScore(tuple(pages), geometry)
                        require_lesson_alignment(phrase, candidate.layout, p.hand)
                        layout = candidate
                        print("PREPROCESS_ENGRAVING_CACHE_HIT:",
                              phrase.first_bar, phrase.last_bar, p.bpm)
                    except (TypeError, ValueError, KeyError, AssertionError):
                        layout = None
                if layout is None:
                    layout = render_layout(notation,phrase.first_bar,phrase.last_bar,p.hand,
                                           total_beats=phrase.end - phrase.start, bpm=p.bpm,
                                           continuous=compact_exercise)
                    require_lesson_alignment(phrase, layout.layout, p.hand)
                    self.preprocessing.write_json("engraving", self._layout_cache_key,
                                                  {"pages": list(layout.pages),
                                                   "layout": layout.layout})
                    self.preprocessing.prune()
                self._layout_cache = layout
                self._page_png.clear()
                self._layout_revision=self.score_revision
                self._layout_bpm=p.bpm
            return self._layout_cache

    def engraved(self, page: int = 0) -> str:
        score=self.engraving()
        if not 0 <= page < len(score.pages):
            raise ValueError("Invalid score page")
        return score.pages[page]

    def engraved_png(self, page: int = 0, *, width: int = 2000) -> bytes:
        # Source SVG and note geometry stay resolution-independent.
        # Godot requests an appropriately dense PNG for the actual staff
        # size; the default preserves compatibility with existing clients.
        if not 600 <= width <= 12000:
            raise ValueError("Invalid engraving image width")
        with self.lock:
            score = self.engraving()
            # Large PNGs are reserved for a single, freshly engraved
            # practice system. Multi-page scores keep their old safe cap.
            if width > 7200 and not bool(getattr(score, "layout", {}).get(
                    "continuous_score", False)):
                raise ValueError("Invalid engraving image width")
            if not 0 <= page < len(score.pages):
                raise ValueError("Invalid score page")
            key = (page, width)
            if key not in self._page_png:
                # Keep only one resolution per page in process memory.
                for cached in list(self._page_png):
                    if cached[0] == page:
                        del self._page_png[cached]
                png_key = (self.preprocessing.key("png", self._layout_cache_key,
                           page, width) if self._layout_cache_key else None)
                png = self.preprocessing.read_png(png_key) if png_key else None
                if png is None:
                    png = (rasterize_score(score.pages[page]) if width == 2000
                           else rasterize_score(score.pages[page], width=width))
                    if png_key:
                        self.preprocessing.write_png(png_key, png)
                else:
                    print("PREPROCESS_PNG_CACHE_HIT:", page, width)
                self._page_png[key] = png
            return self._page_png[key]

    def geometry(self, *, native_notes: bool = False) -> dict:
        """Prepare selected revision/hand in a stateless notation collaborator."""
        from .application.score_preparation import assemble_layout
        with self.lock:
            source_score = self.engraving()
            if not native_notes:
                return assemble_layout(source_score, revision=self.score_revision)
            if self.plan is None:
                raise ValueError("No piece loaded")
            p = self.plan
            phrase = self.display_phrase()
            notation = build_lesson_score(
                phrase, boundaries=p.piece.bar_boundaries,
                time_signatures=p.piece.time_signatures,
                key_signatures=p.piece.key_signatures,
                clef_changes=p.piece.clef_changes,
                default_clefs=infer_piece_clefs(p.piece.notes),
                barlines=p.piece.barlines)
            native_model = build_score_model(notation,
                boundaries=p.piece.bar_boundaries,
                hand=p.hand, revision=self.score_revision)
            return assemble_layout(source_score, native_notes=True,
                native_model=native_model, notation_xml=notation.musicxml,
                cache=self.preprocessing, cache_key=self._layout_cache_key or "",
                revision=self.score_revision)

    def lesson_overview(self) -> dict:
        """Full readable curriculum, with unique per-hand/per-level progress."""
        with self.lock:
            if self.plan is None:
                raise ValueError("Open a piece first")
            p = self.plan
            return {
                "trouble_spots": self._valid_trouble_spots(),
                "route_version": p.route_version,
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
