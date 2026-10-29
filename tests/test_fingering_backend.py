"""Whole-source fingering through the real importer, provider and HTTP API."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import json
from threading import Event, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import mido
import pytest

from piano_teacher.application import score_artifacts
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.server import Handler, PracticeEngine


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


def test_correction_keeps_learning_notes_grading_and_transport(engine, music):
    engine.load(str(music))
    learning = engine.plan
    piece = learning.piece
    phrase = learning.active_phrase
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    engine.engraving()
    engine.engraved_png()
    assert engine.score_artifacts.cached_layout(engine._score_selection()) is not None
    assert engine.score_artifacts.engraving_cache_key is not None
    engine.running = True
    engine.run_at = 123.5
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
    assert (engine.running, engine.run_at, engine.transport_id) == (True, 123.5, 42)
    assert (learning.bpm, learning.target_bpm) == (bpm, target)
    assert engine.score_revision == revision + 1
    assert engine.score_artifacts.cached_layout(engine._score_selection()) is None
    assert engine.score_artifacts.engraving_cache_key is None


def test_native_geometry_receives_same_projected_model(engine, music, monkeypatch):
    from piano_teacher.application import score_preparation
    from piano_teacher import server
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
    assert _fingers(received[1]) == expected

    def unexpected(*args, **kwargs):
        raise AssertionError("Warm geometry must reuse the original engraving cache")

    source_id, original = next(iter(expected.items()))
    engine.correct_fingering(source_id, original["finger"])
    monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
    warm = engine.geometry()
    assert engine.score_artifacts.engraving_cache_key == cache_key
    assert warm["revision"] == engine.score_revision == layout["revision"] + 1
    assert _fingers(received[2]) == _fingers(engine.semantic_score())
    assert _fingers(received[2])[source_id]["origin"] == "manual"


@pytest.fixture
def api(engine):
    class LocalHandler(Handler):
        pass

    LocalHandler.engine = engine
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(route, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(f"http://127.0.0.1:{server.server_port}" + route, data=body,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=60) as reply:
                return reply.status, json.loads(reply.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    yield request
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_http_fingering_reads_and_corrects_source_assignments(engine, music, api):
    assert api("/fingering")[1]["assignments"] == {}
    assert api("/load", {"path": str(music)})[0] == 200
    status, initial = api("/fingering")
    assert status == 200
    assert set(initial["assignments"]) == {n.source_id for n in engine.plan.piece.notes}
    source_id, original = next(iter(_fingers(engine.semantic_score()).items()))
    status, corrected = api("/fingering", {"source_id": source_id, "finger": 5})
    assert status == 200 and corrected["revision"] == engine.score_revision
    assert _fingers(engine.semantic_score())[source_id]["finger"] == 5
    assert api("/fingering", {"source_id": source_id, "finger": None})[0] == 200
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
def test_http_invalid_correction_is_rejected_without_changes(engine, music, api, payload):
    engine.load(str(music))
    if isinstance(payload, dict):
        payload = dict(payload)
        if payload.get("source_id") == "SOURCE":
            payload["source_id"] = engine.plan.piece.notes[0].source_id
    revision, piece = engine.score_revision, engine.plan.piece
    status, response = api("/fingering", payload)
    assert status == 400 and response["error"]
    assert engine.score_revision == revision and engine.plan.piece is piece


@pytest.fixture
def authored_music(tmp_path):
    path = tmp_path / "authored.musicxml"
    path.write_text('''<score-partwise version="4.0"><part-list>
      <score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
      <part id="P1"><measure number="1"><attributes><divisions>4</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>C</step><octave>5</octave></pitch><duration>4</duration>
      <type>quarter</type><notations><technical><fingering>2</fingering></technical></notations></note>
      <note><pitch><step>D</step><octave>5</octave></pitch><duration>4</duration><type>quarter</type></note>
      <note><pitch><step>E</step><octave>5</octave></pitch><duration>8</duration><type>half</type></note>
      </measure></part></score-partwise>''')
    return path


def test_musicxml_authored_fingering_has_priority_and_returns_after_override(engine, authored_music):
    engine.load(str(authored_music))
    source = engine.plan.piece.source_musicxml
    note = next(n for n in engine.plan.piece.notes if n.pitch == 72)
    assert _fingers(engine.semantic_score())[note.source_id]["finger"] == 2
    engine.correct_fingering(note.source_id, 4)
    assert _fingers(engine.semantic_score())[note.source_id]["finger"] == 4
    engine.correct_fingering(note.source_id, None)
    assert _fingers(engine.semantic_score())[note.source_id]["finger"] == 2
    assert engine.plan.piece.source_musicxml == source


def _has_fingering_ink(engraving):
    return any("fing" in element.get("class", "").split()
               for page in engraving.pages for element in ET.fromstring(page).iter())


def test_authored_fingering_is_owned_by_native_model_at_all_three_score_seams(
        engine, authored_music, monkeypatch):
    from piano_teacher import server
    from piano_teacher.application import score_preparation
    engine.load(str(authored_music))
    piece = engine.plan.piece
    source_id = next(n.source_id for n in piece.notes if n.pitch == 72)
    build, assemble = score_artifacts.build_lesson_score, score_preparation.assemble_layout
    handled, native_models = [], []

    def recorded_build(*args, **kwargs):
        handled.append(kwargs.get("fingering_sources", frozenset()))
        return build(*args, **kwargs)

    def recorded_assemble(*args, **kwargs):
        native_models.append(kwargs["native_model"])
        return assemble(*args, **kwargs)

    monkeypatch.setattr(score_artifacts, "build_lesson_score", recorded_build)
    monkeypatch.setattr(score_preparation, "assemble_layout", recorded_assemble)
    model = engine.semantic_score()
    assert model["unrendered_expressions"] == []
    assert _fingers(model)[source_id]["finger"] == 2
    engraving = engine.engraving()
    assert not _has_fingering_ink(engraving)
    assert engine.geometry()["revision"] == engine.score_revision
    assert native_models[0]["unrendered_expressions"] == []
    assert _fingers(native_models[0])[source_id]["finger"] == 2
    assert handled == [frozenset({source_id})]  # All three seams reuse the selected compilation.
    assert engine.plan.piece.source_musicxml == piece.source_musicxml


def test_authored_other_technical_markings_remain_unsupported(engine, authored_music):
    original = authored_music.read_text().replace(
        "<fingering>2</fingering>", "<fingering>2</fingering><up-bow/>")
    authored_music.write_text(original)
    engine.load(str(authored_music))
    model = engine.semantic_score()
    assert "note:technical" in model["unrendered_expressions"]
    source_id = next(n.source_id for n in engine.plan.piece.notes if n.pitch == 72)
    assert _fingers(model)[source_id]["finger"] == 2
    engraving = engine.engraving()
    assert not _has_fingering_ink(engraving)
    assert "up-bow" in engine.plan.piece.source_musicxml
    assert "<fingering>2</fingering>" in engine.plan.piece.source_musicxml


def test_authored_cache_discards_old_number_ink_and_reuses_clean_base_after_correction(
        engine, authored_music, monkeypatch):
    from piano_teacher import server
    from piano_teacher.application import score_preparation
    engine.load(str(authored_music))
    p, phrase = engine.plan, engine.display_phrase()
    piece = p.piece
    source_id = next(n.source_id for n in piece.notes if n.pitch == 72)
    # Seed the actual pre-feature engraving cache, which contains authored
    # fingering ink. A new native model must never reuse that base image.
    legacy_notation = build_lesson_score(
        phrase, boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
        key_signatures=piece.key_signatures, clef_changes=piece.clef_changes,
        default_clefs=infer_piece_clefs(piece.notes), barlines=piece.barlines,
        source_musicxml=piece.source_musicxml)
    legacy = score_artifacts.render_layout(legacy_notation, phrase.first_bar, phrase.last_bar,
                                 p.hand, total_beats=phrase.end - phrase.start,
                                 bpm=piece.bpm, continuous=True)
    assert _has_fingering_ink(legacy)
    legacy_key = engine.preprocessing.key(
        "engraving", "readable-midi-engraving-v2", engine.fingerprint, p.identity,
        phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
        p.hand, piece.bpm, True,
        tuple((n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes))
    engine.preprocessing.write_json("engraving", legacy_key,
                                    {"pages": list(legacy.pages), "layout": legacy.layout})
    base = engine.engraving()
    clean_key = engine.score_artifacts.engraving_cache_key
    assert clean_key != legacy_key and not _has_fingering_ink(base)
    assemble, native_models = score_preparation.assemble_layout, []

    def recorded(*args, **kwargs):
        native_models.append(kwargs["native_model"])
        return assemble(*args, **kwargs)

    def unexpected(*args, **kwargs):
        raise AssertionError("Changing a projected finger must reuse the clean base engraving")

    monkeypatch.setattr(score_preparation, "assemble_layout", recorded)
    monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
    engine.correct_fingering(source_id, 4)
    engine.geometry()
    assert engine.score_artifacts.engraving_cache_key == clean_key
    assert not _has_fingering_ink(engine.engraving())
    assert _fingers(native_models[0])[source_id] == {
        "source_id": source_id, "hand": "right", "finger": 4, "origin": "manual"}
    assert native_models[0]["unrendered_expressions"] == []
    assert "<fingering>2</fingering>" in engine.plan.piece.source_musicxml


def test_midi_fingering_preserves_existing_base_engraving_cache_key(engine, music):
    engine.load(str(music))
    p, phrase = engine.plan, engine.display_phrase()
    compact = phrase.last_bar - phrase.first_bar + 1 <= 12 and phrase.end - phrase.start <= 48
    expected = engine.preprocessing.key(
        "engraving", "readable-midi-engraving-v3", engine.fingerprint, p.identity,
        phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
        p.hand, p.piece.bpm, compact,
        tuple((n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes))
    engine.engraving()
    assert engine.score_artifacts.engraving_cache_key == expected


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


def test_tied_continuations_do_not_gain_new_fingering_attacks(engine, tmp_path):
    engine.load(str(_midi(tmp_path / "tied.mid", held=True)))
    engine.control("select_step", number=len(engine.plan.lesson_steps))
    events = engine.semantic_score()["notation_events"]
    held = next(n for n in engine.plan.piece.notes if n.pitch == 72)
    segments = [e for e in events if e["source_id"] == held.source_id]
    assert len(segments) > 1
    assert sum(e["is_attack"] for e in segments) == 1
    assert all(("fingering" in e) == e["is_attack"] for e in segments)


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


def test_http_rejects_correction_from_different_source_fingerprint(engine, music, api):
    engine.load(str(music))
    source_id = engine.plan.piece.notes[0].source_id
    revision = engine.score_revision
    status, response = api("/fingering", {"source_id": source_id, "finger": 2,
                                          "fingerprint": "obsolete-source"})
    assert status == 400 and "loaded piece changed" in response["error"]
    assert engine.score_revision == revision
    assert engine.state()["fingering"]["manual"] == 0
