"""Continuously publish authoritative per-note assessments for the active take.

The engine computes its normal incremental live assessment (settled notes and
expired-attack misses) on every clock update. This publisher turns each new or
changed per-note result into one ``assessment`` event in the FeedbackEventLog,
so the score is colored during ordinary playback, not only after recovery or
completion. It never grades: it forwards exactly what the assessment produced.
"""
from __future__ import annotations

from .feedback_events import FeedbackEventLog


class LiveAssessmentPublisher:
    def __init__(self, log: FeedbackEventLog) -> None:
        self.log = log
        self._take: tuple | None = None
        self._published: dict[str, tuple] = {}
        self.latest_marks: list[dict] = []

    def publish(self, marks: list[dict], take: dict, *, final: bool = False) -> int:
        """Publish marks that differ from what this take already published."""
        key = tuple(take[field] for field in
                    ("piece_fingerprint", "revision", "transport_id", "mode"))
        if key != self._take:
            self._take = key
            self._published.clear()
        self.latest_marks = list(marks)
        if not take["graded"]:
            return 0
        count = 0
        for mark in marks:
            note_id = mark.get("note_id")
            if mark.get("estimated") or not note_id:
                continue
            dimensions = dict(mark.get("dimensions") or {})
            signature = (mark.get("status"), tuple(sorted(dimensions.items())))
            if self._published.get(note_id) == signature:
                continue
            self._published[note_id] = signature
            self.log.publish({
                "kind": "assessment", **take,
                "note_id": note_id, "source_id": mark.get("source_id", ""),
                "status": mark.get("status"), "dimensions": dimensions,
                "final": final,
            })
            count += 1
        return count
