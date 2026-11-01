"""Expensive authored tempo transformations run once per stage and BPM."""
from types import SimpleNamespace

from piano_teacher.application.tempo_map_cache import TempoMapCache
from piano_teacher.server import PracticeEngine


class Stage:
    def __init__(self, *, result=None):
        self.calls = []
        self.result = object() if result is None else result

    def tempo_map(self, bpm):
        self.calls.append(bpm)
        return self.result


def test_same_stage_and_bpm_reuse_map_for_many_worker_ticks():
    cache = TempoMapCache()
    stage = Stage()
    for _ in range(250):
        assert cache.get(stage, 60) is stage.result
    assert stage.calls == [60]


def test_bpm_and_stage_changes_invalidate_without_stale_mapping():
    cache = TempoMapCache()
    first, second = Stage(), Stage()
    assert cache.get(first, 40) is first.result
    assert cache.get(first, 45) is first.result
    assert cache.get(second, 45) is second.result
    assert cache.get(first, 45) is first.result
    assert first.calls == [40, 45, 45]
    assert second.calls == [45]
    cache.clear()
    assert cache.get(first, 45) is first.result
    assert first.calls == [40, 45, 45, 45]


def test_disabled_tempo_map_is_cached_until_stage_changes():
    cache = TempoMapCache()
    first = Stage(result=None)
    first.result = None
    second = Stage()
    assert cache.get(first, 65) is None
    assert cache.get(first, 65) is None
    assert first.calls == [65]
    assert cache.get(second, 65) is second.result


def test_engine_only_selects_plan_stage_and_mode():
    engine = object.__new__(PracticeEngine)
    engine.tempo_map_cache = TempoMapCache()
    stage = Stage()
    engine.plan = SimpleNamespace(active_stage=stage, bpm=75)
    engine.mode = "practice"
    assert engine._active_tempo_map() is stage.result
    assert engine._active_tempo_map() is stage.result
    engine.mode = "perform"
    assert engine._active_tempo_map() is None
    engine.mode = "listen"
    assert engine._active_tempo_map() is stage.result
    assert stage.calls == [75]
