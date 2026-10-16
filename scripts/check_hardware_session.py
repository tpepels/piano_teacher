"""Phase 8: capture a real USB MIDI session through the running Piano Teacher.

This is a diagnostic, not a latency-calibration algorithm. The callback clock
cannot measure how long the keyboard electronics or speakers took to respond.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8765"


def request(path: str, data: dict | None = None) -> dict:
    payload = None if data is None else json.dumps(data).encode()
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    try:
        with urlopen(Request(BASE + path, payload, headers), timeout=5) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            detail = json.load(exc).get("error", str(exc))
        except (ValueError, OSError):
            detail = str(exc)
        raise RuntimeError(detail) from exc
    except URLError as exc:
        raise RuntimeError("Piano Teacher backend is not running. Start ./run.sh first.") from exc


def run(duration: float, output: Path | None = None) -> dict:
    state = request("/state")
    if not state.get("device"):
        raise RuntimeError("Connect your piano in Settings > Piano input first.")
    if state.get("running"):
        raise RuntimeError("Stop the current practice attempt before diagnostics.")
    print(f"Connected MIDI piano: {state['device']}")
    print("When recording starts: play single notes softly and loudly,")
    print("play a three-note chord, repeat a key, and press/release sustain.")
    print("This captures MIDI arrival timing, NOT physical/audio latency.")
    request("/diagnostics/hardware", {"action": "start"})
    try:
        finish = time.monotonic() + duration
        while time.monotonic() < finish:
            time.sleep(min(0.5, max(0.01, finish - time.monotonic())))
            snapshot = request("/diagnostics/hardware")
            if not snapshot.get("active"):
                break
            print(f"\rNotes on/off: {snapshot['note_ons']}/{snapshot['note_offs']} "
                  f"chord pairs: {snapshot['chord_pairs']} "
                  f"pedal changes: {snapshot['pedal_changes']}  ", end="", flush=True)
    finally:
        report = request("/diagnostics/hardware", {"action": "stop"})
        print()
    print(f"Captured {report['note_ons']} note attacks, "
          f"{report['note_offs']} releases and {report['pedal_changes']} pedal changes.")
    print(f"Orphan releases: {report['orphan_releases']}; "
          f"repeated attacks without release: {report['repeated_attacks']}; "
          f"keys still held: {len(report['held_notes'])}.")
    if report["dropped_events"]:
        print(f"Warning: {report['dropped_events']} events exceeded the bounded trace.")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Saved local diagnostic report to {output}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=25,
                        help="Seconds to collect (5-90; default: 25)")
    parser.add_argument("--output", type=Path,
                        help="Optional local JSON report (contains raw MIDI note pitches)")
    args = parser.parse_args(argv)
    if not (5 <= args.duration <= 90):
        parser.error("--duration must be between 5 and 90 seconds")
    try:
        run(args.duration, args.output)
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"Hardware check stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
