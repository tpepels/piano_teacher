"""Atomic source preparation outside the live MIDI/transport lock.

This owner imports an exact MIDI source, starts independent fingering
inference while compiling its learning curriculum, restores its saved
progress under the caller's short state lock, and publishes only a fully
prepared immutable result. It has no access to the PracticeEngine object
and cannot replace the current playing piece or its score revision.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
import hashlib
import time

from ..learning import LearningPlan


@dataclass(frozen=True, slots=True)
class PreparedSource:
    path: Path
    fingerprint: str
    plan: LearningPlan
    score: object


class SourcePreparationSession:
    def prepare(self, source: Path, *, warmup: bool, preprocessing, fingering,
                progress, fukuda_mistakes, library, state_lock, importer,
                plan_type=LearningPlan,
                diagnostics: bool = False) -> PreparedSource:
        checkpoint = time.perf_counter()
        fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        piece, score = preprocessing.load_import(
            source, fingerprint, importer=importer)
        if diagnostics:
            now = time.perf_counter()
            print("SCORE_LOAD_STAGE: import",round((now-checkpoint)*1000,1),
                  "ms",source.name,flush=True)
            checkpoint = now

        # The external Node/ONNX fingering worker does not participate in
        # learning decisions. Both prepare from the same original source.
        def prepare_fingering():
            started = time.perf_counter()
            result = fingering.prepare(piece,fingerprint)
            return result,(time.perf_counter()-started)*1000.0

        with ThreadPoolExecutor(
                max_workers=1,thread_name_prefix="piano-fingering") as worker:
            predicted = worker.submit(prepare_fingering)
            # Only the database-backed policy snapshot and restore use the
            # state lock; neither expensive worker waits under it.
            with state_lock:
                strategy = library.settings["exercise_strategy"]
                mistakes = fukuda_mistakes.problematic(fingerprint)
                evidence = fukuda_mistakes.evidence(fingerprint)
            started_course = time.perf_counter()
            candidate = plan_type(
                piece,warmup=warmup,exercise_strategy=strategy,
                fukuda_mistakes=mistakes,feedback=evidence)
            with state_lock:
                progress.restore(candidate,fingerprint)
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
        return PreparedSource(source,fingerprint,candidate,score)
