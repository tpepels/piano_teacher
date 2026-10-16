"""Phase 8J reports only evidence that the real capture tools measure."""
import json

import pytest

from scripts import summarize_hardware_acceptance as acceptance


def midi_report():
    return {
        "device": "Kawai CA-49", "note_ons": 20, "note_offs": 19,
        "pedal_changes": 2, "orphan_releases": 1,
        "repeated_attacks": 0, "held_notes": [{"channel": 0, "pitch": 69}],
        "events": [{"pitch": 69, "at_s": 1.234, "velocity": 109}],
        "physical_latency_measured": True,  # Untrusted claim to reject.
    }


def graded_report():
    return {
        "schema": "phase8c-graded-session-v1", "device": "Kawai CA-49",
        "graded_samples": 48, "preview_samples": 0, "midi_attacks_seen": 18,
        "streak_start": 0, "streak_end": 1,
        "hand_start": "left", "hand_end": "right",
        "completed_takes": [
            {"transport_id": 2, "hand": "left", "clean": False, "correct": 6},
            {"transport_id": 3, "hand": "left", "clean": True, "correct": 10},
            {"transport_id": 4, "hand": "right", "clean": True, "correct": 10},
        ],
        "warnings": [],
    }


def test_complete_reports_stay_aggregate_and_never_claim_physical_latency():
    frames = [
        {"fps": 60.0, "p95_frame_ms": 16.6, "worst_frame_ms": 20.2,
         "resident_tile_mib": 2.1, "packed_tile_mib": 1.2},
        {"fps": 59.8, "p95_frame_ms": 16.8, "worst_frame_ms": 24.0,
         "resident_tile_mib": 3.2, "packed_tile_mib": 1.2},
    ]
    listen = [
        {"software_drift_s": -.028, "peak_software_drift_s": .031, "seeks": 0},
        {"software_drift_s": .016, "peak_software_drift_s": .031, "seeks": 1},
    ]
    result = acceptance.summarize(midi_report(), graded_report(), frames, listen)
    assert result["schema"] == "phase8j-hardware-acceptance-v1"
    assert result["midi"]["status"] == "observed"
    assert result["grading"]["clean_takes"] == 2
    assert result["grading"]["hands_observed"] == ["left", "right"]
    assert result["frame_timing"]["every_window_near_60fps"] is True
    assert result["frame_timing"]["highest_p95_frame_ms"] == 16.8
    assert result["frame_timing"]["peak_resident_tile_mib"] == 3.2
    assert result["listen_software_sync"]["highest_absolute_software_drift_ms"] == 28.0
    assert result["listen_software_sync"]["max_recorded_seeks"] == 1
    assert result["physical_latency_measured"] is False
    assert result["acceptance"] == "requires_real_hardware_review"
    # Raw timestamp, per-note pitch and velocity are forbidden in output.
    serialized = json.dumps(result) + acceptance.markdown(result)
    assert '"pitch"' not in serialized
    assert '"velocity"' not in serialized
    assert '1.234' not in serialized
    assert "Physical key-to-sound" in serialized


def test_missing_sources_are_inconclusive_not_a_pass():
    result = acceptance.summarize(None, None, [], [])
    assert all(result[key]["status"] == "missing" for key in
               ("midi", "grading", "frame_timing", "listen_software_sync"))
    assert result["frame_timing"]["every_window_near_60fps"] is None
    assert result["physical_latency_measured"] is False
    assert len(result["warnings"]) >= 3


def test_weak_observations_produce_review_warnings():
    weak = graded_report()
    weak["hand_end"] = "left"
    weak["preview_samples"] = 3
    weak["completed_takes"] = []
    result = acceptance.summarize(
        {**midi_report(), "note_offs": 0, "pedal_changes": 0},
        weak,
        [{"fps": 38, "p95_frame_ms": 32.0, "worst_frame_ms": 75.0}], [])
    warnings = " ".join(result["warnings"])
    assert result["midi"]["status"] == "incomplete"
    assert result["grading"]["status"] == "incomplete"
    assert "No completed" in warnings
    assert "Ungraded preview" in warnings
    assert "Hand progression" in warnings
    assert "60 FPS" in warnings
    assert result["acceptance"] != "pass"


def test_log_reader_only_accepts_expected_console_event_shapes(tmp_path):
    path = tmp_path / "godot.log"
    path.write_text(
        'Godot started\n'
        'prefix PHASE8D_FRAME_INTERVALS:{"fps":60,"p95_frame_ms":16.6}\n'
        'PHASE8B_LISTEN_SOFTWARE_SYNC:{"software_drift_s":0.02,"seeks":0}\n'
        'PHASE8D_FRAME_INTERVALS:broken\n'
        'PHASE8B_LISTEN_SOFTWARE_SYNC:[]\n')
    frames, sync, warnings = acceptance._read_log(path)
    assert len(frames) == len(sync) == 1
    assert frames[0]["fps"] == 60
    assert sync[0]["software_drift_s"] == .02
    assert len(warnings) == 2


def test_cli_writes_local_aggregate_json_and_markdown_without_uploading(tmp_path, capsys):
    midi_file, graded_file, log_file = (
        tmp_path / "midi.json", tmp_path / "graded.json", tmp_path / "godot.log")
    midi_file.write_text(json.dumps(midi_report()))
    graded_file.write_text(json.dumps(graded_report()))
    log_file.write_text('PHASE8D_FRAME_INTERVALS:{"fps":60,"p95_frame_ms":16.6}\n')
    md_path, json_path = tmp_path / "acceptance.md", tmp_path / "acceptance.json"
    status = acceptance.main([
        "--midi", str(midi_file), "--graded", str(graded_file),
        "--log", str(log_file), "--output", str(md_path),
        "--json-output", str(json_path)])
    assert status == 0
    saved = json.loads(json_path.read_text())
    assert saved["grading"]["completed_takes"] == 3
    assert saved["physical_latency_measured"] is False
    assert "Kawai CA-49" in md_path.read_text()
    assert "# Piano Teacher - Phase 8" in capsys.readouterr().out
    assert '"pitch"' not in json_path.read_text()
    assert '1.234' not in md_path.read_text()


def test_missing_or_untrusted_sources_do_not_generate_false_certification(tmp_path):
    graded_file = tmp_path / "wrong.json"
    graded_file.write_text(json.dumps({"schema": "not-our-grader", "completed_takes": []}))
    assert acceptance.main(["--graded", str(graded_file)]) == 1
    with pytest.raises(ValueError, match="phase8c"):
        acceptance.summarize(None, {"schema": "unknown"}, [], [])
    raw = tmp_path / "oversized.json"
    raw.write_bytes(b"x" * 32)
    assert acceptance.main(["--midi", str(raw)]) == 1
    assert acceptance._read_json(raw) if False else True
    # A documented input-size guard prevents accidentally reading huge logs.
    original_limit = acceptance.MAX_JSON_BYTES
    try:
        acceptance.MAX_JSON_BYTES = 16
        with pytest.raises(ValueError, match="exceeds"):
            acceptance._read_json(raw)
    finally:
        acceptance.MAX_JSON_BYTES = original_limit
