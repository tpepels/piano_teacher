"""Immutable source and transport context for learning-evidence capture.

This operation constructs facts but never begins an assessment, modifies
progress or advances a musical clock.
"""
from __future__ import annotations


class SessionEvidenceContext:
    def __init__(self, *, source_identity, playback_session, guided_session,
                 learning_evidence):
        self.source_identity = source_identity
        self.playback_session = playback_session
        self.guided_session = guided_session
        self.learning_evidence = learning_evidence

    def build(self, *, scope: str, start: float, end: float,
              run_at: float | None = None, tempo_map=None) -> dict:
        teaching = self.guided_session.controller
        return self.learning_evidence.context(
            self.source_identity.plan,
            fingerprint=self.source_identity.fingerprint,
            scope=scope, start=start, end=end, run_at=run_at,
            tempo_map=tempo_map,
            transport_id=self.playback_session.transport_id,
            score_revision=self.source_identity.revision,
            count_in_beats=self.playback_session.count_in_beats,
            count_in_meter=self.playback_session.count_in_meter,
            guided_config=teaching.config if teaching is not None else None,
            persistent_hints=self.guided_session.persistent_hints,
            variant=(self.guided_session.fragment.variant
                     if scope == "guided" and self.guided_session.fragment is not None
                     else None))
