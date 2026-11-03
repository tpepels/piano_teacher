"""Full Verovio prefetch of the next actual MIDI lesson stage."""
from __future__ import annotations

import time

from scripts.smoke_phase0 import make_fixture
from piano_teacher.server import PracticeEngine


def test_full_coda_fukuda_future_score_is_source_bound_and_prepared(tmp_path):
    midi = tmp_path / "real.mid"
    make_fixture(midi)
    source = midi.read_bytes()
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    try:
        engine.load(str(midi))
        assert engine.plan.exercise_strategy.name == "coda-fukuda-midi"
        prior_stage = engine.plan.identity
        prior_revision = engine.score_revision
        selection, number = engine._next_stage_selection()
        assert number == 2
        started = time.monotonic()
        future = engine.next_stage_score()
        while future["status"] == "preparing" and time.monotonic() - started < 40:
            time.sleep(.025)
            future = engine.next_stage_score()
        assert future["status"] == "ready", future
        assert future["stage_key"] == selection.stage_key
        assert future["fingerprint"] == engine.fingerprint
        assert future["revision"] == prior_revision + 1
        assert future["layout"]["native_glyphs"]
        assert future["layout"]["native_note_templates"]
        assert future["layout"]["native_tie_templates"]
        assert future["layout"]["anchors"]
        assert future["model"]["schema"] == "piano-teacher-score-model-v1"
        assert future["model"]["revision"] == prior_revision + 1
        assert future["model"]["notes"]
        assert engine.plan.identity == prior_stage
        assert engine.score_revision == prior_revision
        assert midi.read_bytes() == source
        assert engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key,
            revision=selection.revision)["accepted"]
        assert engine.future_score.adopt(selection) is not None
    finally:
        engine.db.close()
