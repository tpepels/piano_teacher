"""Phase 6 bounded cold/warm score and active-session performance.

Real MIDI, actual Coda + Fukuda plan, and canonical Verovio geometry.
This is software CPU/RSS evidence; it cannot establish piano/display latency.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import time

import pytest

from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]
REAL_SCORES = (
    ("moonlight", "Moonlight_Sonata_I.midi", 100),
    ("hanon", "Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi", 500),
)


def _percentile(values, portion):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, max(0, int(len(ordered)*portion+0.99999)-1))]


@pytest.mark.parametrize("label,filename,min_source_notes", REAL_SCORES)
def test_real_score_cold_and_cached_native_pipeline(
        label, filename, min_source_notes, tmp_path):
    path = ROOT / "midi" / filename
    assert path.is_file()
    original = path.read_bytes()
    expected_fingerprint = hashlib.sha256(original).hexdigest()
    engine = PracticeEngine(tmp_path / label, enable_midi=False)
    engine.set_preferences(exercise_strategy="coda-fukuda-midi")
    elapsed = {}
    report = {"score": filename, "sha256":expected_fingerprint,
              "limits": {"cold_load_ms": 45000, "cold_ink_ms": 60000,
                         "warm_ink_ms": 5000, "state_p95_ms": 100,
                         "rss_peak_mb": 1600}}

    def time_call(key, callback):
        started = time.perf_counter()
        value = callback()
        elapsed[key] = round((time.perf_counter()-started)*1000,3)
        return value

    try:
        time_call("cold_load_ms", lambda: engine.load(str(path)))
        assert engine.fingerprint == expected_fingerprint
        assert len(engine.plan.piece.notes) >= min_source_notes
        source_id = engine.plan.identity
        first = time_call("cold_ink_ms", engine.geometry)
        assert first["revision"] == engine.score_revision
        assert first["native_glyphs"] and first["native_note_templates"]
        assert first["native_beams_complete"] and first["native_slurs_complete"]
        semantic = time_call("first_semantic_ms", engine.semantic_score)
        assert semantic["revision"] == first["revision"]
        assert semantic["notes"] and first["notes"]
        # A duplicate native layout response must reuse prepared fragments.
        # Both replies must be isolated, so no consumer can mutate the cache.
        warm = time_call("warm_ink_ms", engine.geometry)
        assert warm["revision"] == first["revision"]
        assert warm["native_glyphs"] == first["native_glyphs"]
        warm["notes"].clear()
        assert engine.geometry()["notes"] == first["notes"]
        report["initial_step"] = {
            "id":source_id,
            "source_notes":len(engine.plan.piece.notes),
            "rendered_notes":len(semantic["notes"]),
            "first_bar":engine.plan.active_phrase.first_bar,
            "last_bar":engine.plan.active_phrase.last_bar}
        assert len(engine.plan.lesson_steps) >= 2
        revision = engine.score_revision
        time_call("select_step_ms", lambda: engine.control("select_step", number=2))
        assert engine.score_revision > revision
        second = time_call("next_stage_ink_ms", engine.geometry)
        assert second["revision"] == engine.score_revision
        assert engine.plan.identity != source_id
        assert second["native_glyphs"]
        # Timed practice and a pause/resume must not reassemble score assets
        # or make state polling proportional to the full imported source.
        engine.control("start")
        samples = []
        for i in range(160):
            started = time.perf_counter()
            snapshot = engine.state()
            samples.append((time.perf_counter()-started)*1000)
            assert snapshot["revision"] == engine.score_revision
        engine.control("pause")
        paused = engine.state()
        assert paused["paused"]
        engine.control("resume")
        assert not engine.state()["paused"]
        report["polls"] = {
            "samples":len(samples),
            "p95_ms":round(_percentile(samples,.95),3),
            "max_ms":round(max(samples),3)}
        report["backend_timings"] = engine.performance_diagnostics()
        captured = engine._capture_session_snapshot()
        assert captured.lesson.lesson_step_count == len(engine.plan.lesson_steps)
        assert len(captured.lesson.lesson_steps) < len(engine.plan.lesson_steps), (
            "A live state response must not copy a full large-score lesson path")
        # ru_maxrss is KiB on Linux, covering interpreter+music21/Verovio.
        report["rss_peak_mb"] = round(resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss / 1024.0,1)
        report["elapsed_ms"] = elapsed
        output = Path(os.environ.get("PIANO_PHASE6_PERF_OUT",str(tmp_path)))
        output.mkdir(parents=True,exist_ok=True)
        (output / (label+".json")).write_text(json.dumps(report,indent=2)+"\n")
        print("PHASE6_PERFORMANCE:",json.dumps(report,sort_keys=True))
        for field in ("cold_load_ms","cold_ink_ms","warm_ink_ms"):
            assert elapsed[field] <= report["limits"][field], (field,report)
        assert report["polls"]["p95_ms"] <= report["limits"]["state_p95_ms"], report
        assert report["rss_peak_mb"] <= report["limits"]["rss_peak_mb"], report
        # The main improvement is avoiding a *second* Verovio fragment
        # compilation. Require a clear reduction on the identical revision.
        assert elapsed["warm_ink_ms"] * 2 < elapsed["cold_ink_ms"] + 1, report
        assert path.read_bytes() == original
    finally:
        engine.listen.cancel()
        engine.db.close()
