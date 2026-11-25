"""The score domain: one owner for the selected score and its successor.

Internals: artifacts (ScoreArtifactRegistry), read (ScoreReadServices),
successor (TeachingContinuation: next-stage readiness, reservation and
schedule), publisher (ScoreStatePublisher) and tempo_maps (TempoMapCache).
Score is also the successor-reservation port the settlement transaction
uses (validate/reserve, capture/restore) for atomic rollback.

Other modules read through the read-only properties below and change
state only through these named operations; the internals are never
referenced outside the domain's own modules.
"""
from __future__ import annotations


class Score:
    def __init__(self, *, artifacts, successor, publisher, tempo_maps):
        self._artifacts = artifacts
        self._read = None
        self._successor = successor
        self._publisher = publisher
        self._tempo_maps = tempo_maps

    def attach_read(self, read) -> None:
        """Bind once during composition."""
        if self._read is not None:
            raise RuntimeError("read is already attached")
        self._read = read

    # --- score_artifact_registry

    @property
    def current_artifacts(self):
        return self._artifacts.current

    def invalidate_artifacts(self, *args, **kwargs):
        return self._artifacts.invalidate(*args, **kwargs)

    # --- score_read

    def bundle(self, *args, **kwargs):
        return self._read.bundle(*args, **kwargs)

    def completed_take_layout(self, *args, **kwargs):
        return self._read.completed_take_layout(*args, **kwargs)

    def geometry(self, *args, **kwargs):
        return self._read.geometry(*args, **kwargs)

    def guided_marks(self, *args, **kwargs):
        return self._read.guided_marks(*args, **kwargs)

    def lesson_overview(self, *args, **kwargs):
        return self._read.lesson_overview(*args, **kwargs)

    def selection(self, *args, **kwargs):
        return self._read.selection(*args, **kwargs)

    def displayed_score(self, *args, **kwargs):
        return self._read.displayed_score(*args, **kwargs)

    def semantic_score(self, *args, **kwargs):
        return self._read.semantic_score(*args, **kwargs)

    def source_model(self, *args, **kwargs):
        return self._read.source_model(*args, **kwargs)

    # --- teaching_continuation

    def begin_feedback(self, *args, **kwargs):
        return self._successor.begin_feedback(*args, **kwargs)

    def capture_successor_state(self, *args, **kwargs):
        return self._successor.capture_state(*args, **kwargs)

    def finish_feedback(self, *args, **kwargs):
        return self._successor.finish_feedback(*args, **kwargs)

    def restore_successor_state(self, *args, **kwargs):
        return self._successor.restore_state(*args, **kwargs)

    def settlement_failure(self, *args, **kwargs):
        return self._successor.settlement_failure(*args, **kwargs)

    def validate_announcement(self, *args, **kwargs):
        return self._successor.validate_announcement(*args, **kwargs)

    def prepare_guided_score(self, *args, **kwargs):
        return self._publisher.prepare_guided(*args, **kwargs)

    def project_transport_state(self, *args, **kwargs):
        return self._publisher.project_transport_state(*args, **kwargs)

    def publish_score_state(self, *args, **kwargs):
        return self._publisher.publish(*args, **kwargs)

    def free_target_arrival(self, lesson, transport) -> float | None:
        """When the current Free target reaches the playhead (None outside Free)."""
        if transport.mode != "learn":
            return None
        return self._publisher.guided_open_at((
            lesson.fingerprint, lesson.plan.identity if lesson.plan else "",
            lesson.revision, transport.transport_id))

    def free_target_travel(self, lesson, transport) -> float | None:
        """Beats the first Free target travels to the playhead."""
        if transport.mode != "learn":
            return None
        return self._publisher.guided_travel((
            lesson.fingerprint, lesson.plan.identity if lesson.plan else "",
            lesson.revision, transport.transport_id))

    def reset_guided_score(self, *args, **kwargs):
        return self._publisher.reset_guided(*args, **kwargs)

    # --- tempo_map_cache

    def tempo_map(self, *args, **kwargs):
        return self._tempo_maps.get(*args, **kwargs)

    # --- successor schedule used by the transport domain
    def announce_successor(self, *args, **kwargs):
        return self._successor.announce(*args, **kwargs)

    def cancel_successor(self, *args, **kwargs):
        return self._successor.cancel(*args, **kwargs)

    def stop_successor(self) -> None:
        self._successor.stop()

