"""Validated, bounded snapshots of the canonical evidence tables.

No writer, migration, grader or mutable lesson plan is used here. Row IDs order
pages; a frozen boundary identity expires cursors after tail deletion/reuse.
"""
from __future__ import annotations

import base64
from datetime import date
from hashlib import sha256
import json
import math
import sqlite3
import time


def validate_query(values=None, fingerprint=None):
    if not isinstance(values, (dict, type(None))):
        raise ValueError("Statistics query must be an object")
    q = dict(values or {})
    allowed = {"version", "fingerprint", "session_id", "date_from", "date_to", "stage_key",
               "hand", "bpm_min", "bpm_max", "scope", "policy", "limit", "cursor", "detail_budget_bytes"}
    if not isinstance(values, (dict, type(None))) or set(q) - allowed:
        raise ValueError("Unknown statistics query input")
    if fingerprint is not None:
        if "fingerprint" in q and q["fingerprint"] != fingerprint:
            raise ValueError("Conflicting source filters")
        q["fingerprint"] = fingerprint
    q.setdefault("version", 1)
    q.setdefault("limit", 250)
    q.setdefault("detail_budget_bytes", 2 * 1024 * 1024)
    for key, maximum in (("version", 1), ("limit", 1000), ("detail_budget_bytes", 4 * 1024 * 1024)):
        if type(q[key]) is not int or not 1 <= q[key] <= maximum:
            raise ValueError(f"Invalid statistics {key}")
    for key in ("fingerprint", "session_id", "stage_key", "policy", "cursor"):
        if key in q and (type(q[key]) is not str or not q[key].strip() or len(q[key]) > 2048):
            raise ValueError(f"Invalid statistics {key}")
    for key, choices in (("hand", {"left", "right", "both"}),
                         ("scope", {"full", "partial", "guided", "preview", "perform", "section_review"})):
        if key in q and (type(q[key]) is not str or q[key] not in choices):
            raise ValueError(f"Invalid statistics {key}")
    for key in ("date_from", "date_to"):
        if key in q:
            try:
                if type(q[key]) is not str or date.fromisoformat(q[key]).isoformat() != q[key]:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(f"Invalid statistics {key}") from None
    if q.get("date_from", "") > q.get("date_to", "9999-12-31"):
        raise ValueError("Reversed statistics dates")
    for key in ("bpm_min", "bpm_max"):
        if key in q and (type(q[key]) not in (int, float) or not math.isfinite(q[key]) or not 0 < q[key] <= 1000):
            raise ValueError(f"Invalid statistics {key}")
    if q.get("bpm_min", 0) > q.get("bpm_max", 1000):
        raise ValueError("Reversed statistics tempo range")
    return q


def rows(db, sql, args=()):
    cursor = db.execute(sql, args)
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, row)) for row in cursor]


def capture_statistics(db, learner_id, q):
    """Capture at most 1000 attempts and 4 MiB retained detail, in one snapshot.

    Related event/decision/outcome rows each have a 4000-row cap and share the
    detail byte budget. A SQLite progress deadline bounds pathological filters.
    The caller owns transaction/connection lifetime; formatting follows capture.
    """
    digest = sha256(json.dumps({k: v for k, v in q.items() if k != "cursor"}, sort_keys=True).encode()).hexdigest()
    boundary = db.execute("SELECT rowid,attempt_id FROM learning_attempts ORDER BY rowid DESC LIMIT 1").fetchone()
    high, boundary_id = boundary if boundary else (0, None)
    after = 0
    if "cursor" in q:
        try:
            token = json.loads(base64.urlsafe_b64decode(q["cursor"].encode()))
            if (set(token) != {"v", "learner", "query", "high", "boundary", "after", "anchor"} or token["v"] != 2
                    or token["learner"] != learner_id or token["query"] != digest
                    or type(token["high"]) is not int or type(token["after"]) is not int
                    or not 0 < token["after"] <= token["high"] <= high
                    or db.execute("SELECT attempt_id FROM learning_attempts WHERE rowid=?", (token["high"],)).fetchone() != (token["boundary"],)
                    or db.execute("SELECT attempt_id FROM learning_attempts WHERE rowid=?", (token["after"],)).fetchone() != (token["anchor"],)):
                raise ValueError()
            high, after, boundary_id = token["high"], token["after"], token["boundary"]
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("Invalid or expired statistics cursor") from None
    clauses = ["s.learner_id=?", "t.rowid>?", "t.rowid<=?"]
    args = [learner_id, after, high]
    for key, expression, operator in (
            ("fingerprint", "t.fingerprint", "="), ("stage_key", "t.stage_key", "="),
            ("session_id", "t.session_id", "="), ("hand", "json_extract(t.summary_json,'$.hand')", "="),
            ("scope", "json_extract(t.summary_json,'$.scope')", "="),
            ("bpm_min", "json_extract(t.summary_json,'$.performed_bpm')", ">="),
            ("bpm_max", "json_extract(t.summary_json,'$.performed_bpm')", "<="),
            ("date_from", "substr(json_extract(t.summary_json,'$.started_utc'),1,10)", ">="),
            ("date_to", "substr(json_extract(t.summary_json,'$.started_utc'),1,10)", "<=")):
        if key in q:
            clauses.append(f"{expression}{operator}?")
            args.append(q[key])
    if "policy" in q:
        clauses.append("EXISTS(SELECT 1 FROM learning_decisions p WHERE p.attempt_id=t.attempt_id AND json_extract(p.summary_json,'$.policy')=?)")
        args.append(q["policy"])
    deadline = time.monotonic() + 2.0
    db.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
    try:
        attempts = rows(db, """SELECT t.rowid AS sequence,t.attempt_id,t.session_id,t.fingerprint,t.stage_key,t.rule_id,t.state,t.reason,t.summary_json,t.detail_pruned,t.provenance,
            a.bpm AS assessed_bpm,a.passed,a.clean,a.mastery_eligible,a.extra_notes,
            a.summary_json AS assessment_json FROM learning_attempts t
            JOIN learning_sessions s USING(session_id) LEFT JOIN learning_assessments a USING(attempt_id)
            WHERE """ + " AND ".join(clauses) + " ORDER BY t.rowid LIMIT ?", (*args, q["limit"] + 1))
        more = len(attempts) > q["limit"]
        attempts = attempts[:q["limit"]]
        ids = [a["attempt_id"] for a in attempts]
        slots = ",".join("?" for _ in ids) or "NULL"
        session_ids = sorted({a["session_id"] for a in attempts})
        session_slots = ",".join("?" for _ in session_ids) or "NULL"
        sessions = rows(db, f"SELECT * FROM learning_sessions WHERE session_id IN ({session_slots})", session_ids)
        budget = q["detail_budget_bytes"]
        used = truncated = 0
        for a in attempts:
            a["detail_present"] = False
            a["observations_json"] = None
        by_id = {a["attempt_id"]: a for a in attempts}
        for meta in rows(db, f"SELECT attempt_id,octet_length(detail_json) AS size FROM learning_attempt_details WHERE attempt_id IN ({slots})", ids):
            if meta["size"] > budget - used:
                truncated += 1
                continue
            used += meta["size"]
            detail = db.execute("SELECT json_extract(detail_json,'$.observations') FROM learning_attempt_details WHERE attempt_id=?", (meta["attempt_id"],)).fetchone()[0]
            by_id[meta["attempt_id"]].update(detail_present=True, observations_json=detail)
        related = {}
        related_truncated = {}
        for name, sql, params in (
                ("decisions", f"SELECT * FROM learning_decisions WHERE attempt_id IN ({slots}) ORDER BY rowid LIMIT 4001", ids),
                ("events", f"SELECT * FROM learning_events WHERE session_id IN ({session_slots}) AND (attempt_id IN ({slots}) OR kind='phase_intervals') ORDER BY rowid LIMIT 4001", (*session_ids, *ids)),
                ("outcomes", f"SELECT o.* FROM learning_outcomes o JOIN learning_decisions d USING(decision_id) WHERE d.attempt_id IN ({slots}) ORDER BY o.rowid LIMIT 4001", ids)):
            # SQL substr prevents a single oversized retained payload crossing
            # the boundary; the original size is still exposed as truncation.
            sql = sql.replace("SELECT *", "SELECT *,octet_length(data_json) AS payload_size").replace("SELECT o.*", "SELECT o.*,octet_length(o.data_json) AS payload_size")
            sql = sql.replace("SELECT *,", "SELECT " + ",".join(c[1] for c in db.execute(f"PRAGMA table_info(learning_{name})") if c[1] != "data_json") + ",") if name != "outcomes" else sql.replace("o.*", "o.outcome_id,o.decision_id,o.attempt_id,o.summary_json")
            values = rows(db, sql, params)
            related_truncated[name] = int(len(values) > 4000)
            related[name] = []
            for value in values[:4000]:
                size = value.pop("payload_size") or 0
                value["data_json"] = None
                if size <= budget - used:
                    table, identity = "learning_" + name, {"events": "event_id", "decisions": "decision_id", "outcomes": "outcome_id"}[name]
                    value["data_json"] = db.execute(f"SELECT data_json FROM {table} WHERE {identity}=?", (value[identity],)).fetchone()[0]
                    used += size
                elif size:
                    related_truncated[name] += 1
                related[name].append(value)
        rule_ids = sorted({a["rule_id"] for a in attempts if a["rule_id"]})
        rule_slots = ",".join("?" for _ in rule_ids) or "NULL"
        rules = dict(db.execute(f"SELECT rule_id,snapshot_json FROM learning_rules WHERE rule_id IN ({rule_slots})", rule_ids))
        observation_count = observation_truncated = 0
        for a in attempts:
            observations = json.loads(a["observations_json"] or "[]")
            available = max(0, 10000-observation_count)
            observation_truncated += max(0, len(observations)-available)
            observations = observations[:available]
            observation_count += len(observations)
            a["observations_json"] = json.dumps(observations, separators=(",", ":")) if a["detail_present"] else None
            # Saved stage progress may resume in another capture session. A
            # session boundary alone never proves that its initial streak was
            # zero, even when all earlier retained attempts are in this page.
            a["has_prior_episode_attempts"] = bool(db.execute("""SELECT 1 FROM learning_attempts p
                JOIN learning_sessions s ON s.session_id=p.session_id
                WHERE s.learner_id=? AND p.fingerprint=? AND p.stage_key=? AND p.rowid<?
                AND (p.session_id<>? OR p.rowid<?) LIMIT 1""",
                (learner_id, a["fingerprint"], a["stage_key"], a["sequence"],
                 a["session_id"], attempts[0]["sequence"])).fetchone())
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc):
            raise ValueError("Statistics query exceeded its bounded read deadline; narrow the filters") from None
        raise
    finally:
        db.set_progress_handler(None, 0)
    token = None
    if more:
        last = attempts[-1]
        token = base64.urlsafe_b64encode(json.dumps(dict(v=2, learner=learner_id, query=digest,
            high=high, boundary=boundary_id, after=last["sequence"], anchor=last["attempt_id"]), separators=(",", ":")).encode()).decode()
    return dict(attempts=attempts, sessions=sessions, rules=rules, **related,
                query={**{k: v for k, v in q.items() if k != "cursor"}, "has_more": more,
                       "next_cursor": token, "attempt_ids": ids, "order": "recorded_insertion_order",
                       "high_water_sequence": high},
                resource=dict(detail_bytes_read=used, detail_budget_truncated_attempts=truncated,
                              related_truncation=related_truncated, related_row_cap=4000,
                              related_truncation_counts_are_lower_bounds=True,
                              observation_limit=10000, observation_count=observation_count,
                              truncated_observations=observation_truncated))
