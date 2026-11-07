"""Backend feedback events reach the production app's ledger exactly once.

A real PracticeEngine performs a take (clean, omitted, early-released notes)
under a controlled clock. The production Godot application then consumes the
engine's own acknowledged event log through main.gd's single feedback path,
while its last state snapshot is deliberately stale (the previous transport,
not yet playing) -- the transport transition that used to discard events.
"""
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts.smoke_phase0 import make_fixture

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


def _performed_take(tmp_path, monkeypatch):
    from piano_teacher import server
    from piano_teacher.server import PracticeEngine

    midi = tmp_path / "chords.mid"
    make_fixture(midi)
    now = [500.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.load(str(midi))
        engine.plan.set_hand("both")
        engine.midi.port = SimpleNamespace(closed=False)
        payload = {"model": engine.semantic_score(), "layout": engine.geometry()}
        engine.start()
        assert engine.running and not engine.preview_only
        payload["stale_state"] = engine.state()  # count-in of this transport
        phrase = engine.plan.active_phrase
        spb = 60.0 / engine.plan.bpm
        keys = []
        for index, note in enumerate(phrase.notes):
            if index == 1:
                continue  # omitted: must be shown missed during playback
            onset = (note.start - phrase.start) * spb
            release = (note.end - phrase.start) * spb
            if index == 2:
                release = onset + .05  # early release
            keys += [(onset, 0, note.pitch, True), (release, 1, note.pitch, False)]
        for at, _, pitch, down in sorted(keys):
            now[0] = engine.visual_transport.run_at + at
            engine._receive(SimpleNamespace(type="note_on" if down else "note_off",
                                            note=pitch, velocity=80 if down else 0,
                                            channel=0))
            engine.advance_clock()
        end = engine.visual_transport.run_at + (phrase.end - phrase.start) * spb
        while engine.running and now[0] < end + 3:
            now[0] += .05
            engine.advance_clock()
        assert engine.pending_result is not None or engine.performance_summary is not None \
            or engine.feedback_marks
        payload["feedback"] = engine.feedback_events.after(0)
        events = payload["feedback"]["events"]
        assert {event["kind"] for event in events} == {"attack", "release", "assessment"}
        assert {event["transport_id"] for event in events} == {engine.transport_id}
        assert payload["stale_state"]["phase"] != "playing"
        # The state the UI last saw names the PREVIOUS transport.
        payload["stale_state"]["transport_id"] = engine.transport_id - 1
        payload["state"] = dict(payload["stale_state"])
        return payload
    finally:
        engine.db.close()


@pytest.mark.skipif(GODOT is None, reason="Godot 4 not installed")
def test_engine_feedback_events_reach_the_production_ledger_once(tmp_path, monkeypatch):
    payload = _performed_take(tmp_path, monkeypatch)
    (tmp_path / "native.json").write_text(json.dumps(payload))
    script = tmp_path / "note_reactions.gd"
    script.write_text('''extends SceneTree
const Status := preload("res://note_status_registry.gd")
var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("NOTE_REACTIONS_FAIL:", label)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    var app = load("FIXTURE_PATH").new()
    root.add_child(app)
    var error: String = await app.load_native_fixture(folder)
    check(error.is_empty(), "Production native fixture loads: " + error)
    if not failures.is_empty():
        app.free()
        quit(1)
        return
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        folder.path_join("native.json")))
    var renderer = app.practice_view.stage.renderer
    var feedback = app.practice_view.stage.feedback
    check(feedback.score == renderer and feedback.score_revision == app.revision,
        "Production binds the ledger to the loaded source revision")
    check(renderer.note_status_source == feedback,
        "The production renderer paints from the one note-status ledger")
    # The UI has not seen a snapshot of the new transport yet.
    app.last_state = data["stale_state"]
    var reply: Dictionary = data["feedback"]
    var events: Array = reply["events"]
    app._consume_feedback_reply(reply)
    check(app.feedback_inbox.acknowledged == int(events[-1]["sequence"]),
        "Every event is acknowledged after it was processed")
    check(feedback.ignored_events == 0 and feedback.pending_events() == 0,
        "No event of the transport transition is dropped or left pending")
    var latest: Dictionary = {}
    var take := ""
    var hits := 0
    for event in events:
        take = Status.take_key(event)
        if event["kind"] == "assessment":
            latest[event["note_id"]] = event
        elif event["kind"] == "attack" and event["status"] in ["on_time","early","late"]:
            hits += 1
    check(not latest.is_empty(), "The engine published per-note assessments")
    var missed := 0
    for id in latest:
        var expected: String = Status.display_status(latest[id]["dimensions"])
        check(feedback.status_for(take,id) == expected,
            "note %s shows %s from its settled dimensions" % [id,expected])
        check(feedback.statuses.is_settled(take,id), "note %s is settled" % id)
        missed += int(expected == Status.MISSED)
    check(missed >= 1, "The omitted note is shown missed")
    check(hits > 0, "The take contains matched attacks")
    var applied: int = feedback.applied_events
    app._consume_feedback_reply(reply)
    check(feedback.applied_events == applied,
        "A repeated reply cannot replay an acknowledged event")
    print("NOTE_REACTIONS_FAILURES:",failures.size())
    app.free()
    quit(0 if failures.is_empty() else 1)
'''.replace("FIXTURE_PATH", str(ROOT / "tests/godot/native_production_fixture.gd")))
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(script), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=60
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output and "ERROR:" not in output, output
    assert "NOTE_REACTIONS_FAILURES:0" in output, output
