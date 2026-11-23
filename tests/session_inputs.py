"""Inputs for real engine scenarios; no grading or progression decisions."""
from dataclasses import dataclass
import json
import time

import mido

from piano_teacher.inprocess import EngineCommands
from piano_teacher.server import PracticeEngine
from piano_teacher import sample_piano


@dataclass
class InputClock:
    at: float = 1000.0

    def __call__(self):
        return self.at


class InputPort:
    closed = False

    def __init__(self, callback):
        self.callback = callback

    def close(self):
        self.closed = True

    def send(self, pitch, on=True):
        self.callback(mido.Message("note_on" if on else "note_off",
            note=pitch, velocity=80 if on else 0))


def write_midi(path, *, bars=5, bpm=80, left=True, chords=False,
               first_attack=0.0, held_tail=0.0, meter=(4, 4), single=False):
    """Write known original attacks, including optional chords/pickup/hold."""
    beats = meter[0]*4/meter[1]
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    meta.append(mido.MetaMessage("time_signature", numerator=meter[0], denominator=meter[1]))
    for channel in range(2 if left else 1):
        track = mido.MidiTrack()
        midi.tracks.append(track)
        events = []
        for bar in range(bars):
            base = bar*beats
            attacks = [(base+first_attack, 48+bar, base+beats)] if channel else [
                (base+first_attack, 72+bar, base+min(beats, first_attack+1)),
                (base+beats-1, 79+bar, base+beats)]
            if not channel and single:
                attacks = [(base+first_attack, 72+bar, base+beats)]
            if not channel and chords:
                attacks += [(base+first_attack, pitch+bar, base+1)
                            for pitch in (76, 79)]
            for start, pitch, end in attacks:
                if bar == bars-1 and start == base+beats-1:
                    end += held_tail
                events.append((round(start*480), 1, pitch))
                events.append((round(end*480), 0, pitch))
        previous = 0
        for tick, on, pitch in sorted(events):
            track.append(mido.Message("note_on" if on else "note_off",
                channel=channel, note=pitch, velocity=80 if on else 0,
                time=tick-previous))
            previous = tick
    midi.save(path)
    return path


def take(state):
    """The authorized physical take: one deadline Python chose for the receipt."""
    current = state["playback_timeline"]["current"]
    assert current is not None, state["playback_timeline"]
    return current


class PracticeSession:
    def __init__(self, directory, monkeypatch, **midi_options):
        self.clock = InputClock()
        self.music = directory/"music"
        self.music.mkdir(parents=True)
        self.path = write_midi(self.music/"lesson.mid", **midi_options)
        self.data = directory/"learner"
        self.monkeypatch = monkeypatch
        monkeypatch.delenv("PIANO_TEACHER_SOUNDFONT", raising=False)
        monkeypatch.setattr(sample_piano, "DEFAULT_SOUNDFONT", directory/"absent-optional.sf2")
        self.engine = None
        self.open()

    @classmethod
    def attach(cls, engine, clock):
        """Drive an engine built by another fixture through the same protocol."""
        driver = cls.__new__(cls)
        driver.engine, driver.clock, driver.receipt = engine, clock, None
        driver.commands = EngineCommands(engine=engine)
        return driver

    def open(self):
        if self.engine is not None:
            self.close()
        monkeypatch = self.monkeypatch
        monkeypatch.setattr(mido, "get_input_names", lambda: ["Test piano"])
        monkeypatch.setattr(mido, "open_input", lambda name, callback: InputPort(callback))
        self.engine = PracticeEngine(self.data, clock=self.clock)
        self.commands = EngineCommands(engine=self.engine)
        self.receipt = None
        self.ask("settings.update", music_dir=str(self.music), exercise_strategy="practice-flow")
        self.ask("midi.device.select", name="Test piano")
        return self.ask("library.open", id=self.path.name)

    def ask(self, operation, **payload):
        status, body = self.commands.request(operation, json.dumps(payload))
        assert status == 0, (operation, payload, body.decode())
        response = json.loads(body)
        return response["state"] if operation == "practice.command" else response

    def command(self, action, **values):
        return self.ask("practice.command", action=action, **values)

    def snapshot(self):
        return self.ask("state.snapshot")

    def tick(self, seconds=0.0):
        self.clock.at += seconds
        self.commands.tick()
        return self.snapshot()

    def key(self, pitch, on=True, *, after=0.01):
        self.clock.at += after
        self.engine.midi.port.send(pitch, on)

    def strike(self, pitch):
        self.key(pitch)
        self.key(pitch, False)

    def wait_audio(self):
        limit = time.monotonic()+5
        while time.monotonic() < limit:
            state = self.snapshot()
            demo = state.get("demo")
            if demo and demo.get("audio_available"):
                return demo
            time.sleep(0.005)
        raise AssertionError("Real Listen audio did not prepare within five seconds")

    def physical_offer(self, intent, **changes):
        """The native renderer's immutable physical witness, never a deadline."""
        values = {key: intent[key] for key in (
            "intent_id", "attempt", "take_id", "fingerprint", "stage_key", "revision", "hand")}
        sampled_ms = self.clock() * 1000.0
        physical_ms = (intent["fixed_deadline_ms"] if intent["fixed_deadline_ms"] is not None
                       else intent["earliest_deadline_ms"])
        values.update(source_from_beat=intent["from_beat"], source_end_beat=intent["end_beat"],
                      sampled_at_ms=sampled_ms, travel_ms=physical_ms-sampled_ms,
                      world_origin=100.0, queue_generation=1,
                      renderer_generation=intent["revision"])
        values.update(changes)
        return values

    def admit(self, state=None):
        """Reserve and present the pending physical intent, as Godot does."""
        state = state or self.snapshot()
        intent = state.get("playback_intent")
        if not intent:
            return state
        receipt = self.ask("playback.reserve", **self.physical_offer(intent))
        sampled = self.clock()*1000.0
        self.ask("playback.present", intent_id=intent["intent_id"],
                 attempt=intent["attempt"], segment_id=receipt["segment_id"],
                 physical_world_origin=receipt["world_origin"],
                 physical_sampled_at_ms=sampled,
                 physical_travel_ms=receipt["deadline_ms"]-sampled,
                 physical_queue_generation=receipt["queue_generation"]+1,
                 physical_renderer_generation=intent["revision"])
        self.receipt = receipt
        return self.snapshot()

    def ready_score(self, *, admit=True, state=None):
        state = state or self.snapshot()
        if state.get("awaiting_score_revision") is not None:
            state = self.command("score_ready", revision=state["revision"])
        return self.admit(state) if admit else state

    def start_listen(self):
        """A running Listen take admitted through the physical protocol."""
        state = self.snapshot()
        if state["mode"] == "listen" and state["phase"] == "ready":
            # A directly loaded source waits for the learner's Listen press.
            self.command(state["controls"]["primary"]["action"])
        demo = self.wait_audio()
        self.ready_score()
        return self.admit(self.command("demo_ready", token=demo["token"]))

    def tempo(self):
        """Listen, Free, then the first admitted Tempo take of the window."""
        self.finish_listen()
        self.finish_free()
        return self.ready_score()

    def finish_listen(self):
        self.start_listen()
        demo = self.snapshot()["demo"]
        self.clock.at = self.receipt["deadline_ms"]/1000+demo["duration_seconds"]+.001
        self.tick()
        return self.ready_score()

    def reach_free_target(self):
        """Wait, as a player does, until the Free target reaches the playhead."""
        state = self.snapshot()
        guided = (state.get("playback_timeline") or {}).get("guided")
        if guided and guided["deadline_at_ms"]/1000.0 > self.clock.at:
            self.clock.at = guided["deadline_at_ms"]/1000.0
            state = self.tick()
        return state

    def finish_free(self):
        initial = self.ready_score()
        for _ in range(100):
            state = self.reach_free_target()
            teaching = state.get("teaching")
            if state["mode"] != "learn" or state["revision"] != initial["revision"]:
                return state
            assert teaching and teaching["expected_notes"], state
            for target in teaching["expected_notes"]:
                self.key(target["pitch"])
            for target in teaching["expected_notes"]:
                self.key(target["pitch"], False)
            self.tick()
        raise AssertionError("Free did not finish after its published targets")

    def select(self, first=None, last=None, hand="right", *, final=False):
        steps = self.ask("lesson.overview")["steps"]
        target = next(step for step in steps if step["hand"] == hand and
            (step["kind"] == "perform" if final else
             step["kind"] != "perform" and step["first_bar"] == first and step["last_bar"] == last))
        self.command("select_step", number=target["number"])
        return self.command("learn")

    def play_take(self, *, correct=True):
        state = self.ready_score()
        assert state["running"] and state["mode"] == "practice", state
        transport = state["transport_id"]
        source = self.ask("score.semantic")
        start = self.receipt["deadline_ms"]/1000
        floor = state["play_from_beat"]
        seconds_per_beat = 60/state["bpm"]
        if correct:
            events = []
            for note in source["notes"]:
                at = start+(note["onset_beats"]-floor)*seconds_per_beat
                events += [(at, True, note["midi_pitch"]),
                           (at+note["duration_beats"]*seconds_per_beat, False, note["midi_pitch"])]
            for at, on, pitch in sorted(events):
                self.clock.at = at
                self.engine.midi.port.send(pitch, on)
        sounding = source["practice_timeline"]["sounding_duration_beats"]
        self.clock.at = max(self.clock.at, start+(sounding-floor)*seconds_per_beat+.001)
        for _ in range(300):
            result = self.admit(self.tick(.025))
            if (result["transport_id"] != transport or result["mode"] != "practice"
                    or result["lesson_steps_mastered"] > state["lesson_steps_mastered"]):
                return result
            time.sleep(.001)
        raise AssertionError("The completed take did not continue automatically")

    def close(self):
        self.engine.close()
