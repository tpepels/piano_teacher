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
        self._beats: dict[str, float] = {}
        self.latest_marks: list[dict] = []

    def clear(self) -> None:
        """Forget the previous take's marks; a new take starts empty."""
        self._take = None
        self._published.clear()
        self._beats.clear()
        self.latest_marks = []

    def publish(self, marks: list[dict], take: dict, *, final: bool = False,
                scope_start_beat: float = -float("inf")) -> int:
        """Publish marks that differ from what this take already published."""
        key = tuple(take[field] for field in
                    ("piece_fingerprint", "revision", "transport_id", "mode"))
        if key != self._take:
            self._take = key
            self._published.clear()
            self._beats.clear()
        self.latest_marks = list(marks)
        if not take["graded"]:
            return 0
        count = 0
        current_ids = {mark.get("source_id") for mark in marks
                       if not mark.get("estimated") and mark.get("source_id")}
        # A later physical press may improve the scorer's closest-onset
        # assignment. Withdraw its old provisional head rather than retain
        # ink which no longer exists in the authoritative projection.
        for source_id in self._published.keys() - current_ids:
            if self._beats.get(source_id,-float("inf")) < scope_start_beat:
                continue  # Older exposed ink keeps its last canonical observation.
            self._beats.pop(source_id,None)
            self.log.publish({"kind": "assessment", **take,
                              "source_id": source_id,
                              "status": "pending", "dimensions": None,
                              "final": False})
            del self._published[source_id]
            count += 1
        for mark in marks:
            source_id = mark.get("source_id")
            if mark.get("estimated") or not source_id:
                continue
            dimensions = dict(mark.get("dimensions") or {})
            signature = (mark.get("status"), tuple(sorted(dimensions.items())), final)
            if self._published.get(source_id) == signature:
                continue
            self._published[source_id] = signature
            self._beats[source_id] = float(mark.get("beat",0.0))
            self.log.publish({
                "kind": "assessment", **take,
                "source_id": source_id,
                "status": mark.get("status"), "dimensions": dimensions,
                "final": final,
            })
            count += 1
        return count
