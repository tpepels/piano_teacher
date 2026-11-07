"""Whole-source fingering through the real importer and typed in-process API."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event

import mido
import pytest

from piano_teacher.application import score_artifacts
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.inprocess import EngineCommands, OK, INVALID
from piano_teacher.server import PracticeEngine


def _midi(path, *, transpose=0, held=False):
    midi = mido.MidiFile(ticks_per_beat=480)
    for hand, pitches, spacing in (
        ("right", (60, 62, 64, 65, 67, 65, 64, 62), .5),
        ("left", (48, 52, 55, 52), 1),
    ):
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("track_name", name=f"{hand} hand"))
        track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
        events = []
        for i in range(int(16 / spacing)):
            pitch = pitches[i % len(pitches)] + transpose
            onset = int(i * spacing * 480)
            events.extend(((onset, True, pitch), (onset + int(spacing * 400), False, pitch)))
        if hand == "right":
            for pitch in (64, 67):
                events.extend(((0, True, pitch + transpose), (200, False, pitch + transpose)))
            if held:
                events.extend(((1680, True, 72 + transpose), (2160, False, 72 + transpose)))
        previous = 0
        for tick, on, pitch in sorted(events):
            track.append(mido.Message("note_on" if on else "note_off", note=pitch,
                                      velocity=85 if on else 0, time=tick - previous))
            previous = tick
        track.append(mido.MetaMessage("end_of_track", time=16 * 480 - previous))
    midi.save(path)
    return path


@pytest.fixture
def music(tmp_path):
    return _midi(tmp_path / "piece.mid")


@pytest.fixture
def engine(tmp_path):
    instance = PracticeEngine(tmp_path / "state", enable_midi=False)
    instance.set_preferences(exercise_strategy="source-progression")
    yield instance
    instance.db.close()


def _fingers(model):
    return {event["source_id"]: event["fingering"]
            for event in model["notation_events"]
            if event["kind"] == "note" and event["is_attack"]}


def _unprojected(engine):
    piece = engine.plan.piece
    notation = build_lesson_score(
        engine.display_phrase(), boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes, default_clefs=infer_piece_clefs(piece.notes),
        barlines=piece.barlines, source_musicxml=piece.source_musicxml)
    return build_score_model(notation, boundaries=piece.bar_boundaries,
                             hand=engine.plan.hand, revision=engine.score_revision)


@pytest.mark.usefixtures("lumikey_runtime")
def test_import_prepares_original_piece_outside_lock_before_learning_plan(engine, music, monkeypatch):
    prepare = engine.fingering.prepare
    calls = []

    def recorded(piece, fingerprint):
        assert not engine.lock._is_owned()
        calls.append((piece, fingerprint))
        return prepare(piece, fingerprint)

    monkeypatch.setattr(engine.fingering, "prepare", recorded)
    assert engine.state()["fingering"] is None
    engine.load(str(music))
    piece = engine.plan.piece
    assert len(calls) == 1
    assert calls[0][0].notes is piece.notes
    assert calls[0][1] == engine.fingerprint
    assert len(piece.notes) == 50
    assert piece.fingering_plan is not None
    assert not hasattr(engine.plan, "fingering_plan")
    assert engine.state()["fingering"] == piece.fingering_plan.summary()
    assignments = piece.fingering_plan.assignments
    assert set(assignments) == {n.source_id for n in piece.notes}
    fingers = _fingers(engine.semantic_score())
    assert fingers and all(f["finger"] in range(1, 6) for f in fingers.values())
    chord = [assignments[n.source_id].finger for n in piece.notes
             if n.hand == "right" and n.start == 0]
    assert len(chord) == len(set(chord)) == 3


@pytest.mark.usefixtures("lumikey_runtime")
def test_complete_lesson_path_projects_saved_fingers_without_inference(engine, music, monkeypatch):
    engine.load(str(music))
    plan = engine.plan
    seen = {}

    def unexpected(*args, **kwargs):
        raise AssertionError("Lesson navigation must never infer fingering")

    monkeypatch.setattr(engine.fingering, "prepare", unexpected)
    levels, hands = set(), set()
    for number in range(1, len(plan.lesson_steps) + 1):
        engine.control("select_step", number=number)
        levels.add(plan.active_variant.level)
        hands.add(plan.hand)
        model = engine.semantic_score()
        original = _unprojected(engine)
        assert model["notes"] == original["notes"]
        assert model["active_note_ids"] == original["active_note_ids"]
        for event, unprojected in zip(model["notation_events"], original["notation_events"]):
            assert {k: v for k, v in event.items() if k != "fingering"} == unprojected
        for source_id, fingering in _fingers(model).items():
            assert fingering["finger"] in range(1, 6)
            assert seen.setdefault(source_id, fingering) == fingering
        engine.control("tempo_down")
        assert _fingers(engine.semantic_score()) == _fingers(model)
    assert {"left", "right", "both"} <= hands
    assert {"skeleton", "original"} <= levels
    assert set(seen) == {n.source_id for n in plan.piece.notes}


@pytest.mark.usefixtures("lumikey_runtime")
def test_corrections_persist_and_removal_restores_prediction(tmp_path, music, monkeypatch):
    directory = tmp_path / "persisted"
    first = PracticeEngine(directory, enable_midi=False)
    try:
        first.load(str(music))
        source_id, original = next(iter(_fingers(first.semantic_score()).items()))
        chosen = 1 if original["finger"] != 1 else 2
        first.correct_fingering(source_id, chosen)
        assert _fingers(first.semantic_score())[source_id]["finger"] == chosen
    finally:
        first.db.close()
    second = PracticeEngine(directory, enable_midi=False)
    try:
        def unexpected(*args, **kwargs):
            raise AssertionError("Restart or restoring a saved plan must reuse actual cached inference")

        monkeypatch.setattr(second.fingering.provider, "predict", unexpected)
        second.load(str(music))
        assert _fingers(second.semantic_score())[source_id]["finger"] == chosen
        second.correct_fingering(source_id, None)
        assert _fingers(second.semantic_score())[source_id] == original
    finally:
        second.db.close()
    third = PracticeEngine(directory, enable_midi=False)
    try:
        third.load(str(music))
        assert _fingers(third.semantic_score())[source_id] == original
        assert third.state()["fingering"]["manual"] == 0
    finally:
        third.db.close()


@pytest.mark.usefixtures("lumikey_runtime")
def test_correction_keeps_learning_notes_grading_and_transport(engine, music):
    engine.load(str(music))
    learning = engine.plan
    piece = learning.piece
    phrase = learning.active_phrase
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    engine.engraving()
    assert engine.score_artifacts.cached_layout(engine._score_selection()) is not None
    assert engine.score_artifacts.engraving_cache_key is not None
    engine.running = True
    engine.visual_transport.run_at = 123.5
    engine.transport_id = 42
    revision, bpm, target = engine.score_revision, learning.bpm, learning.target_bpm
    played = [PlayedNote(n.pitch, (n.start - phrase.start) * 60 / bpm,
                        (n.end - phrase.start) * 60 / bpm) for n in phrase.notes]
    before = evaluate(phrase, learning.hand, bpm, played)
    engine.correct_fingering(source_id, original["finger"])
    assert engine.plan is learning and learning.piece is not piece
    assert learning.piece.notes is piece.notes
    assert learning.piece.phrases is piece.phrases
    assert learning.active_phrase is phrase
    assert evaluate(phrase, learning.hand, bpm, played) == before
    assert (engine.running, engine.visual_transport.run_at, engine.transport_id) == (True, 123.5, 42)
    assert (learning.bpm, learning.target_bpm) == (bpm, target)
    assert engine.score_revision == revision + 1
    assert engine.score_artifacts.cached_layout(engine._score_selection()) is None
    assert engine.score_artifacts.engraving_cache_key is None


@pytest.mark.usefixtures("lumikey_runtime")
def test_native_geometry_receives_same_projected_model(engine, music, monkeypatch):
    from piano_teacher.application import score_preparation
    engine.load(str(music))
    expected = _fingers(engine.semantic_score())
    assemble = score_preparation.assemble_layout
    received = []

    def recorded(*args, **kwargs):
        received.append(kwargs["native_model"])
        return assemble(*args, **kwargs)

    monkeypatch.setattr(score_preparation, "assemble_layout", recorded)
    layout = engine.geometry()
    assert layout["revision"] == engine.score_revision
    assert _fingers(received[0]) == expected
    cache_key, engraving = engine.score_artifacts.engraving_cache_key, engine.engraving()
    assert engine.geometry()["revision"] == engine.score_revision
    assert engine.engraving() is engraving
    assert len(received) == 1
    assert _fingers(received[0]) == expected

    def unexpected(*args, **kwargs):
        raise AssertionError("Warm geometry must reuse the original engraving cache")

    source_id, original = next(iter(expected.items()))
    engine.correct_fingering(source_id, original["finger"])
    monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
    warm = engine.geometry()
    assert engine.score_artifacts.engraving_cache_key == cache_key
    assert warm["revision"] == engine.score_revision == layout["revision"] + 1
    assert _fingers(received[1]) == _fingers(engine.semantic_score())
    assert _fingers(received[1])[source_id]["origin"] == "manual"


@pytest.fixture
def api(engine, music):
    engine.set_preferences(music_dir=str(music.parent))
    commands = EngineCommands(engine=engine)

    def request(operation, payload=None):
        status, raw = commands.request(
            operation, "" if payload is None else json.dumps(payload))
        return status, json.loads(raw)

    return request


@pytest.mark.usefixtures("lumikey_runtime")
def test_inprocess_fingering_reads_and_corrects_source_assignments(engine, music, api):
    assert api("fingering.status")[1]["assignments"] == {}
    assert api("library.open", {"id": music.name})[0] == OK
    status, initial = api("fingering.status")
    assert status == OK
    assert set(initial["assignments"]) == {n.source_id for n in engine.plan.piece.notes}
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    status, corrected = api("fingering.correct", {"source_id": source_id, "finger": 5})
    assert status == OK and corrected["revision"] == engine.score_revision
    assert _fingers(engine.semantic_score())[source_id]["finger"] == 5
    assert api("fingering.correct", {"source_id": source_id, "finger": None})[0] == OK
    assert _fingers(engine.semantic_score())[source_id] == original


@pytest.mark.parametrize("payload", [
    {}, {"source_id": "missing", "finger": 3},
    {"source_id": [], "finger": 3}, {"source_id": "", "finger": 3},
    {"finger": 3}, [], {"source_id": "SOURCE", "finger": True},
    {"source_id": "SOURCE", "finger": "3"},
    {"source_id": "SOURCE", "finger": 2.5},
    {"source_id": "SOURCE", "finger": 0},
    {"source_id": "SOURCE", "finger": 6}, {"source_id": "SOURCE"},
])
def test_inprocess_invalid_correction_is_rejected_without_changes(engine, music, api, payload):
    engine.load(str(music))
    if isinstance(payload, dict):
        payload = dict(payload)
        if payload.get("source_id") == "SOURCE":
            payload["source_id"] = engine.plan.piece.notes[0].source_id
    revision, piece = engine.score_revision, engine.plan.piece
    status, response = api("fingering.correct", payload)
    assert status == INVALID and response["error"]
    assert engine.score_revision == revision and engine.plan.piece is piece



def test_midi_fingering_reuses_durable_base_engraving(engine, music, monkeypatch):
    engine.load(str(music))
    engine.engraving()
    key = engine.score_artifacts.engraving_cache_key
    assert key is not None
    engine.score_artifacts.invalidate()

    def unexpected(*args, **kwargs):
        raise AssertionError("An unchanged MIDI source must reuse its durable engraving")

    monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
    engine.engraving()
    assert engine.score_artifacts.engraving_cache_key == key


def test_provider_runtime_failure_is_visible_without_fabricated_fingers(engine, music, monkeypatch):
    monkeypatch.setattr(engine.fingering.provider, "node", "/missing-piano-fingering-node")
    engine.load(str(music))
    state = engine.state()
    summary = state["fingering"]
    assert state["loaded"] and summary["status"] == "unavailable"
    assert summary["error"] and summary["unknown"] == len(engine.plan.piece.notes)
    assert summary["assigned"] == 0
    assert all("fingering" not in event for event in engine.semantic_score()["notation_events"])
    source_id = engine.plan.piece.notes[0].source_id
    engine.correct_fingering(source_id, 2)
    summary = engine.state()["fingering"]
    assert summary["status"] == "unavailable" and summary["error"]
    assert summary["manual"] == summary["assigned"] == 1
    assert engine.fingering_status()["assignments"][source_id]["finger"] == 2


@pytest.mark.usefixtures("lumikey_runtime")
def test_tied_continuations_do_not_gain_new_fingering_attacks(engine, tmp_path):
    engine.load(str(_midi(tmp_path / "tied.mid", held=True)))
    engine.control("select_step", number=len(engine.plan.lesson_steps))
    events = engine.semantic_score()["notation_events"]
    held = next(n for n in engine.plan.piece.notes if n.pitch == 72)
    segments = [e for e in events if e["source_id"] == held.source_id]
    assert len(segments) > 1
    assert sum(e["is_attack"] for e in segments) == 1
    assert all(("fingering" in e) == e["is_attack"] for e in segments)


@pytest.mark.usefixtures("lumikey_runtime")
def test_correction_retargets_pending_score_ack_without_starting_attempt(engine, music):
    engine.load(str(music))
    engine.control("practice")
    revision = engine.score_revision
    assert engine.awaiting_score_revision == revision
    engine.control("pause")
    engine.control("score_ready", revision=revision)
    assert engine._deferred_score_ack == revision
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    engine.correct_fingering(source_id, original["finger"])
    assert engine.awaiting_score_revision == engine.score_revision == revision + 1
    assert engine._deferred_score_ack is None
    engine.control("resume")
    assert not engine.running and engine.awaiting_score_revision == revision + 1
    engine.control("score_ready", revision=revision)
    assert not engine.running
    engine.control("score_ready", revision=revision + 1)
    assert engine.running


@pytest.mark.usefixtures("lumikey_runtime")
def test_correction_during_listen_audio_render_preserves_readiness(engine, music, monkeypatch):
    from piano_teacher.demo import DemoAudioCache
    from piano_teacher import sample_piano
    engine.load(str(music))
    render = DemoAudioCache.render
    started, release = Event(), Event()

    def delayed(cache, *args, **kwargs):
        started.set()
        assert release.wait(10)
        return render(cache, *args, **kwargs)

    monkeypatch.setattr(DemoAudioCache, "render", delayed)
    monkeypatch.setattr(sample_piano, "find_soundfont", lambda: None)
    # Render real PCM at the supported low sample rate to keep this race test fast.
    engine.listen.cache = DemoAudioCache(engine._data_dir / "demo-audio", sample_rate=8000)
    engine.control("listen")
    try:
        assert started.wait(10)
        token, revision = engine.listen.snapshot()["token"], engine.score_revision
        source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
        engine.correct_fingering(source_id, original["finger"])
    finally:
        release.set()
        engine.listen.thread.join(timeout=20)
    assert not engine.listen.thread.is_alive()
    assert engine.listen.snapshot()["token"] == token and engine.listen.snapshot()["audio_available"]
    assert engine.score_revision == revision + 1
    # DemoPlayer retains the audio token and the revision at which its WAV
    # request began. A fingering-only score update must accept that audio ack.
    engine.control("demo_ready", token=token, revision=revision)
    assert engine.listen.snapshot()["ready"] and not engine.running
    engine.control("score_ready", revision=revision)
    assert not engine.running
    engine.control("score_ready", revision=engine.score_revision)
    assert engine.running and engine.mode == "listen"


@pytest.mark.usefixtures("lumikey_runtime")
def test_correction_after_failed_listen_render_does_not_restore_loading(engine, music):
    engine.load(str(music))

    class FailedCache:
        def render(self, variant, bpm):
            raise OSError('Controlled unavailable audio cache')

    engine.listen.cache = FailedCache()
    engine.control('listen')
    engine.listen.thread.join(3)
    assert not engine.listen.thread.is_alive()
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    # No state poll has consumed the worker's failure before this correction.
    revision = engine.score_revision
    engine.correct_fingering(source_id, original['finger'])
    state = engine.state()
    assert state['revision'] == revision + 1
    assert state['phase'] == 'ready' and engine.awaiting_score_revision is None
    assert state['demo']['error'] == state['feedback']
    engine.control('score_ready', revision=state['revision'])
    assert not engine.state()['running']


def test_load_inference_keeps_state_responsive_and_rejects_queued_old_piece_edit(
        engine, music, tmp_path, monkeypatch):
    engine.load(str(music))
    old_fingerprint = engine.fingerprint
    source_id = engine.plan.piece.notes[0].source_id
    other = _midi(tmp_path / "other.mid", transpose=12)
    prepare = engine.fingering.prepare
    started, release, attempted = Event(), Event(), Event()
    lock = engine._fingering_lock

    class ObservedLock:
        def __enter__(self):
            attempted.set()
            return lock.__enter__()

        def __exit__(self, *args):
            return lock.__exit__(*args)

    def delayed(*args):
        assert not engine.lock._is_owned()
        started.set()
        assert release.wait(10)
        return prepare(*args)

    monkeypatch.setattr(engine, "_fingering_lock", ObservedLock())
    monkeypatch.setattr(engine.fingering, "prepare", delayed)
    with ThreadPoolExecutor(max_workers=3) as workers:
        loaded = workers.submit(engine.load, str(other))
        try:
            assert started.wait(10)
            assert workers.submit(engine.state).result(timeout=2)["piece_fingerprint"] == old_fingerprint
            attempted.clear()
            edited = workers.submit(engine.correct_fingering, source_id, 3)
            assert attempted.wait(10)  # The edit captured the old source before waiting.
        finally:
            release.set()
        loaded.result(timeout=10)
        with pytest.raises(ValueError, match="loaded piece changed"):
            edited.result(timeout=10)
    assert engine.fingerprint != old_fingerprint
    assert engine.state()["fingering"]["manual"] == 0


@pytest.mark.usefixtures("lumikey_runtime")
def test_concurrent_edits_survive_learning_plan_reset(engine, music, monkeypatch):
    engine.load(str(music))
    previous_plan = engine.plan
    choices = list(_fingers(engine.semantic_score()).items())[:2]
    correct = engine.fingering.correct
    started, release = Event(), Event()
    calls = []

    def delayed(piece, fingerprint, source_id, finger):
        assert not engine.lock._is_owned()
        calls.append(source_id)
        if len(calls) == 1:
            started.set()
            assert release.wait(10)
        return correct(piece, fingerprint, source_id, finger)

    monkeypatch.setattr(engine.fingering, "correct", delayed)
    with ThreadPoolExecutor(max_workers=3) as workers:
        first = workers.submit(engine.correct_fingering, choices[0][0], choices[0][1]["finger"])
        try:
            assert started.wait(10)
            assert workers.submit(engine.state).result(timeout=2)["loaded"]
            engine.control("reset_path", fingerprint=engine.fingerprint, confirm=True)
            second = workers.submit(engine.correct_fingering, choices[1][0], choices[1][1]["finger"])
        finally:
            release.set()
        first.result(timeout=10)
        second.result(timeout=10)
    assert engine.plan is not previous_plan
    assert engine.plan.piece.notes is previous_plan.piece.notes
    assert len(calls) == 2 and engine.state()["fingering"]["manual"] == 2
    assignments = engine.fingering_status()["assignments"]
    assert all(assignments[sid]["manual"] == fingering["finger"] for sid, fingering in choices)


def test_inprocess_rejects_correction_from_different_source_fingerprint(engine, music, api):
    engine.load(str(music))
    source_id = engine.plan.piece.notes[0].source_id
    revision = engine.score_revision
    status, response = api("fingering.correct", {"source_id": source_id, "finger": 2,
                                          "fingerprint": "obsolete-source"})
    assert status == INVALID and "loaded piece changed" in response["error"]
    assert engine.score_revision == revision
    assert engine.state()["fingering"]["manual"] == 0
