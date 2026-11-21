"""Validation, compact summaries and privacy encoding for learning evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math


SCHEMA_VERSION = 1
class LearningLedgerLimitError(ValueError):
    """Detail cannot fit without discarding an open or pending exposure."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _identifier(value, label="identity") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"A nonempty {label} is required")
    return value


def _validate(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Evidence numbers must be finite")
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate(item)
        return
    raise ValueError("Evidence must be finite JSON with string object keys")


def _json(value) -> str:
    _validate(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def _hash(value) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _object(value, label="payload") -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"The {label} must be a JSON object")
    _validate(value)
    return value


def _compact(value):
    """Small facts retained after detail pruning; omission is labeled in coverage."""
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in value.items()
                if not isinstance(item, str) or len(item) <= 1024}
    if isinstance(value, (list, tuple)):
        if len(value) <= 16 and all(not isinstance(item, (dict, list, tuple)) for item in value):
            return list(value)
        return {"item_count": len(value), "detail_required": True}
    return value


_CONTEXT_FACTS = frozenset((
    "score_revision", "from_beat", "phrase_start", "phrase_end", "assistance",
    "calibration_ms", "calibration_applied_ms", "midi_available", "count_in_beats", "count_in_meter", "scheduled_origin",
    "fingerprint", "stage_key", "rule_id", "generator", "generator_version", "strategy",
    "strategy_version", "hand", "variant", "level", "classification", "mode", "scope",
    "target_bpm", "source_bpm", "performed_bpm", "bpm", "tempo_map_hash", "transport_id", "revision",
    "started_utc", "monotonic_start", "run_id", "parent_decision_id", "first_bar", "last_bar",
    "start_beat", "end_beat", "full_target", "mastery_eligible", "eligibility_reason",
    "calibration", "calibration_ms", "device_available", "midi_available", "assistance",
    "score_revision", "phrase_start", "phrase_end", "from_beat", "source_sha256", "provenance"))


def _context_summary(value: dict) -> dict:
    return _compact({key: item for key, item in value.items() if key in _CONTEXT_FACTS})


def _redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if ("path" in normalized or normalized in {"name", "title", "filename", "file_name", "raw_midi", "midi_bytes",
                    "music_dir", "midi_device", "last_piece", "source", "device"}
                    or normalized.endswith("_name") or normalized.endswith("_title")
                    or normalized in {"device", "piece"} and isinstance(item, str)):
                continue
            result[key] = _redact(item)
            if normalized.endswith("_residual") and isinstance(item, (int, float)) and not isinstance(item, bool):
                result[key + "_microseconds"] = round(item * 1_000_000)
            if normalized.endswith("_residual_seconds") and isinstance(item, (int, float)) and not isinstance(item, bool):
                result[key[:-7] + "microseconds"] = round(item * 1_000_000)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
