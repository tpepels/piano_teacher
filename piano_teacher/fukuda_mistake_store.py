"""Persistent source-attack mistakes for the MIDI-only Fukuda lesson generator.

Never infer a mistaken source note from a pitch alone: each assessment
references the original imported MIDI attack identity. Persist only on
actual graded performances of the original notes, not simplified stages
or a Listen preview. A newly correct source attack resolves its prior
mistake, so exercises can recover toward the full original score.
"""
from __future__ import annotations

from collections import Counter
import sqlite3

from .practice import Assessment
from .sqlite_transaction import sqlite_atomic


class FukudaMistakeStore:
    def __init__(self,db:sqlite3.Connection):
        self.db=db
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS fukuda_mistakes(
                    fingerprint TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    failures INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL,
                    PRIMARY KEY (fingerprint,source_id)
                )""")

    def problematic(self,fingerprint:str)->frozenset[str]:
        if not fingerprint:
            raise ValueError("Fukuda evidence needs a source MIDI fingerprint")
        return frozenset(row[0] for row in self.db.execute(
            "SELECT source_id FROM fukuda_mistakes WHERE fingerprint=? AND failures>0",
            (fingerprint,)))

    def evidence(self, fingerprint: str) -> dict[str, str]:
        """Return stable per-original-attack error families for course selection."""
        if not fingerprint:
            raise ValueError("Fukuda evidence needs a source MIDI fingerprint")
        return {sid: status for sid, status in self.db.execute(
            "SELECT source_id,status FROM fukuda_mistakes "
            "WHERE fingerprint=? AND failures>0 ORDER BY source_id",
            (fingerprint,))}

    def observe(self,fingerprint:str,result:Assessment)->frozenset[str]:
        """Atomically update the exact source notes scored in one original take."""
        if not fingerprint or not result.notes:
            raise ValueError("Fukuda only accepts completed MIDI assessments")
        ids=[n.note.source_id for n in result.notes]
        if any(not x for x in ids) or len(ids)!=len(set(ids)):
            raise ValueError("Fukuda needs unique original MIDI attack identities")
        with sqlite_atomic(self.db):
            for entry in result.notes:
                sid=entry.note.source_id
                if entry.status=="correct":
                    self.db.execute(
                        "DELETE FROM fukuda_mistakes WHERE fingerprint=? AND source_id=?",
                        (fingerprint,sid))
                else:
                    self.db.execute("""
                        INSERT INTO fukuda_mistakes(fingerprint,source_id,failures,status)
                        VALUES (?,?,1,?)
                        ON CONFLICT(fingerprint,source_id)
                        DO UPDATE SET failures=failures+1,status=excluded.status
                    """,(fingerprint,sid,entry.status))
        return self.problematic(fingerprint)

    def reset(self,fingerprint:str)->None:
        with sqlite_atomic(self.db):
            self.db.execute("DELETE FROM fukuda_mistakes WHERE fingerprint=?",(fingerprint,))
