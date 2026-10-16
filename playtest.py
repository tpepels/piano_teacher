#!/usr/bin/env python3
"""One-command on-piano playtest: launch, observe, summarize, and pack evidence.

Run from the repository root:
    .venv/bin/python playtest.py
    .venv/bin/python playtest.py --preflight

The program starts the normal UI via run.sh; it does not open a second
MIDI input, change the transport, judge notes, or award mastery.
Raw MIDI pitches/velocities never enter the shareable ZIP.
Physical acoustic and display latency still cannot be measured here.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from scripts.check_grading_session import SessionCapture
from scripts import summarize_hardware_acceptance as acceptance

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
POLL_SECONDS = 0.18
STARTUP_SECONDS = 35.0
PROBE_RETRY_SECONDS = 4.0
PROBE_MAX_SECONDS = 90.0
DIAGNOSTIC_PREFIXES = (
    acceptance.FRAME_PREFIX,
    acceptance.SYNC_PREFIX,
)
# Never include raw notes, key velocities, held pitches, or event timestamps.
SHARE_FILES = ("report.md", "report.json", "graded.json",
               "midi-summary.json", "godot-diagnostics.log", "preflight.log")


def api(path: str, data: dict | None = None, *, timeout: float = 1.8) -> dict:
    body = None if data is None else json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    try:
        with urlopen(Request(BASE + path, body, headers), timeout=timeout) as response:
            result = json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"Backend request {path} failed: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected backend response for {path}")
    return result


def safe_midi_report(raw: dict) -> dict:
    """Preserve aggregate hardware evidence but no identifiable note event."""
    scalar = ("device", "reason", "duration_s", "note_ons", "note_offs",
              "chord_pairs", "velocity_min", "velocity_max", "pedal_changes",
              "orphan_releases", "repeated_attacks", "stored_events",
              "dropped_events")
    result = {key: raw[key] for key in scalar if key in raw}
    result["held_note_count"] = len(raw.get("held_notes", []))
    result["active"] = bool(raw.get("active", False))
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def record_console(stream, output: Path, diagnostics: Path) -> None:
    """Drain the child PIPE even during a fullscreen multi-hour session."""
    with output.open("w", encoding="utf-8") as full, diagnostics.open(
            "w", encoding="utf-8") as metrics:
        for line in stream:
            full.write(line)
            if any(prefix in line for prefix in DIAGNOSTIC_PREFIXES):
                metrics.write(line)
            elif "SCRIPT ERROR" in line or "ERROR:" in line or "Parse Error" in line:
                print(line.rstrip(), file=sys.stderr, flush=True)


class Playtest:
    def __init__(self, output: Path, *, midi_seconds: float = 90.0,
                 preflight: bool = False, request=api, clock=time.monotonic,
                 sleep=time.sleep) -> None:
        self.output = output
        self.midi_seconds = midi_seconds
        self.preflight = preflight
        self.request = request
        self.clock = clock
        self.sleep = sleep
        self.capture: SessionCapture | None = None
        self.probe_started_at: float | None = None
        self.probe_done = midi_seconds <= 0
        self.probe_retry_at = 0.0
        self.probe_report: dict | None = None
        self.probe_snapshot: dict | None = None
        self.probe_last_sample_at = -10.0
        self.probe_device = ""
        self.last_backend_error = ""
        self.capture_notes: list[str] = []
        self.process: subprocess.Popen | None = None
        self.log_thread: threading.Thread | None = None
        self.session_started = self.clock()

    def note(self, value: str) -> None:
        if value not in self.capture_notes:
            self.capture_notes.append(value)
            print(f"[Playtest] {value}", flush=True)

    def _maybe_start_probe(self, state: dict, now: float) -> None:
        if self.probe_done or self.probe_started_at is not None:
            return
        device = str(state.get("device", ""))
        if not device or state.get("running") or now < self.probe_retry_at:
            return
        # Backend accepts the hardware probe ONLY while practice is stopped.
        # It observes the same existing MIDI callback during the first 90s;
        # no second port or separate app is started.
        try:
            self.request("/diagnostics/hardware", {"action": "start"})
        except RuntimeError as exc:
            self.probe_retry_at = now + PROBE_RETRY_SECONDS
            self.note(f"MIDI diagnostic not armed yet: {exc}")
            return
        self.probe_device = device
        self.probe_started_at = now
        self.note(f"MIDI diagnostic armed on {device} for up to {self.midi_seconds:g}s. "
                  "Play notes, a chord and sustain normally.")

    def _finish_probe(self) -> None:
        if self.probe_started_at is None:
            return
        try:
            raw = self.request("/diagnostics/hardware", {"action": "stop"})
            self.probe_report = safe_midi_report(raw)
        except RuntimeError as exc:
            # Closing the UI tears down run.sh's backend immediately.
            # Preserve the most recent aggregate snapshot rather than losing
            # the entire hardware audit at the end of a short session.
            self.probe_report = self.probe_snapshot
            self.note(f"MIDI backend stopped before final probe read: {exc}")
        finally:
            self.probe_done = True
            self.probe_started_at = None
        if self.probe_report is not None:
            write_json(self.output / "midi-summary.json", self.probe_report)
            self.note(f"MIDI diagnostic retained {self.probe_report.get('note_ons', 0)} "
                      "attacks (raw pitches excluded).")

    def _sample_probe(self, now: float) -> None:
        if self.probe_started_at is None or now - self.probe_last_sample_at < 1.0:
            return
        self.probe_last_sample_at = now
        try:
            self.probe_snapshot = safe_midi_report(
                self.request("/diagnostics/hardware"))
        except RuntimeError:
            pass  # A device can vanish between input callback and /state.

    def observe(self, state: dict) -> None:
        now = self.clock()
        # Finish the probe before deciding to record more scored takes. The
        # backend can stop it early on USB loss without damaging the grader.
        if self.probe_started_at is not None:
            if (now - self.probe_started_at >= self.midi_seconds
                    or str(state.get("device", "")) != self.probe_device):
                self._finish_probe()
        self._maybe_start_probe(state, now)
        self._sample_probe(now)

        if self.capture is None:
            if state.get("device") and state.get("mode", "practice") in ("practice", "perform"):
                try:
                    self.capture = SessionCapture(state)
                except RuntimeError as exc:
                    self.note(f"Graded capture unavailable: {exc}")
                else:
                    self.note("Graded practice audit active. Play normally; no extra controls.")
        if self.capture is not None:
            if (state.get("device") and
                    str(state.get("device")) != self.capture.device):
                self.note("Selected MIDI device changed during graded capture; "
                          "review session provenance.")
            self.capture.observe(state)

    def _preflight(self) -> bool:
        if not self.preflight:
            return True
        python = ROOT / ".venv/bin/python"
        if not python.exists():
            python = Path(sys.executable)
        cmd = [str(python), "-m", "pytest", "-q",
               "tests/test_phase79_status.py",
               "tests/test_phase78_stage.py",
               "tests/test_midi_reconnect.py",
               "tests/test_listen_sync.py",
               "tests/test_score_motion_render.py"]
        self.note("Running the practice UI/MIDI/score tests before launching the piano.")
        with (self.output / "preflight.log").open("w", encoding="utf-8") as out:
            result = subprocess.run(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                    check=False)
        if result.returncode != 0:
            self.note("Preflight tests failed; see preflight.log. App not started.")
            return False
        self.note("Preflight tests passed.")
        return True

    def _launch(self) -> None:
        self.note("Launching Piano Teacher with frame and Listen-sync diagnostics.")
        self.process = subprocess.Popen(
            ["bash", str(ROOT / "run.sh"), "--", "--frame-diagnostics",
             "--listen-sync-diagnostics"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", bufsize=1, start_new_session=True)
        assert self.process.stdout is not None
        self.log_thread = threading.Thread(
            target=record_console,
            args=(self.process.stdout, self.output / "godot.log",
                  self.output / "godot-diagnostics.log"), daemon=True)
        self.log_thread.start()

    def _stop_child(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        # run.sh owns a backend child; terminate the entire isolated process
        # group so neither the GUI nor ALSA input is left running after ^C.
        if os.name == "posix":
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                self.process.kill()
            self.process.wait(timeout=5)

    def _collect(self) -> None:
        assert self.process is not None
        started = self.clock()
        online = False
        lost = 0
        while self.process.poll() is None:
            try:
                state = self.request("/state")
            except RuntimeError as exc:
                self.last_backend_error = str(exc)
                if online:
                    lost += 1
                    if lost >= 8:
                        self.note("Backend disconnected; preserving evidence captured so far.")
                        break
                elif self.clock() - started >= STARTUP_SECONDS:
                    self.note(f"Backend not available after startup: {exc}")
                    break
                self.sleep(.2)
                continue
            online = True
            lost = 0
            self.observe(state)
            self.sleep(POLL_SECONDS)
        if not online:
            self.note("No live backend states were captured. Review godot.log.")

    def _finalize(self) -> Path:
        self._finish_probe()
        if self.capture is not None:
            graded = self.capture.report(self.clock() - self.session_started)
            write_json(self.output / "graded.json", graded)
        else:
            graded = None
            self.note("No connected Practice/Perform grading was observed.")
        metrics_path = self.output / "godot-diagnostics.log"
        frames, audio, warnings = acceptance._read_log(
            metrics_path if metrics_path.exists() else None)
        report = acceptance.summarize(self.probe_report, graded,
                                      frames, audio, warnings)
        report["playtest"] = {
            "session_seconds": round(self.clock() - self.session_started, 1),
            "notes": self.capture_notes,
            "physical_latency_measured": False,
        }
        write_json(self.output / "report.json", report)
        human = acceptance.markdown(report)
        if self.capture_notes:
            human += "\n## Session notes\n" + "".join(
                f"- {note}\n" for note in self.capture_notes)
        (self.output / "report.md").write_text(human, encoding="utf-8")
        archive = self.output / "playtest.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name in SHARE_FILES:
                file = self.output / name
                if file.is_file():
                    bundle.write(file, arcname=name)
        return archive

    def run(self) -> int:
        self.output.mkdir(parents=True, exist_ok=True)
        try:
            if not self._preflight():
                return 1
            self._launch()
            self._collect()
        except KeyboardInterrupt:
            self.note("Stopping play session; preparing captured evidence.")
        finally:
            # Probe must be stopped while run.sh still owns the backend.
            self._finish_probe()
            self._stop_child()
            if self.log_thread is not None:
                self.log_thread.join(timeout=5)
            archive = self._finalize()
            self.note(f"One file to share: {archive}")
            self.note(f"Readable summary: {self.output / 'report.md'}")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true",
                        help="Run focused Godot/MIDI/score regressions before playing")
    parser.add_argument("--midi-seconds", type=float, default=PROBE_MAX_SECONDS,
                        help="Live hardware probe window (0 disables; 1-90; default 90)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Evidence directory (default: playtest-results/<timestamp>)")
    args = parser.parse_args(argv)
    if args.midi_seconds != 0 and not 1 <= args.midi_seconds <= PROBE_MAX_SECONDS:
        parser.error("--midi-seconds must be 0 or between 1 and 90")
    if args.output_dir is None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        args.output_dir = ROOT / "playtest-results" / stamp
    try:
        session = Playtest(args.output_dir.resolve(),
                           midi_seconds=args.midi_seconds, preflight=args.preflight)
        return session.run()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Playtest could not start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
