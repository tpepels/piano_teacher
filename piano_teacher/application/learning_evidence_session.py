"""Immutable assessment context and adaptive retry-evidence preparation.

Only this session constructs the versioned learning-rule snapshot used for
stored attempts and reads compatible completed/interrupted prior attempts
for retry policy. It owns no teaching decision, clock, MIDI grading or
visual transport and never reaches back into PracticeEngine.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from ..lesson_settings import SETTINGS
from ..teaching import TeachingConfig
from .mistake_responses import resolve_mistake_policy, mistake_policy_facts


class LearningEvidenceSession:
    def __init__(self, progress, library, measurement, midi, midi_calibration):
        self._progress = progress
        self._library = library
        self._measurement = measurement
        self._midi = midi
        self._midi_calibration = midi_calibration
        self._db = progress.db

    def context(self, plan, *, fingerprint: str, scope: str,
                start: float, end: float, run_at: float | None = None,
                tempo_map=None, transport_id: int, score_revision: int,
                count_in_beats: float, count_in_meter,
                guided_config=None, persistent_hints: bool = False) -> dict:
        p = plan
        phrase = p.active_phrase
        tempo = tempo_map
        segments = (list(tempo.as_segments()) if tempo is not None else
                    [{"start_beat": 0.0, "end_beat": phrase.end-phrase.start,
                      "bpm": p.bpm}])
        rule = {"schema_version": 1, "grader": "nearest-onset-v1",
                "mastery": "accepted-full-target-v1", "lesson_settings": asdict(SETTINGS),
                "onset_formula": "max(grading_onset_tolerance_seconds,min(0.30,0.20*local_spb))",
                "hold_formula": "max(grading_duration_floor_seconds,duration*max(grading_duration_tolerance_fraction,min(0.75,grading_duration_tolerance_fraction+0.28*max(0,local_spb-0.5))))",
                "importer": "midi-source-v1", "generator": p.lesson_generator.name,
                "generator_version": p.route_version,
                "retry_version": resolve_mistake_policy(self._library.settings["mistake_response_strategy"]).version,
                "guided_config": {**asdict(guided_config if guided_config is not None else TeachingConfig()),
                                  "persistent_hints": persistent_hints},
                "retry": mistake_policy_facts(resolve_mistake_policy(self._library.settings["mistake_response_strategy"]))}
        rule_id = self._progress.ledger.store_rules(rule)
        return {"fingerprint": fingerprint, "source_sha256": fingerprint,
                "stage_key": p.identity, "hand": p.hand, "scope": scope,
                "variant": p.active_variant.level, "generator": p.lesson_generator.name,
                "generator_version": p.route_version, "rule_id": rule_id,
                "source_note_ids": [n.source_id for n in phrase.notes],
                "variant_source_indices": list(p.active_variant.source_indices),
                "expected_notes": [asdict(n) for n in phrase.notes],
                "bar_boundaries": list(p.piece.bar_boundaries),
                "time_signatures": [list(signature) for signature in p.piece.time_signatures],
                "phrase_start": phrase.start, "phrase_end": phrase.end,
                "from_beat": start, "end_beat": end, "target_bpm": p.target_bpm,
                "source_bpm": p.piece.bpm,
                "performed_bpm": p.bpm, "tempo_map": segments,
                "tempo_map_hash": hashlib.sha256(json.dumps(segments, sort_keys=True).encode()).hexdigest(),
                "transport_id": transport_id, "score_revision": score_revision,
                "scheduled_origin": None if run_at is None else run_at-self._measurement.origin,
                "count_in_beats": count_in_beats,
                "count_in_meter": list(count_in_meter),
                "midi_available": self._midi.connected,
                "device_name": self._midi.device,
                "calibration_ms": self._library.settings["midi_offset_ms"],
                "calibration_result": self._midi_calibration.result,
                "calibration_applied_ms": (0 if scope in ("guided", "preview") else
                                            self._library.settings["midi_offset_ms"]),
                "assistance": persistent_hints or scope == "guided"}


    def adaptive_context(self, result, *, plan, fingerprint: str,
                         from_beat: float, end_beat=None):
        """Use compatible, retained original grading evidence at retry boundaries."""
        from .mistake_responses import (
            AdaptiveAttempt, AdaptiveContext, adaptive_attempt_from_assessment)
        context = self._measurement.context or {}
        phrase = plan.active_phrase
        attempts = []
        rows = self._db.execute("""SELECT t.context_json,d.detail_json FROM learning_attempts t
            JOIN learning_attempt_details d USING(attempt_id)
            WHERE t.fingerprint=? AND t.stage_key=? AND t.state IN ('completed','interrupted')
            ORDER BY t.rowid DESC LIMIT 16""", (fingerprint, plan.identity)).fetchall()
        for encoded, detail_json in reversed(rows):
            if not encoded:
                continue
            previous, detail = json.loads(encoded), json.loads(detail_json)
            if any(previous.get(key) != context.get(key) for key in
                   ("hand", "rule_id", "target_bpm", "calibration_applied_ms")):
                continue
            assessment = detail.get("assessment")
            observations = detail.get("observations", [])
            if not assessment or not observations or previous.get("scope") in ("perform", "preview", "guided"):
                continue
            if any(item.get("missingness") for item in observations):
                continue
            selected = {}
            if previous.get("parent_decision_id"):
                row = self._db.execute("SELECT data_json FROM learning_decisions WHERE decision_id=?",
                                      (previous["parent_decision_id"],)).fetchone()
                if row and row[0]:
                    selected = json.loads(row[0]).get("selected", {})
            attempts.append(AdaptiveAttempt(
                identity=plan.identity, start_beat=previous["from_beat"],
                end_beat=detail.get("assessed_end_beat", previous["end_beat"]),
                bpm=previous["performed_bpm"],
                wrong_beats=tuple(n["source_beat"]-phrase.start for n in observations if n["status"] == "wrong"),
                missed_beats=tuple(n["source_beat"]-phrase.start for n in observations if n["status"] == "missed"),
                timing_errors=sum(bool(n.get("timing_error")) for n in observations),
                hold_errors=sum(bool(n.get("hold_error")) for n in observations),
                accepted=assessment["passed"], assisted=bool(detail.get("assistance_used")),
                action=selected.get("action", "repeat"), extra_errors=assessment.get("extra_notes", 0)))
        action = "repeat"
        parent = context.get("parent_decision_id")
        if parent:
            row = self._db.execute("SELECT data_json FROM learning_decisions WHERE decision_id=?", (parent,)).fetchone()
            if row and row[0]:
                action = json.loads(row[0]).get("selected", {}).get("action", "repeat")
        attempts.append(adaptive_attempt_from_assessment(result, identity=plan.identity,
            start_beat=from_beat,
            end_beat=end_beat if end_beat is not None else context.get("end_beat", phrase.end-phrase.start),
            bpm=context.get("performed_bpm", plan.bpm), phrase_start=phrase.start,
            assisted=self._measurement.assistance_used, action=action))
        episode = self._measurement.episode
        count, reference = 0, context.get("performed_bpm", plan.bpm)
        if episode:
            count = self._db.execute("SELECT count(*) FROM learning_decisions WHERE json_extract(summary_json,'$.episode_id')=?",
                                    (episode["id"],)).fetchone()[0]
            row = self._db.execute("""SELECT t.summary_json FROM learning_decisions d
                JOIN learning_attempts t ON t.attempt_id=d.attempt_id WHERE d.decision_id=?""",
                (episode["first_decision"],)).fetchone()
            if row:
                reference = json.loads(row[0]).get("performed_bpm", reference)
        onsets = {n.start for n in phrase.notes if plan.hand == "both" or n.hand == plan.hand}
        return AdaptiveContext(plan.identity, tuple(attempts), episode_action_count=count,
            original_start_beat=0., original_end_beat=phrase.end-phrase.start,
            source_attacks=len(onsets), attacks_per_beat=len(onsets)/(phrase.end-phrase.start),
            reference_bpm=reference)





    def history_status(self, *, fingerprint: str, data_dir) -> dict:
        status = self._progress.ledger.status()
        return {**status, "attempt_count": status["attempts"],
                "detail_attempt_count": status["attempts"]-status["coverage"]["pruned_detail_attempts"]-status["coverage"]["legacy_bounded_attempts"],
                "pruned_attempt_count": status["coverage"]["pruned_detail_attempts"],
                "current_fingerprint": fingerprint,
                "default_path": str(data_dir / "exports" / "learning-history.json"),
                "evidence_retention_days": self._library.settings["evidence_retention_days"],
                "evidence_budget_mib": self._library.settings["evidence_budget_mib"],
                "summary": (f"{status['attempts']} recorded takes. "
                            "History stays on this computer. Reset Lesson preserves history.")}


    def statistics(self, fingerprint: str | None = None, *, query=None) -> dict:
        """Read measured learning outcomes without advancing the musical clock."""
        from ..learning_statistics import learning_statistics
        from ..learning_statistics_query import capture_statistics, validate_query
        from contextlib import closing
        import sqlite3
        q = validate_query(query, fingerprint)
        # An independent read-only connection never waits for the engine lock.
        # Close the bounded snapshot before formatting, releasing SQLite's read
        # lock before any expensive dictionary/quantile projection.
        path = self._progress.db_path.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(path, uri=True, timeout=.05)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            learner = db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()[0]
            snapshot = capture_statistics(db, learner, q)
            db.rollback()
            report = learning_statistics(None, query=q, snapshot=snapshot)
            # Deletion may commit while formatting. Never publish erased data
            # or a former learner's snapshot after that boundary.
            current = db.execute("SELECT learner_id FROM learning_current_learner WHERE singleton=1").fetchone()
            ids = snapshot["query"]["attempt_ids"]
            slots = ",".join("?" for _ in ids) or "NULL"
            retained = db.execute(f"SELECT count(*) FROM learning_attempts WHERE attempt_id IN ({slots})", ids).fetchone()[0]
            if current != (learner,) or retained != len(ids):
                raise ValueError("Learning history changed during the report; refresh statistics")
            report["learner_id"] = learner
            return report

