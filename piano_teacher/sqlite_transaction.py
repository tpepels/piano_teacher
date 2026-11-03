"""SQLite write boundary shared by progress, adaptation and learner evidence.

Nested writes use SAVEPOINT rather than independently committing the connection.
A completed assessment publishes all durable effects or none of them.
"""
from __future__ import annotations

from contextlib import contextmanager
from itertools import count
import sqlite3

_tokens = count()


@contextmanager
def sqlite_atomic(db: sqlite3.Connection):
    name = f"piano_write_{next(_tokens)}"
    db.execute(f"SAVEPOINT {name}")
    try:
        yield
    except BaseException:
        db.execute(f"ROLLBACK TO SAVEPOINT {name}")
        db.execute(f"RELEASE SAVEPOINT {name}")
        raise
    else:
        db.execute(f"RELEASE SAVEPOINT {name}")
