"""Capture musical inputs and authorize source-bound worker replies."""
from __future__ import annotations

from time import monotonic

from ..source_timing import selected_practice_timeline
from .score_ipc import BINDING_FIELDS, DEADLINE_SECONDS, document_bytes
from .score_process import ScoreCancelled
from .score_selection import ScoreSelection


class ScoreReadServices:
    def __init__(self, *, lesson, transport, process, learner_progress, lock):
        self.lesson = lesson
        self.transport = transport
        self.process = process
        self.learner_progress = learner_progress
        self.lock = lock
        self._timing = None
        self._encoded_source = None
        self._cancellation_generation = 0

    def selection(self) -> ScoreSelection:
        plan = self.lesson.plan
        if plan is None:
            raise ValueError("No piece loaded")
        remediation = self.lesson.flow_aid
        return ScoreSelection(
            piece=plan.piece, phrase=self.lesson.display_phrase(learning=self.transport.mode == "learn"),
            hand=plan.hand, stage_key=plan.identity,
            revision=self.lesson.revision,
            fingerprint=self.lesson.fingerprint,
            transformed_rhythm=(remediation.transformed_rhythm
                if remediation is not None else plan.active_stage.transformed_rhythm))

    def displayed_score(self, *, learning: bool | None = None, aid=...) -> tuple:
        """What the drawn score depends on (not its revision number):
        piece, window phrase, hand, stage and any aid. Equal values mean
        the notes on screen would be identical."""
        plan = self.lesson.plan
        if plan is None:
            return ()
        if learning is None:
            learning = self.transport.mode == "learn"
        if aid is ...:
            aid = self.lesson.flow_aid if learning else None
        phrase = self.lesson.display_phrase(learning=learning)
        return (self.lesson.fingerprint, plan.identity, plan.hand,
                aid.focus if aid is not None else None,
                aid.transformed_rhythm if aid is not None else plan.active_stage.transformed_rhythm,
                phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
                tuple((n.source_id, n.start, n.end, n.pitch) for n in phrase.notes))

    def practice_timing(self) -> dict:
        with self.lock:
            selected = self.selection()
            return self._timing_for(selected)

    def _timing_for(self, selected: ScoreSelection) -> dict:
        timing = self._timing
        if timing is None or timing[0] != selected.identity:
            timing = (selected.identity,
                      selected_practice_timeline(selected.piece, selected.phrase))
            self._timing = timing
        return timing[1]

    def cancel_preparation(self) -> None:
        self._cancellation_generation += 1

    def _source_document(self, selected, timing, checkpoint):
        # Only the asset lane owns these transfer bytes. In particular the
        # same-revision fingering correction replaces the immutable Piece.
        cached = self._encoded_source
        if cached is not None:
            previous, body = cached
            if (selected.piece is previous.piece and selected.identity == previous.identity
                    and selected.phrase == previous.phrase):
                return body
        body = document_bytes(selected.document(timing), checkpoint)
        checkpoint()
        self._encoded_source = (selected, body)
        return body

    def prepare(self, operation, expected, *, cancelled=None,
                timeout=DEADLINE_SECONDS) -> tuple[int, bytearray]:
        deadline = monotonic() + timeout
        with self.lock:
            selected = self.selection()
            if expected and selected.binding != {key: expected.get(key) for key in BINDING_FIELDS}:
                raise ScoreCancelled("Score request was superseded before preparation")
            timing = self._timing_for(selected)
            generation = self._cancellation_generation

        def obsolete():
            # These cheap reads can stop a job early. The exact check under
            # the session lock below is the publication boundary.
            return (generation != self._cancellation_generation
                    or selected.revision != self.lesson.revision
                    or (cancelled is not None and cancelled()))

        while True:
            status, body = self.process.request(
                operation, selected.binding,
                lambda checkpoint, selection=selected: self._source_document(selection, timing, checkpoint),
                generation=expected.get("generation", generation), cancelled=obsolete,
                rejected_generation=expected.get("rejected_generation"),
                timeout=deadline-monotonic(), validate_json=cancelled is None)
            with self.lock:
                if obsolete() or self.lesson.plan is None:
                    raise ScoreCancelled("Score request was superseded during preparation")
                current = self.selection()
                if current.identity != selected.identity:
                    raise ScoreCancelled("Score request was superseded during preparation")
                if monotonic() >= deadline:
                    raise TimeoutError("Score request exceeded its publication deadline")
                if current.piece is selected.piece:
                    return status, body
                # A correction retains the geometry revision. Capture its new
                # annotations and retry within the original request deadline.
                selected = current

    def guided_marks(self, snapshot: dict) -> list[dict]:
        return self.lesson.guided_marks(snapshot)

    def lesson_overview(self) -> dict:
        return self.learner_progress.lesson_overview(
            self.lesson.plan,
            fingerprint=self.lesson.fingerprint)
