"""Settings change transaction and configured policy installation.

Validation precedes side effects. Device reconfiguration, evidence retention,
policy selection and session invalidation consume the same persisted settings.
No engine reference or second assessment policy is retained.
"""
from __future__ import annotations
from .learning_capture import identifier


class SettingsWorkflows:
    def __init__(self, *, library, measurement, lifecycle, notices,
                 policy_registry, midi_key_shortcuts, playback_session,
                 visual_transport, progress, library_health, source_identity):
        self.library = library
        self.measurement = measurement
        self.lifecycle = lifecycle
        self.notices = notices
        self.policy_registry = policy_registry
        self.midi_key_shortcuts = midi_key_shortcuts
        self.playback_session = playback_session
        self.visual_transport = visual_transport
        self.progress = progress
        self.library_health = library_health
        self.source_identity = source_identity

    def preferences(self) -> dict:
        return self.library.public_settings()

    def record_midi_key_range(self, device: str, keys: tuple,
                              *, pause_current) -> dict:
        """Store a completed physical shortcut capture through settings policy."""
        ranges = self.library.settings["midi_key_ranges"].copy()
        ranges[device] = list(keys)
        return self.update({"midi_key_ranges": ranges},
                           pause_current=pause_current)

    def update(self, changes: dict, *, pause_current) -> dict:
        proposed = self.library.propose_update(**changes)
        before = self.library.settings["music_dir"]
        intent = identifier()
        self.measurement.event("settings_intent", {
            "intent_id": intent,
            "before": {key: self.library.settings[key] for key in changes},
            "after": {key: proposed[key] for key in changes}})
        if proposed["midi_offset_ms"] != self.library.settings["midi_offset_ms"]:
            self.lifecycle.stop(reason="calibration_changed")
            self.notices.publish(
                "MIDI timing correction changed",
                "Press Play to start a new attempt.")
        if proposed["mistake_response_strategy"] != self.library.settings["mistake_response_strategy"]:
            self.lifecycle.stop(reason="policy_changed")
            self.notices.publish(
                "Retry strategy changed",
                "Press Play to start a new attempt.")
        prior_hold_grading = self.library.settings["grade_note_holds"]
        updated = self.library.update(**changes)
        if updated["grade_note_holds"] != prior_hold_grading:
            # Hold grading applies to timed attempts, not Listen or Free.
            # Stopping an ungraded exposure cancels its asynchronous audio
            # preparation and leaves the learner waiting for an invalidated
            # source. Preserve those exposures; new Tempo takes use the
            # newly installed rule. Invalidate any graded attempt/continuation
            # so an existing recorder cannot mix two grading policies.
            if self.playback_session.mode in ("practice", "perform"):
                self.lifecycle.stop(reason="grading_rule_changed")
                self.notices.publish(
                    "Note-hold grading changed",
                    "Press Play to start a new attempt.")
            self.policy_registry.apply_hold_rule(updated["grade_note_holds"])
        if "midi_key_ranges" in changes:
            self.midi_key_shortcuts.configure(updated["midi_key_ranges"])
        self.measurement.event("settings_applied", {
            "intent_id": intent, "changes": changes})
        if {"evidence_retention_days", "evidence_budget_mib"} & changes.keys():
            if self.playback_session.running and not self.visual_transport.paused:
                pause_current()
            self.progress.ledger.prune(
                days=proposed["evidence_retention_days"],
                budget_mib=proposed["evidence_budget_mib"])
        if {"diagnosis_strategy", "learner_strategy"} & changes.keys():
            self.policy_registry.apply_learning_rules(self.library.settings)
        if before != self.library.settings["music_dir"]:
            self.library_health.reset()
        return updated

    def exercise_diagnostics(self, *, tempo_map) -> dict:
        selected = self.source_identity.plan
        if selected is None:
            return {"loaded": False,
                    "exercise_strategy": self.library.settings["exercise_strategy"]}
        return {"loaded": True,
                "exercise_strategy": selected.exercise_strategy.name,
                "tempo_segments": tempo_map.as_segments() if tempo_map is not None else (),
                "stage_key": selected.identity,
                **self.policy_registry.learning.inspect(
                    self.source_identity.fingerprint, selected.identity)}
