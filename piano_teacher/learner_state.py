"""Persist preparation and trouble separately from graded lesson mastery.

The exact LearningPlan stage key already identifies the source event content,
hand and variant. Local two-bar units additionally retain their source indices
so a stale guided cursor cannot silently skip changed notes. Nothing here
writes the existing sessions/mastery tables or changes the selected plan.
"""
from __future__ import annotations

import json
import math
from numbers import Real
import sqlite3

from .exercise_generator import ExerciseVariant
from .measure_grid import phrase_grid, two_bar_chunks


def guided_units(variant: ExerciseVariant, boundaries: tuple[float, ...] = ()) -> tuple[dict, ...]:
    """Source-grid ideas with attacks; timed Practice retains all silent bars."""
    phrase = variant.phrase
    grid = phrase_grid(phrase, boundaries)
    if len(variant.notes) != len(variant.source_indices):
        raise ValueError("Each active note needs its source index")
    units = []
    for start, end in two_bar_chunks(grid):
        indices = [index for note, index in zip(variant.notes, variant.source_indices)
                   if start-1e-7 <= note.start-phrase.start < end-1e-7]
        if not indices:
            continue
        first, last = grid.index(start), grid.index(end)
        units.append({"first_bar": phrase.first_bar+first, "last_bar": phrase.first_bar+last-1,
                      "start_beat": start, "end_beat": end,
                      "source_indices": indices, "required_notes": len(indices)})
    return tuple(units)


def _same_unit(left: dict, right: dict) -> bool:
    return all(left.get(field) == right.get(field)
               for field in ("start_beat", "end_beat", "source_indices"))


def next_guided_unit(variant: ExerciseVariant, boundaries: tuple[float, ...] = (),
                     state: dict | None = None) -> dict | None:
    """Resume one exact idea, then prepare remaining ideas before full rhythm.

    None means all current source ideas were prepared. It grants no timed
    credit. A deliberately saved resume can revisit an already prepared idea.
    """
    units = guided_units(variant, boundaries)
    state = state or {}
    resume = state.get("resume_unit")
    if isinstance(resume, dict):
        match = next((unit for unit in units if _same_unit(unit, resume)), None)
        if match is not None:
            return match
    completed = state.get("completed_units", [])
    return next((unit for unit in units
                 if not any(isinstance(saved, dict) and _same_unit(unit, saved) for saved in completed)), None)


def placement_candidate(plan):
    """Offer the current hand's original notes as an optional placement start.

    This is a suggestion, never a skill inference or automatic exemption. The
    caller must explicitly select it and record skipped/placed stages. The
    original stage still needs its normal three clean full target-speed takes.
    Existing generator rules already omit nearly redundant simplified stages.
    """
    if plan.active_variant.level == "original":
        return None
    return next((step for step in plan.lesson_steps
                 if step.exercise_index == plan.index and step.hand == plan.hand
                 and step.level == "original"), None)


def _identity(fingerprint: str, stage_key: str):
    if not all(isinstance(value, str) and value.strip() for value in (fingerprint, stage_key)):
        raise ValueError("A saved learner state needs a piece fingerprint and exact stage key")


def _unit(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("A guided unit must contain source range and note identities")
    first, last = value.get("first_bar"), value.get("last_bar")
    if (not isinstance(first, int) or isinstance(first, bool) or first < 1
            or not isinstance(last, int) or isinstance(last, bool) or last < first):
        raise ValueError("A guided unit needs valid source bar numbers")
    start, end = value.get("start_beat"), value.get("end_beat")
    if (any(isinstance(beat, bool) or not isinstance(beat, Real) or not math.isfinite(beat)
            for beat in (start, end)) or not 0 <= start < end):
        raise ValueError("A guided unit needs a finite positive local beat range")
    indices = value.get("source_indices")
    if (not isinstance(indices, (tuple, list)) or not indices
            or any(not isinstance(i, int) or isinstance(i, bool) or i < 0 for i in indices)
            or len(set(indices)) != len(indices) or value.get("required_notes") != len(indices)):
        raise ValueError("A guided unit needs distinct source indices for each required note")
    return {"first_bar": first, "last_bar": last, "start_beat": float(start), "end_beat": float(end),
            "source_indices": list(indices), "required_notes": len(indices)}


def _json(value) -> str:
    return json.dumps(value, separators=(',', ':'), sort_keys=True, allow_nan=False)


class LearnerStateStore:
    """Use the engine's SQLite connection; caller retains connection ownership."""
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS learner_stages (
                fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
                resume_unit TEXT, skip_status TEXT NOT NULL DEFAULT 'active'
                    CHECK(skip_status IN ('active','skipped','placed')),
                skip_reason TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(fingerprint,stage_key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS learner_units (
                fingerprint TEXT NOT NULL, stage_key TEXT NOT NULL,
                start_beat REAL NOT NULL, end_beat REAL NOT NULL, unit TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0, assisted INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
                pitches TEXT NOT NULL DEFAULT '[]', resolved INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(fingerprint,stage_key,start_beat,end_beat))""")

    def _ensure_stage(self, fingerprint, stage_key):
        self.db.execute("INSERT OR IGNORE INTO learner_stages(fingerprint,stage_key) VALUES (?,?)",
                        (fingerprint, stage_key))

    def _ensure_unit(self, fingerprint, stage_key, unit):
        self._ensure_stage(fingerprint, stage_key)
        values = (fingerprint, stage_key, unit['start_beat'], unit['end_beat'], _json(unit))
        # A changed binding must not relabel old completion as new learning.
        self.db.execute("""DELETE FROM learner_units WHERE fingerprint=? AND stage_key=?
                           AND start_beat=? AND end_beat=? AND unit<>?""", values)
        self.db.execute("""INSERT OR IGNORE INTO learner_units(fingerprint,stage_key,start_beat,end_beat,unit)
                           VALUES (?,?,?,?,?)""", values)

    def read(self, fingerprint: str, stage_key: str) -> dict:
        _identity(fingerprint, stage_key)
        stage = self.db.execute("SELECT resume_unit,skip_status,skip_reason FROM learner_stages WHERE fingerprint=? AND stage_key=?",
                                (fingerprint, stage_key)).fetchone()
        rows = self.db.execute("""SELECT unit,completed,failures,errors,pitches,resolved FROM learner_units
                                  WHERE fingerprint=? AND stage_key=? ORDER BY start_beat,end_beat""",
                               (fingerprint, stage_key)).fetchall()
        return {"resume_unit": json.loads(stage[0]) if stage and stage[0] else None,
                "completed_units": [json.loads(row[0]) for row in rows if row[1]],
                "trouble_units": [{**json.loads(row[0]), "failures": row[2], "errors": row[3],
                                   "pitches": json.loads(row[4]), "resolved": False}
                                  for row in rows if row[2] and not row[5]],
                "skip_status": stage[1] if stage else "active", "skip_reason": stage[2] if stage else ""}

    def save_resume(self, fingerprint: str, stage_key: str, unit: dict):
        _identity(fingerprint, stage_key)
        unit = _unit(unit)
        with self.db:
            self._ensure_stage(fingerprint, stage_key)
            self.db.execute("UPDATE learner_stages SET resume_unit=? WHERE fingerprint=? AND stage_key=?",
                            (_json(unit), fingerprint, stage_key))

    def complete_unit(self, fingerprint: str, stage_key: str, unit: dict, *, assisted: bool = False):
        _identity(fingerprint, stage_key)
        unit = _unit(unit)
        with self.db:
            self._ensure_unit(fingerprint, stage_key, unit)
            self.db.execute("""UPDATE learner_units SET completed=1,assisted=max(assisted,?)
                               WHERE fingerprint=? AND stage_key=? AND start_beat=? AND end_beat=?""",
                            (int(bool(assisted)), fingerprint, stage_key, unit['start_beat'], unit['end_beat']))
            self.db.execute("""UPDATE learner_stages SET resume_unit=NULL
                               WHERE fingerprint=? AND stage_key=? AND resume_unit=?""",
                            (fingerprint, stage_key, _json(unit)))

    def record_trouble(self, fingerprint: str, stage_key: str, unit: dict, *, errors: int, pitches=()):
        _identity(fingerprint, stage_key)
        unit = _unit(unit)
        if not isinstance(errors, int) or isinstance(errors, bool) or errors <= 0:
            raise ValueError("Trouble must describe a positive number of settled errors")
        if (not isinstance(pitches, (tuple, list, set))
                or any(not isinstance(pitch, int) or isinstance(pitch, bool) or not 0 <= pitch <= 127 for pitch in pitches)):
            raise ValueError("Trouble pitches must be valid MIDI note numbers")
        with self.db:
            self._ensure_unit(fingerprint, stage_key, unit)
            key = (fingerprint, stage_key, unit['start_beat'], unit['end_beat'])
            failures, old_pitches, resolved = self.db.execute("""SELECT failures,pitches,resolved FROM learner_units
                WHERE fingerprint=? AND stage_key=? AND start_beat=? AND end_beat=?""", key).fetchone()
            combined = sorted(set(pitches) | (set() if resolved else set(json.loads(old_pitches))))
            self.db.execute("""UPDATE learner_units SET failures=?,errors=?,pitches=?,resolved=0
                               WHERE fingerprint=? AND stage_key=? AND start_beat=? AND end_beat=?""",
                            (1 if resolved else failures+1, errors, _json(combined), *key))

    def resolve_trouble(self, fingerprint: str, stage_key: str, unit: dict | None = None):
        """Call only after evidence of improvement, e.g. a clean full take."""
        _identity(fingerprint, stage_key)
        unit = _unit(unit) if unit is not None else None
        with self.db:
            query = "UPDATE learner_units SET resolved=1 WHERE fingerprint=? AND stage_key=?"
            values = (fingerprint, stage_key)
            if unit is not None:
                query += " AND start_beat=? AND end_beat=?"
                values += (unit['start_beat'], unit['end_beat'])
            self.db.execute(query, values)

    def trouble_for_piece(self, fingerprint: str, *, include_resolved: bool = False) -> list[dict]:
        _identity(fingerprint, "piece-query")
        rows = self.db.execute("""SELECT stage_key,unit,failures,errors,pitches,resolved FROM learner_units
                                  WHERE fingerprint=? AND failures>0 ORDER BY stage_key,start_beat,end_beat""",
                               (fingerprint,)).fetchall()
        return [{"stage_key": row[0], **json.loads(row[1]), "failures": row[2], "errors": row[3],
                 "pitches": json.loads(row[4]), "resolved": bool(row[5])}
                for row in rows if include_resolved or not row[5]]

    def mark_skipped(self, fingerprint: str, stage_key: str, *, reason: str, status: str = "skipped"):
        _identity(fingerprint, stage_key)
        if status not in ("skipped", "placed") or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Skip/placement needs an explicit skipped or placed status and a reason")
        with self.db:
            self._ensure_stage(fingerprint, stage_key)
            self.db.execute("UPDATE learner_stages SET skip_status=?,skip_reason=? WHERE fingerprint=? AND stage_key=?",
                            (status, reason.strip(), fingerprint, stage_key))

    def reactivate(self, fingerprint: str, stage_key: str):
        _identity(fingerprint, stage_key)
        with self.db:
            self.db.execute("UPDATE learner_stages SET skip_status='active',skip_reason='' WHERE fingerprint=? AND stage_key=?",
                            (fingerprint, stage_key))
