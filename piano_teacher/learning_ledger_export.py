"""Read-only history snapshot and atomic, redacted export writer."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .learning_ledger_common import SCHEMA_VERSION, _redact, _utc
from .learning_ledger_retention import LearningDetailRetention
from .sqlite_transaction import sqlite_atomic


class LearningHistoryExporter:
    def __init__(self, db: sqlite3.Connection, retention: LearningDetailRetention):
        self.db = db
        self.retention = retention

    def _rows(self, table):
        cursor = self.db.execute(f"SELECT * FROM {table}")
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def export(self, path, *, include_detail=False) -> dict:
        if not isinstance(include_detail, bool):
            raise ValueError("Detailed export must be explicitly selected")
        with sqlite_atomic(self.db):
            attempts = self._rows("learning_attempts")
            for row in attempts:
                row["summary"] = json.loads(row.pop("summary_json"))
                context = row.pop("context_json")
                checkpoint = row.pop("checkpoint_json")
                row["context"] = json.loads(context) if include_detail and context else row["summary"]
                row["checkpoint"] = json.loads(checkpoint) if include_detail and checkpoint else None
                detail = self.db.execute("SELECT detail_json FROM learning_attempt_details WHERE attempt_id=?", (row["attempt_id"],)).fetchone()
                row["detail"] = json.loads(detail[0]) if include_detail and detail else None
                row["detail_pruned"] = bool(row["detail_pruned"])
            assessments = self._rows("learning_assessments")
            for row in assessments:
                row["summary"] = json.loads(row.pop("summary_json"))
                row["statuses"] = json.loads(row.pop("statuses_json"))
                for key in ("clean", "passed", "mastery_eligible", "assessed"):
                    if row[key] is not None:
                        row[key] = bool(row[key])
            result = {"schema_version": SCHEMA_VERSION, "exported_utc": _utc(), "learner_id": self.retention.learner_id,
                      "include_detail": include_detail, "units": {"beats": "quarter_notes", "times": "seconds",
                          "residuals": "seconds", "derived_residuals": "integer_microseconds", "tempo": "beats_per_minute",
                          "monotonic": "seconds_within_run_only", "calendar": "UTC"},
                      "missingness": {"unknown": "null or an explicit unknown marker; never a measured zero",
                          "legacy_bounded": "Only the retained old status window was imported; timing, rules, timestamps and passed are unknown",
                          "pruned_detail": "Compact summaries remain; missing note detail is not a complete lifetime observation",
                          "unavailable": ["physical_hand", "pedal_accuracy", "velocity_accuracy"]},
                      "coverage": self.retention.status()["coverage"], "sessions": self._rows("learning_sessions"),
                      "attempts": attempts, "assessments": assessments,
                      "rules": [{"rule_id": row["rule_id"], "snapshot": json.loads(row["snapshot_json"])}
                                for row in self._rows("learning_rules")]}
            for session in result["sessions"]:
                session["durations_seconds"] = json.loads(session.pop("durations_json"))
            for name in ("events", "decisions", "outcomes"):
                rows = self._rows("learning_" + name)
                for row in rows:
                    row["summary"] = json.loads(row.pop("summary_json"))
                    encoded = row.pop("data_json")
                    row["data"] = json.loads(encoded) if include_detail and encoded else row["summary"]
                result[name] = rows
            result = _redact(result)
        target = Path(path)
        # A failed serialization or write never leaves an apparently complete
        # export at the selected destination.
        encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + "." + str(uuid4()) + ".tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return {"path": str(target), "schema_version": SCHEMA_VERSION, "attempts": len(attempts), "include_detail": include_detail}
