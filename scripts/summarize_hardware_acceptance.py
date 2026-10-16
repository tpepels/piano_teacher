"""Phase 8J: honest, offline acceptance summary from real device evidence.

Consumes reports produced by the existing loopback MIDI and graded-session
diagnostics plus opt-in Godot console logs. Never opens the MIDI port, records
new notes, mutates progress, or infers key/speaker/display latency.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
import sys

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 16 * 1024 * 1024
FRAME_PREFIX = "PHASE8D_FRAME_INTERVALS:"
SYNC_PREFIX = "PHASE8B_LISTEN_SOFTWARE_SYNC:"


def _read_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"Diagnostic report exceeds {MAX_JSON_BYTES} bytes: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON report object: {path}")
    return data


def _read_log(path: Path | None) -> tuple[list[dict], list[dict], list[str]]:
    if path is None:
        return [], [], []
    if path.stat().st_size > MAX_LOG_BYTES:
        raise ValueError(f"Godot log exceeds {MAX_LOG_BYTES} bytes: {path}")
    frames: list[dict] = []
    sync: list[dict] = []
    warnings: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for prefix, target in ((FRAME_PREFIX, frames), (SYNC_PREFIX, sync)):
            if prefix not in line:
                continue
            try:
                event = json.loads(line.split(prefix, 1)[1].strip())
            except (ValueError, TypeError):
                warnings.append(f"Invalid {prefix[:-1]} JSON on log line {number}")
                continue
            if isinstance(event, dict):
                target.append(event)
            else:
                warnings.append(f"Invalid {prefix[:-1]} object on log line {number}")
    return frames, sync, warnings


def _numeric(value: object, default: float = 0.0) -> float:
    # Invalid or non-finite diagnostic data must not pass thresholds.
    import math
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def summarize(midi: dict | None, graded: dict | None,
              frames: list[dict], sync: list[dict],
              log_warnings: list[str] | None = None) -> dict:
    warnings = list(log_warnings or [])
    midi_result = {
        "status": "missing", "device": None, "note_ons": 0,
        "note_offs": 0, "pedal_changes": 0,
        "orphan_releases": 0, "repeated_attacks": 0,
        "held_notes": 0,
    }
    if midi is not None:
        midi_result.update(
            device=str(midi.get("device", "")),
            note_ons=int(_numeric(midi.get("note_ons"))),
            note_offs=int(_numeric(midi.get("note_offs"))),
            pedal_changes=int(_numeric(midi.get("pedal_changes"))),
            orphan_releases=int(_numeric(midi.get("orphan_releases"))),
            repeated_attacks=int(_numeric(midi.get("repeated_attacks"))),
            held_notes=(max(0, int(_numeric(midi["held_note_count"])))
                        if "held_note_count" in midi
                        else len(midi.get("held_notes", []))
                        if isinstance(midi.get("held_notes", []), list) else 0))
        midi_result["status"] = (
            "observed" if midi_result["note_ons"] > 0 and midi_result["note_offs"] > 0
            else "incomplete")
        if midi_result["status"] == "incomplete":
            warnings.append("MIDI diagnostic did not observe both note attacks and releases.")
        if midi_result["pedal_changes"] == 0:
            warnings.append("MIDI diagnostic contains no sustain-pedal changes.")
        if _numeric(midi.get("dropped_events")) > 0:
            warnings.append("Some raw MIDI trace entries exceeded the bounded capture size.")

    completed: list[dict] = []
    grading_result = {
        "status": "missing", "device": None, "completed_takes": 0,
        "clean_takes": 0, "graded_samples": 0, "preview_samples": 0,
        "midi_attacks_seen": 0, "hands_observed": [],
        "hand_start": None, "hand_end": None,
        "streak_start": 0, "streak_end": 0,
    }
    if graded is not None:
        if graded.get("schema") != "phase8c-graded-session-v1":
            raise ValueError("Expected a phase8c-graded-session-v1 report")
        submitted = graded.get("completed_takes", [])
        if not isinstance(submitted, list):
            raise ValueError("Invalid completed_takes in graded session")
        completed = [item for item in submitted if isinstance(item, dict)]
        grading_result.update(
            device=str(graded.get("device", "")),
            completed_takes=len(completed),
            clean_takes=sum(bool(item.get("clean", False)) for item in completed),
            graded_samples=int(_numeric(graded.get("graded_samples"))),
            preview_samples=int(_numeric(graded.get("preview_samples"))),
            midi_attacks_seen=int(_numeric(graded.get("midi_attacks_seen"))),
            hands_observed=sorted({str(item.get("hand", ""))
                                   for item in completed if item.get("hand")}),
            hand_start=str(graded.get("hand_start", "")),
            hand_end=str(graded.get("hand_end", "")),
            streak_start=int(_numeric(graded.get("streak_start"))),
            streak_end=int(_numeric(graded.get("streak_end"))))
        grading_result["status"] = (
            "observed" if completed and grading_result["graded_samples"] > 0
            else "incomplete")
        if not completed:
            warnings.append("No completed, backend-graded practice take was captured.")
        if grading_result["preview_samples"]:
            warnings.append("Ungraded preview was present; it is excluded from scored results.")
        if grading_result["hand_start"] == grading_result["hand_end"]:
            warnings.append("Hand progression was not demonstrated in this capture.")
        for entry in graded.get("warnings", []):
            if isinstance(entry, str) and entry not in warnings:
                warnings.append(entry)

    fps_values = [_numeric(f.get("fps"), -1) for f in frames if isinstance(f, dict)]
    fps_values = [v for v in fps_values if v > 0]
    p95_values = [_numeric(f.get("p95_frame_ms"), -1) for f in frames
                  if isinstance(f, dict)]
    p95_values = [v for v in p95_values if v > 0]
    worst_values = [_numeric(f.get("worst_frame_ms"), -1) for f in frames
                    if isinstance(f, dict)]
    worst_values = [v for v in worst_values if v > 0]
    resident = [_numeric(f.get("resident_tile_mib"), -1) for f in frames
                if isinstance(f, dict)]
    resident = [v for v in resident if v >= 0]
    packed = [_numeric(f.get("packed_tile_mib"), -1) for f in frames
              if isinstance(f, dict)]
    packed = [v for v in packed if v >= 0]
    frame_result = {
        "status": "observed" if fps_values and p95_values else "missing",
        "windows": min(len(fps_values), len(p95_values)),
        "median_fps": round(median(fps_values), 1) if fps_values else None,
        "lowest_fps": round(min(fps_values), 1) if fps_values else None,
        "highest_p95_frame_ms": round(max(p95_values), 1) if p95_values else None,
        "worst_frame_ms": round(max(worst_values), 1) if worst_values else None,
        "peak_resident_tile_mib": round(max(resident), 2) if resident else None,
        "peak_packed_tile_mib": round(max(packed), 2) if packed else None,
        "every_window_near_60fps": (
            min(fps_values) >= 59.0 and max(p95_values) <= 17.0
            if fps_values and p95_values else None),
    }
    if not fps_values:
        warnings.append("No on-device Godot frame-rate measurements were supplied.")
    elif not frame_result["every_window_near_60fps"]:
        warnings.append("At least one measured window missed the 60 FPS / 17 ms review target.")

    drifts = [abs(_numeric(s.get("software_drift_s"))) for s in sync
              if isinstance(s, dict) and s.get("software_drift_s") is not None]
    sync_result = {
        "status": "observed" if drifts else "missing",
        "samples": len(drifts),
        "highest_absolute_software_drift_ms": (
            round(max(drifts) * 1000, 1) if drifts else None),
        "max_recorded_seeks": (
            max(int(_numeric(s.get("seeks"))) for s in sync
                if isinstance(s, dict)) if sync else None),
        "physical_latency_measured": False,
    }
    if not drifts:
        warnings.append("No Listen software audio-sync measurements were supplied.")

    if midi_result["device"] and grading_result["device"] and (
            midi_result["device"] != grading_result["device"]):
        warnings.append("MIDI and graded reports name different devices; verify session provenance.")

    # The supported inputs categorically cannot measure acoustic or physical
    # latency, even if their originating JSON contains an incorrect flag.
    warnings.append(
        "Physical key-to-sound, speaker-to-ear and display latency remain unmeasured.")
    return {
        "schema": "phase8j-hardware-acceptance-v1",
        "midi": midi_result,
        "grading": grading_result,
        "frame_timing": frame_result,
        "listen_software_sync": sync_result,
        "physical_latency_measured": False,
        "acceptance": "requires_real_hardware_review",
        "warnings": list(dict.fromkeys(warnings)),
    }


def markdown(report: dict) -> str:
    midi, graded, frame, audio = (
        report["midi"], report["grading"], report["frame_timing"],
        report["listen_software_sync"])
    lines = [
        "# Piano Teacher - Phase 8 hardware acceptance",
        "",
        "**Status:** Real instrument review required; physical latency has not been measured.",
        "",
        "## MIDI input",
        f"- Evidence: {midi['status']}",
        f"- Device: {midi['device'] or 'not supplied'}",
        f"- Attacks / releases: {midi['note_ons']} / {midi['note_offs']}",
        f"- Sustain changes: {midi['pedal_changes']}",
        f"- Orphan releases / repeated attacks: {midi['orphan_releases']} / {midi['repeated_attacks']}",
        "",
        "## Graded practice",
        f"- Evidence: {graded['status']}",
        f"- Completed / clean takes: {graded['completed_takes']} / {graded['clean_takes']}",
        f"- Graded / preview samples: {graded['graded_samples']} / {graded['preview_samples']}",
        f"- Hands observed: {', '.join(graded['hands_observed']) or 'none'}",
        f"- Hand start / end: {graded['hand_start'] or '-'} / {graded['hand_end'] or '-'}",
        "",
        "## Frame intervals (Godot)",
        f"- Evidence: {frame['status']}; sampled windows: {frame['windows']}",
        f"- Median / lowest FPS: {frame['median_fps']} / {frame['lowest_fps']}",
        f"- Highest p95 / worst frame: {frame['highest_p95_frame_ms']} / {frame['worst_frame_ms']} ms",
        f"- Peak raw resident / packed tile data: {frame['peak_resident_tile_mib']} / {frame['peak_packed_tile_mib']} MiB",
        "",
        "## Listen audio synchronization (software only)",
        f"- Evidence: {audio['status']}; samples: {audio['samples']}",
        f"- Highest observed absolute drift: {audio['highest_absolute_software_drift_ms']} ms",
        f"- Maximum recorded corrective seeks: {audio['max_recorded_seeks']}",
        "",
        "## Open checks",
        *[f"- {warning}" for warning in report["warnings"]],
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--midi", type=Path, help="Output of check_hardware_session.py")
    parser.add_argument("--graded", type=Path, help="Output of check_grading_session.py")
    parser.add_argument("--log", type=Path, help="Godot terminal output with frame/sync records")
    parser.add_argument("--output", type=Path, help="Write human-readable Markdown")
    parser.add_argument("--json-output", type=Path, help="Write aggregate machine-readable JSON")
    args = parser.parse_args(argv)
    if not any((args.midi, args.graded, args.log)):
        parser.error("Provide at least one real diagnostic input")
    try:
        frames, audio, warnings = _read_log(args.log)
        result = summarize(_read_json(args.midi), _read_json(args.graded),
                           frames, audio, warnings)
        rendered = markdown(result)
        for path, text in ((args.output, rendered),
                           (args.json_output, json.dumps(result, indent=2) + "\n")):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
        print(rendered)
        return 0
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        print(f"Could not summarize acceptance evidence: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
