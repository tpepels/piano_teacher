"""Immutable source and transport context for learning-evidence capture.

This operation constructs facts but never begins an assessment, modifies
progress or advances a musical clock.
"""
from __future__ import annotations


class SessionEvidenceContext:
    def __init__(self, *, lesson, transport,
                 learning_evidence):
        self.lesson = lesson
        self.transport = transport
        self.learning_evidence = learning_evidence

    def build(self, *, scope: str, start: float, end: float,
              run_at: float | None = None, tempo_map=None) -> dict:
        teaching = self.lesson.guided_controller
        return self.learning_evidence.context(
            self.lesson.plan,
            fingerprint=self.lesson.fingerprint,
            scope=scope, start=start, end=end, run_at=run_at,
            tempo_map=tempo_map,
            transport_id=self.transport.transport_id,
            score_revision=self.lesson.revision,
            count_in_beats=self.transport.count_in_beats,
            count_in_meter=self.transport.count_in_meter,
            guided_config=teaching.config if teaching is not None else None,
            persistent_hints=self.lesson.persistent_hints,
            variant=(self.lesson.guided_fragment.variant
                     if scope == "guided" and self.lesson.guided_fragment is not None
                     else None))
