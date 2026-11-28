"""Shared player-behaviour test support."""

import pytest


@pytest.fixture
def practice_session(tmp_path, monkeypatch):
    from session_inputs import PracticeSession
    sessions = []

    def create(**options):
        session = PracticeSession(tmp_path/str(len(sessions)), monkeypatch, **options)
        sessions.append(session)
        return session

    yield create
    for session in sessions:
        session.close()
