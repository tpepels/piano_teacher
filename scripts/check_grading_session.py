"""Phase 8C: passively capture a real, graded practice session.

Uses only the running Piano Teacher loopback API. It never opens another
MIDI port, modifies the transport, manufactures notes or changes mastery.
The optional JSON report contains aggregate results, NOT raw MIDI pitches.
Actual acoustic/key latency and FPS require separate measurement.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE = "http://127.0.0.1:8765"
MAX_SECONDS = 300.0
POLL_SECONDS = 0.15
MAX_EVENTS = 512
MAX_TRANSITIONS = 128


def state_request() -> dict:
    try:
        with urlopen(BASE + "/state", timeout=3) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise RuntimeError("Backend returned an invalid practice state")
        return result
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError("Cannot reach Piano Teacher. Start ./run.sh first.") from exc


class SessionCapture:
    def __init__(self, first: dict) -> None:
        self.device = str(first.get("device", ""))
        if not self.device:
            raise RuntimeError("Connect a real MIDI piano before graded-session capture.")
        if first.get("mode", "practice") not in ("practice", "perform"):
            raise RuntimeError("Select Practice or Perform before graded-session capture.")
        self.hand_start = str(first.get("hand", ""))
        self.streak_start = int(first.get("streak", 0))
        self.midi_count_start = int(first.get("midi_input_count", 0))
        self.midi_count_end = self.midi_count_start
        self.streak_end = self.streak_start
        self.hand_end = self.hand_start
        self.samples = 0
        self.graded_samples = 0
        self.preview_samples = 0
        self.seen_playing = False
        self.phase_transitions: list[dict] = []
        self.completed_takes: list[dict] = []
        self.event_counts: Counter[str] = Counter()
        self.seen_events: set[tuple[int, int]] = set()
        self.seen_takes: set[int] = set()
        self.last_phase_key: tuple[int, str] | None = None

    def observe(self, snapshot: dict) -> None:
        self.samples += 1
        self.midi_count_end = max(self.midi_count_end,
                                  int(snapshot.get("midi_input_count", self.midi_count_end)))
        self.streak_end = int(snapshot.get("streak", self.streak_end))
        self.hand_end = str(snapshot.get("hand", self.hand_end))
        mode = str(snapshot.get("mode", "practice"))
        phase = str(snapshot.get("phase", ""))
        transport = int(snapshot.get("transport_id", 0))
        preview = bool(snapshot.get("preview_only", False))
        graded = bool(snapshot.get("scoring_available", False)) and not preview \
            and mode in ("practice", "perform")
        self.graded_samples += int(graded)
        self.preview_samples += int(preview)
        self.seen_playing |= phase == "playing" and bool(snapshot.get("running", False))
        phase_key = (transport, phase)
        if phase_key != self.last_phase_key:
            if len(self.phase_transitions) < MAX_TRANSITIONS:
                self.phase_transitions.append({"transport_id": transport, "phase": phase})
            self.last_phase_key = phase_key
        # These are backend-generated MIDI judgments, not a second grader.
        for event in snapshot.get("midi_visual_events", []):
            if not isinstance(event, dict):
                continue
            seq = int(event.get("sequence", -1))
            key = (int(event.get("transport_id", transport)), seq)
            if seq < 0 or key in self.seen_events or key[0] != transport:
                continue
            if len(self.seen_events) >= MAX_EVENTS:
                continue
            self.seen_events.add(key)
            status = str(event.get("status", "unknown"))
            self.event_counts[status] += 1
        result = snapshot.get("take_result")
        if (graded and isinstance(result, dict) and transport not in self.seen_takes
                and phase in ("feedback", "recovering", "loading", "ready")):
            self.seen_takes.add(transport)
            self.completed_takes.append({
                "transport_id": transport, "hand": str(snapshot.get("hand", "")),
                "clean": bool(result.get("clean", False)),
                "correct": int(result.get("correct", 0)),
                "total": int(result.get("total", 0)),
                "streak": int(snapshot.get("streak", 0)),
                "bpm": int(snapshot.get("bpm", 0)),
            })

    def report(self, elapsed: float) -> dict:
        warnings: list[str] = []
        if self.preview_samples:
            warnings.append("Ungraded preview observed: those frames do not count as practice.")
        if not self.graded_samples:
            warnings.append("No scoring-enabled practice state observed.")
        if not self.seen_playing:
            warnings.append("No active playing phase was observed.")
        if not self.completed_takes:
            warnings.append("No completed graded take was observed.")
        if len(self.seen_events) >= MAX_EVENTS:
            warnings.append("Event summary reached its 512-event cap.")
        return {
            "schema": "phase8c-graded-session-v1",
            "device": self.device,
            "duration_s": round(elapsed, 2),
            "samples": self.samples,
            "graded_samples": self.graded_samples,
            "preview_samples": self.preview_samples,
            "midi_attacks_seen": max(0, self.midi_count_end - self.midi_count_start),
            "visual_event_counts": dict(sorted(self.event_counts.items())),
            "phase_transitions": self.phase_transitions,
            "completed_takes": self.completed_takes,
            "clean_takes": sum(int(t["clean"]) for t in self.completed_takes),
            "hand_start": self.hand_start, "hand_end": self.hand_end,
            "streak_start": self.streak_start, "streak_end": self.streak_end,
            "physical_latency_measured": False,
            "audio_latency_measured": False,
            "warnings": warnings,
        }


def run(duration: float, takes: int, output: Path | None = None) -> dict:
    if not 5 <= duration <= MAX_SECONDS:
        raise ValueError("Duration must be between 5 and 300 seconds.")
    if not 1 <= takes <= 30:
        raise ValueError("Take count must be between 1 and 30.")
    capture = SessionCapture(state_request())
    print(f"Listening to graded Practice/Perform on {capture.device}.")
    print("Play a complete warm-up or passage; this command never sends MIDI.")
    start = time.monotonic()
    deadline = start + duration
    while time.monotonic() < deadline:
        capture.observe(state_request())
        if len(capture.completed_takes) >= takes:
            break
        time.sleep(POLL_SECONDS)
    result = capture.report(time.monotonic() - start)
    print(f"Captured {result['midi_attacks_seen']} MIDI attacks, "
          f"{len(result['completed_takes'])} graded takes, "
          f"{result['clean_takes']} clean.")
    if result["warnings"]:
        for warning in result["warnings"]:
            print("Warning: " + warning)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        print(f"Saved aggregate report to {output}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=120,
                        help="Maximum listening time in seconds (5-300)")
    parser.add_argument("--takes", type=int, default=3,
                        help="Stop after this many completed graded takes (default 3)")
    parser.add_argument("--output", type=Path,
                        help="Optional aggregate JSON report; raw pitches excluded")
    args = parser.parse_args(argv)
    try:
        run(args.duration, args.takes, args.output)
    except (ValueError, RuntimeError, KeyboardInterrupt) as exc:
        print(f"Graded-session capture stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
