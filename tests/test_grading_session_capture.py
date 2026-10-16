"""Phase 8C records authoritative grader output without opening MIDI."""
import json

import pytest

from scripts import check_grading_session as diag


def snapshot(*, phase="ready", sequence=(), transport=7, take=None,
             device="Kawai CA-49", mode="practice", preview=False,
             input_count=0, streak=0, hand="left"):
    return {
        "device": device, "mode": mode, "phase": phase,
        "transport_id": transport, "scoring_available": bool(device) and not preview,
        "preview_only": preview, "running": phase in ("count_in", "playing"),
        "midi_input_count": input_count, "streak": streak, "hand": hand,
        "bpm": 60, "take_result": take,
        "midi_visual_events": list(sequence),
    }


def test_capture_deduplicates_polled_events_and_authoritative_take_results():
    capture = diag.SessionCapture(snapshot(input_count=11))
    chord = [
        {"sequence": 1, "transport_id": 7, "status": "on_time",
         "pitch": 60, "source_id": "note-a"},
        {"sequence": 2, "transport_id": 7, "status": "early",
         "pitch": 64, "source_id": "note-b"},
    ]
    playing = snapshot(phase="playing", sequence=chord, input_count=13)
    for _ in range(4):
        capture.observe(playing)
    graded = snapshot(phase="feedback", sequence=chord, input_count=13,
                      take={"clean": True, "correct": 2, "total": 2}, streak=1)
    for _ in range(3):
        capture.observe(graded)
    result = capture.report(1.3)
    assert result["visual_event_counts"] == {"early": 1, "on_time": 1}
    assert result["midi_attacks_seen"] == 2
    assert result["clean_takes"] == 1
    assert len(result["completed_takes"]) == 1
    assert result["completed_takes"][0]["correct"] == 2
    assert result["streak_end"] == 1
    assert result["physical_latency_measured"] is False
    assert result["audio_latency_measured"] is False
    # The actual source IDs and individual pitches are intentionally absent.
    serialized = json.dumps(result)
    assert "note-a" not in serialized and '"pitch"' not in serialized


def test_ungraded_preview_never_counts_success():
    capture = diag.SessionCapture(snapshot())
    capture.observe(snapshot(phase="playing", input_count=12, preview=True,
        sequence=[{"sequence": 1, "transport_id": 7, "status": "on_time"}]))
    capture.observe(snapshot(phase="feedback", preview=True,
        take={"clean": True, "correct": 4, "total": 4}, streak=0))
    result = capture.report(5)
    assert not result["completed_takes"]
    assert result["visual_event_counts"] == {}
    assert result["preview_samples"] == 2
    assert result["warnings"]


@pytest.mark.parametrize("first", [
    snapshot(device=""),
    snapshot(mode="listen"),
    snapshot(mode="learn"),
])
def test_acceptance_capture_rejects_unscorable_setup(first):
    with pytest.raises(RuntimeError):
        diag.SessionCapture(first)


def test_runtime_polling_reads_live_backend_and_stops_after_real_take(monkeypatch, tmp_path):
    states = iter([
        snapshot(input_count=5),
        snapshot(phase="count_in", input_count=5),
        snapshot(phase="playing", input_count=7),
        snapshot(phase="feedback", input_count=7, streak=1,
                 take={"clean": True, "correct": 2, "total": 2}),
    ])
    monkeypatch.setattr(diag, "state_request", lambda: next(states))
    timeline = iter([100.0, 100.0, 100.15, 100.3, 100.35])
    monkeypatch.setattr(diag.time, "monotonic", lambda: next(timeline, 100.4))
    monkeypatch.setattr(diag.time, "sleep", lambda _: None)
    path = tmp_path / "graded.json"
    result = diag.run(duration=5, takes=1, output=path)
    assert len(result["completed_takes"]) == 1
    assert result["clean_takes"] == 1
    assert result["midi_attacks_seen"] == 2
    assert json.loads(path.read_text()) == result
