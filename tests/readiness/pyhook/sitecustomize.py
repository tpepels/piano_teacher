"""R1 readiness sweep: an in-process simulated pianist for the real app.

Loaded by the embedded CPython only when tests/readiness/pyhook is on
PYTHONPATH and R1_SWEEP_DIR is set (tests/readiness/run_sweep.sh does both).
It changes no product behaviour. It:

* opens a virtual ALSA MIDI output port and selects it as the MIDI piano,
  exactly as a user does in Settings (engine.connect), so every key goes
  through the real rtmidi input callback, MidiConnection and grading;
* plays each graded take from the engine's own schedule (run_at,
  play_from_beat, tempo map, active phrase and hand) with a per-note plan
  chosen by the Godot harness through ``control.json``: hit, late,
  early_onset, early_release, missed, wrong;
* logs the plan, every key sent, and every feedback event Python publishes
  (observer wrapper around FeedbackEventLog.publish) to JSONL files.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback

_DIR = os.environ.get("R1_SWEEP_DIR", "")


def _log(name: str, record: dict) -> None:
    try:
        with open(os.path.join(_DIR, name), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


class Performer(threading.Thread):
    # Unique per process: concurrent sweeps (CI, other agents) must never
    # connect to each other's virtual keyboard.
    CLIENT = f"R1Sweep{os.getpid()}"
    PORT = "R1 Sweep Keyboard"

    def __init__(self, engine):
        super().__init__(name="r1-performer", daemon=True)
        self.engine = engine
        self.out = None
        self.take = None          # transport_id of the scheduled take
        self.events: list[dict] = []
        self.held: dict[int, int] = {}
        self.was_paused = False
        self.dumped: set = set()

    # ---- plan -------------------------------------------------------
    def _control(self) -> dict:
        try:
            with open(os.path.join(_DIR, "control.json"), encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {"plan": "mixed"}

    def _schedule(self) -> None:
        from piano_teacher.grading_tolerance import onset_tolerance
        from piano_teacher.lesson_settings import SETTINGS
        e = self.engine
        control = self._control()
        plan_name = str(control.get("plan", "mixed"))
        phrase = e.plan.active_phrase
        hand = e.plan.hand
        bpm = float(e.plan.bpm)
        tempo = e._active_tempo_map()
        from_beat = float(e.visual_transport.play_from_beat)

        def sec(beat: float) -> float:
            return tempo.seconds_at(beat) if tempo is not None else beat * 60.0 / bpm

        def spb(beat: float) -> float:
            return 60.0 / (tempo.bpm_at(beat) if tempo is not None else bpm)

        origin = sec(from_beat)
        notes = sorted((n for n in phrase.notes if hand == "both" or n.hand == hand),
                       key=lambda n: (n.start, n.pitch))
        rows = []
        for n in notes:
            b = n.start - phrase.start
            if b < from_beat - 1e-6:
                continue
            on = sec(b) - origin
            off = sec(min(n.end, phrase.end) - phrase.start) - origin
            rows.append({"note": n, "beat": b, "on": on, "off": off, "spb": spb(b)})
        # Every take of a mixed plan contains each planned mistake once,
        # spread through the passage; all other notes are clean hits.
        targets = ["late", "early_onset", "early_release", "missed", "wrong"]
        if len(rows) < 15:
            # Short passages: three mistakes per take, alternating sets.
            targets = (["late", "early_onset", "missed"] if e.transport_id % 2
                       else ["early_release", "wrong", "late"])
        stride = max(2, len(rows) // (len(targets) + 1))
        wanted: dict[int, str] = {}
        if plan_name == "mixed":
            for i, name in enumerate(targets):
                wanted[1 + i * stride] = name
        carry: list[str] = []
        planned = []
        events = []
        for k, row in enumerate(rows):
            n = row["note"]
            dur = row["off"] - row["on"]
            allowed = onset_tolerance(row["spb"])
            window = max(SETTINGS.grading_match_window_min_seconds,
                         SETTINGS.grading_match_window_beats * row["spb"])
            shift = (allowed + window) / 2.0
            outcome = "hit"
            if k in wanted:
                carry.append(wanted[k])
            if plan_name == "silent":
                outcome = "missed"
            # Neighbours of the same pitch constrain timing shifts.
            same = [r for r in rows if r is not row and r["note"].pitch == n.pitch]
            prev_off = max((r["off"] for r in same if r["on"] < row["on"]), default=-1e9)
            next_on = min((r["on"] for r in same if r["on"] > row["on"]), default=1e9)
            def eligible(name: str) -> bool:
                if name == "early_onset":
                    return row["on"] - shift > prev_off + 0.05
                if name == "late":
                    return row["off"] + shift < next_on - 0.05
                if name == "early_release":
                    return dur >= 0.45
                return True
            for name in list(carry):
                if eligible(name):
                    outcome = name
                    carry.remove(name)
                    break
            played_pitch = n.pitch
            if outcome == "wrong":
                near = {r["note"].pitch for r in rows if abs(r["on"] - row["on"]) <= window + 0.05}
                for delta in (1, -1, 2, -2, 3, -3):
                    if n.pitch + delta not in near and 21 <= n.pitch + delta <= 108:
                        played_pitch = n.pitch + delta
                        break
                else:
                    outcome = "missed"
            on, off = row["on"], row["off"]
            release_gap = min(0.03, max(0.0, dur * 0.1))
            if outcome == "late":
                on, off = on + shift, off + shift - release_gap
            elif outcome == "early_onset":
                on, off = on - shift, off - release_gap
            elif outcome == "early_release":
                off = on + max(0.05, 0.15 * dur)
            else:
                off = off - release_gap
            planned.append({"k": k, "source_id": n.source_id, "pitch": n.pitch,
                            "played_pitch": played_pitch, "beat": row["beat"],
                            "expected_on": row["on"], "expected_off": row["off"],
                            "outcome": outcome, "shift": shift})
            if outcome != "missed":
                events.append({"at": on, "on": True, "pitch": played_pitch,
                               "source_id": n.source_id, "k": k})
                events.append({"at": max(on + 0.02, off), "on": False, "pitch": played_pitch,
                               "source_id": n.source_id, "k": k})
        events.sort(key=lambda ev: (ev["at"], ev["on"]))
        self.events = events
        _log("performer.jsonl", {
            "type": "take", "transport_id": e.transport_id, "plan": plan_name,
            "label": control.get("label", ""), "run_at": e.visual_transport.run_at,
            "now": e.now(), "from_beat": from_beat, "bpm": bpm, "hand": hand,
            "tempo_map": tempo is not None, "phrase_start": phrase.start,
            "phrase_end": phrase.end, "identity": str(getattr(e.plan, "identity", "")),
            "lesson_step": getattr(e, "lesson_step", None),
            "fingerprint": e.fingerprint, "revision": e.score_revision,
            "mode": e.mode, "notes": planned})
        key = (e.fingerprint, e.score_revision)
        if key not in self.dumped:
            self.dumped.add(key)
            threading.Thread(target=self._dump_verovio, args=(e.score_revision,),
                             daemon=True).start()

    def _dump_verovio(self, revision: int) -> None:
        """Verovio's own SVG of the stage on screen, as the reference."""
        try:
            time.sleep(0.5)
            pages = self.engine.engraving().pages
            for i, svg in enumerate(pages):
                with open(os.path.join(_DIR, f"verovio_rev{revision}_p{i + 1}.svg"), "w") as handle:
                    handle.write(svg)
        except Exception:
            _log("performer.jsonl", {"type": "verovio_dump_failed",
                                     "error": traceback.format_exc()})

    # ---- MIDI -------------------------------------------------------
    def _send(self, on: bool, pitch: int, meta: dict) -> None:
        if on:
            self.out.send_message([0x90, pitch, 80])
            self.held[pitch] = self.held.get(pitch, 0) + 1
        else:
            self.out.send_message([0x80, pitch, 0])
            if self.held.get(pitch, 0) > 1:
                self.held[pitch] -= 1
            else:
                self.held.pop(pitch, None)
        _log("keys.jsonl", {"t": self.engine.now(), "on": on, "pitch": pitch, **meta})

    def _release_all(self, reason: str) -> None:
        for pitch, count in list(self.held.items()):
            for _ in range(count):
                self.out.send_message([0x80, pitch, 0])
            _log("keys.jsonl", {"t": self.engine.now(), "on": False, "pitch": pitch,
                                "release_all": reason, "transport_id": self.take})
        self.held.clear()

    def _connect(self) -> None:
        import mido
        import rtmidi
        self.out = rtmidi.MidiOut(name=self.CLIENT)
        self.out.open_virtual_port(self.PORT)
        deadline = time.monotonic() + 30
        name = ""
        while time.monotonic() < deadline and not name:
            names = [n for n in mido.get_input_names()
                     if n.split(":")[0] == self.CLIENT]
            name = names[0] if names else ""
            if not name:
                time.sleep(0.1)
        if not name:
            raise RuntimeError("Virtual MIDI port not visible to mido")
        # The user's Settings choice: the same engine.connect the
        # "midi.device.select" command runs.
        self.engine.connect(name)
        _log("performer.jsonl", {"type": "connected", "device": name,
                                 "connected": bool(self.engine.midi.connected),
                                 "now": self.engine.now()})
        with open(os.path.join(_DIR, "performer_connected"), "w") as handle:
            handle.write(name)

    # ---- loop -------------------------------------------------------
    def run(self) -> None:
        try:
            time.sleep(1.0)
            self._connect()
            while True:
                self._tick()
                time.sleep(0.0007)
        except Exception:
            _log("performer.jsonl", {"type": "crash", "error": traceback.format_exc()})

    def _tick(self) -> None:
        e = self.engine
        live = (e.plan is not None and e.running and e.mode == "practice"
                and not e.preview_only)
        paused = bool(e.visual_transport.paused)
        if not live:
            if self.held:
                self._release_all("not_running")
            return
        if e.transport_id != self.take:
            if self.held:
                self._release_all("new_take")
            self.take = e.transport_id
            with e.lock:
                self._schedule()
        if paused:
            if not self.was_paused:
                self._release_all("pause")
                _log("performer.jsonl", {"type": "paused", "transport_id": self.take,
                                         "now": e.now(), "run_at": e.visual_transport.run_at})
            self.was_paused = True
            return
        if self.was_paused:
            self.was_paused = False
            _log("performer.jsonl", {"type": "resumed", "transport_id": self.take,
                                     "now": e.now(), "run_at": e.visual_transport.run_at,
                                     "grading_after": e._resume_grading_after})
        now = e.now()
        run_at = e.visual_transport.run_at
        while self.events:
            ev = self.events[0]
            due = run_at + ev["at"]
            if due > now:
                break
            self.events.pop(0)
            meta = {"transport_id": self.take, "source_id": ev["source_id"],
                    "k": ev["k"], "due": due, "late_by": now - due}
            if ev["on"]:
                if now - due > 0.05:
                    # A key whose moment passed during a pause: a player skips
                    # it rather than bursting through. Its release is dropped.
                    _log("keys.jsonl", {"t": now, "skipped": True, **meta})
                    self.events = [x for x in self.events
                                   if not (x["k"] == ev["k"] and not x["on"])]
                    continue
                self._send(True, ev["pitch"], meta)
            else:
                if self.held.get(ev["pitch"], 0) > 0:
                    self._send(False, ev["pitch"], meta)


def _install() -> None:
    import piano_teacher.inprocess as inprocess

    original = inprocess.EngineCommands.__init__

    def wrapped(self, *args, **kwargs):
        original(self, *args, **kwargs)
        engine = self.engine
        publish = engine.feedback_events.publish

        def observed(event, _publish=publish):
            stored = _publish(event)
            _log("feedback.jsonl", {"t": engine.now(), **stored})
            return stored

        engine.feedback_events.publish = observed
        Performer(engine).start()
        _log("performer.jsonl", {"type": "installed", "pid": os.getpid()})

    inprocess.EngineCommands.__init__ = wrapped


if _DIR:
    try:
        _install()
    except Exception:
        _log("performer.jsonl", {"type": "install_failed", "error": traceback.format_exc()})
        print("R1 performer install failed", file=sys.stderr)
