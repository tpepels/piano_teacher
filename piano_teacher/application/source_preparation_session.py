"""Atomic source preparation outside the live MIDI/transport lock.

This owner imports an exact MIDI source, starts independent fingering
inference while compiling its learning curriculum, and returns the candidate
for progress restoration and installation under the application lock. The same owner serializes source replacement and
fingering correction, validates their generation/original-note identity, and
returns an exact correction install effect. It retains no engine or live plan.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
import time
from threading import Lock

from ..learning import LearningPlan
from ..music import Note, Piece
from ..fingering.types import FingeringPlan


@dataclass(frozen=True, slots=True)
class PreparedSource:
    path: Path
    fingerprint: str
    plan: LearningPlan
    restore_progress: bool = True


@dataclass(frozen=True, slots=True)
class CorrectionIdentity:
    generation: int
    fingerprint: str
    notes: tuple[Note, ...]


@dataclass(frozen=True, slots=True)
class PreparedFingeringCorrection:
    identity: CorrectionIdentity
    fingering: FingeringPlan


@dataclass(frozen=True, slots=True)
class FingeringInstall:
    piece: Piece
    score_revision: int


_SOURCE_CHANGED = "The loaded piece changed; refresh the score before correcting fingering"


class SourcePreparationSession:
    def __init__(self, shutdown_requested=None):
        self._shutdown_requested = shutdown_requested
        self._cancelled = None
        self._source_mutation = Lock()
        self._generation = 0

    @contextmanager
    def source_mutation(self, cancelled=None):
        """Serialize full import/correction work outside the musical lock."""
        with self._source_mutation:
            self._cancelled = cancelled
            try:
                self.checkpoint()
                yield
            finally:
                self._cancelled = None

    def checkpoint(self):
        if self._shutdown_requested and self._shutdown_requested():
            raise ValueError("Source preparation cancelled during shutdown")
        if self._cancelled and self._cancelled():
            raise ValueError("Source preparation superseded")

    def source_installed(self) -> None:
        """Called under source_mutation and the short application state lock."""
        self._generation += 1

    def capture_correction(self, *, piece: Piece | None, fingerprint: str,
                           requested_fingerprint: str | None) -> CorrectionIdentity:
        """Capture immutable request identity under the application state lock."""
        if piece is None:
            raise ValueError("Open a piece before correcting fingering")
        if requested_fingerprint is not None and requested_fingerprint != fingerprint:
            raise ValueError(_SOURCE_CHANGED)
        return CorrectionIdentity(self._generation,fingerprint,piece.notes)

    def _require_current(self, identity: CorrectionIdentity, *,
                         piece: Piece | None, fingerprint: str) -> Piece:
        if (identity.generation != self._generation or piece is None
                or fingerprint != identity.fingerprint or piece.notes is not identity.notes):
            raise ValueError(_SOURCE_CHANGED)
        return piece

    def correct_fingering(self, identity: CorrectionIdentity, *,
                          piece: Piece | None, fingerprint: str,
                          source_id: str, finger: int | None,
                          fingering) -> PreparedFingeringCorrection:
        """Validate one serialized source-bound edit before durable inference.

        The caller supplies a state-locked Piece snapshot after entering
        source_mutation. Navigation may replace the live plan during inference;
        correction_install validates the current original source again.
        """
        piece = self._require_current(identity,piece=piece,fingerprint=fingerprint)
        if not isinstance(source_id,str) or not source_id:
            raise ValueError("Choose an original source note")
        if finger is not None and (type(finger) is not int or
                                   not 1 <= finger <= 5):
            raise ValueError(
                "Finger must be an integer from 1 to 5, or null to remove a correction")
        return PreparedFingeringCorrection(identity,
            fingering.correct(piece,fingerprint,source_id,finger))

    def correction_install(self, corrected: PreparedFingeringCorrection, *,
                           piece: Piece | None, fingerprint: str,
                           score_revision: int) -> FingeringInstall:
        """Return the exact new Piece/revision under the state lock.

        Rebase only fingering onto the current Piece, including after a lesson
        reset. The original note tuple must be the same object throughout.
        """
        current = self._require_current(corrected.identity,piece=piece,
                                        fingerprint=fingerprint)
        return FingeringInstall(replace(current,fingering_plan=corrected.fingering),
                                score_revision)

    def prepare(self, source: Path, *, preprocessing, fingering,
                diagnostics: bool = False) -> PreparedSource:
        checkpoint = time.perf_counter()
        fingerprint, piece = preprocessing.load_import(source, source.read_bytes())
        self.checkpoint()
        if diagnostics:
            now = time.perf_counter()
            print("SCORE_LOAD_STAGE: import",round((now-checkpoint)*1000,1),
                  "ms",source.name,flush=True)
            checkpoint = now

        # The isolated Python/ONNX fingering worker does not participate in
        # learning decisions. Both prepare from the same original source.
        def prepare_fingering():
            started = time.perf_counter()
            result = fingering.prepare(piece,fingerprint)
            return result,(time.perf_counter()-started)*1000.0

        with ThreadPoolExecutor(
                max_workers=1,thread_name_prefix="piano-fingering") as worker:
            predicted = worker.submit(prepare_fingering)
            started_course = time.perf_counter()
            candidate = LearningPlan(piece)
            course_ms = (time.perf_counter()-started_course)*1000.0
            fingering_plan,infer_ms = predicted.result()
            candidate.piece = replace(piece,fingering_plan=fingering_plan)
            if diagnostics:
                print("SCORE_LOAD_STAGE: fingering",round(infer_ms,1),
                      "ms status",fingering_plan.status,flush=True)
                print("SCORE_LOAD_STAGE: curriculum",round(course_ms,1),
                      "ms",candidate.lesson_generator.name,flush=True)
                print("SCORE_LOAD_STAGE: parallel_prepare",
                      round((time.perf_counter()-checkpoint)*1000,1),
                      "ms wall",source.name,flush=True)
        return PreparedSource(source,fingerprint,candidate)
