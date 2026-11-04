"""The embedded command boundary exposes measured learning, without HTTP."""
import json

from test_mastery_acceptance_contract import practice_factory, _play
from piano_teacher.inprocess import EngineCommands, OK, INVALID


def test_statistics_command_distinguishes_warning_acceptance_and_strict_clean(practice_factory):
    engine, clock = practice_factory()
    _play(engine, clock, late=(1,))
    commands = EngineCommands(engine=engine)
    code, raw = commands.request("learning.statistics", json.dumps({"fingerprint": engine.fingerprint}))
    assert code == OK, raw
    report = json.loads(raw)
    assert report["assessments"]["accepted"] == 1
    assert report["assessments"]["strict_clean"] == 0
    assert report["assessments"]["accepted_mastery_eligible"] == 1
    assert report["mistakes"]["status_counts"]["late"] == 1
    assert engine.plan.streak == 1
    for payload in ({"fingerprint": ""}, {"fingerprint": 1}, {"unexpected": True}):
        assert commands.request("learning.statistics", json.dumps(payload))[0] == INVALID
