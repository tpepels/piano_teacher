"""Persistent reuse must never change musical identity or serve stale ink."""
from pathlib import Path

import pytest

from piano_teacher.application import score_artifacts
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.server import PracticeEngine

FIXTURE = Path(__file__).parent / "fixtures/musical_fidelity/midi_four_four.mid"


def test_reopening_source_and_engraving_skips_parsing_and_rasterization(
        tmp_path, monkeypatch):
    music = tmp_path / "piece.mid"
    music.write_bytes(FIXTURE.read_bytes())
    directory = tmp_path / "data"
    first = PracticeEngine(directory, enable_midi=False)
    try:
        first.load(str(music))
        source_ids = tuple(n.source_id for n in first.plan.piece.notes)
        layout = first.engraving()
        png = first.engraved_png(0)
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert layout.pages
    finally:
        first.db.close()

    import piano_teacher.score as score
    import piano_teacher.server as server

    def unexpected(*args, **kwargs):
        raise AssertionError("Warm cache unexpectedly recomputed source or score")

    monkeypatch.setattr(server, "import_piece", unexpected)
    monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
    monkeypatch.setattr(score_artifacts, "rasterize_score", unexpected)
    again = PracticeEngine(directory, enable_midi=False)
    try:
        again.load(str(music))
        assert tuple(n.source_id for n in again.plan.piece.notes) == source_ids
        cached_layout = again.engraving()
        assert cached_layout.pages == layout.pages
        assert cached_layout.layout == layout.layout
        assert again.engraved_png(0) == png
    finally:
        again.db.close()


def test_cache_key_tracks_content_version_and_kind(tmp_path, monkeypatch):
    import piano_teacher.preprocessing_cache as module
    cache = PreprocessingCache(tmp_path)
    original = cache.key("source", "fingerprint-one", "piece.mid")
    assert original != cache.key("source", "fingerprint-two", "piece.mid")
    assert original != cache.key("source", "fingerprint-one", "other.mid")
    assert original != cache.key("engraving", "fingerprint-one", "piece.mid")
    cache.write_json("source", original, {"title": "Demo"})
    assert cache.read_json("source", original) == {"title": "Demo"}
    monkeypatch.setattr(module, "CACHE_VERSION", "next-import-and-notation-version")
    changed = PreprocessingCache(tmp_path)
    assert changed.key("source", "fingerprint-one", "piece.mid") != original
    assert changed.read_json("source", original) is None


def test_corrupted_cache_is_an_ordinary_miss(tmp_path):
    cache = PreprocessingCache(tmp_path)
    key = cache.key("source", "some-hash", "test.mid")
    cache.write_json("source", key, {"title": "Demo"})
    path = cache._path("source", key, "json.gz")
    path.write_bytes(b"corrupted compressed cache")
    assert cache.read_json("source", key) is None
    assert cache.read_png(cache.key("png", "no-png")) is None


def test_source_bytes_change_forces_reimport(tmp_path):
    import hashlib
    from piano_teacher.music import Piece
    music = tmp_path / "source.mid"
    music.write_bytes(FIXTURE.read_bytes())
    cache = PreprocessingCache(tmp_path / "cache")
    fingerprint = hashlib.sha256(music.read_bytes()).hexdigest()
    piece, _ = cache.load_import(music, fingerprint)
    assert isinstance(piece, Piece)
    cached, _ = cache.load_import(music, fingerprint)
    assert cached == piece
    # Different content must never hit the original cache key.
    assert cache.key("source", "different-sha", music.name) != \
           cache.key("source", fingerprint, music.name)


def test_peace_register_layout_replaces_legacy_cache_and_reuses_new_warm_cache(
        tmp_path, monkeypatch):
    """An existing installation must receive the correction without cache deletion."""
    import hashlib
    from xml.etree import ElementTree as ET
    from piano_teacher import server
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.learning import LearningPlan
    from piano_teacher.notation import lesson

    path = Path(__file__).resolve().parents[1] / "midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi"
    piece, _ = import_piece(path)
    engines = []

    def create():
        app = PracticeEngine(tmp_path / "state", enable_midi=False)
        engines.append(app)
        app.plan = LearningPlan(piece)
        app.plan.select_step(3)
        app.fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        return app

    def staff_index(engraving, identifier):
        found = []
        for page in engraving.pages:
            root = ET.fromstring(page)
            for measure in root.iter():
                if measure.get("class") != "measure":
                    continue
                staves = [node for node in measure if node.get("class") == "staff"]
                found.extend(index for index, staff in enumerate(staves)
                             if any(node.get("id") == identifier for node in staff.iter()))
        assert len(found) == 1
        return found[0]

    try:
        app = create()
        p, phrase = app.plan, app.display_phrase()
        # Reproduce the previous generator: source hands also selected the
        # engraved staff, leaving the real C2 inside the wide RH chord.
        with monkeypatch.context() as previous:
            previous.setattr(lesson, "distribute_piano_registers", lambda lanes, clefs: lanes)
            old_score = lesson.build_lesson_score(
                phrase, boundaries=piece.bar_boundaries,
                time_signatures=piece.time_signatures,
                default_clefs=lesson.infer_piece_clefs(piece.notes))
        low_id = next(identifier for identifier, binding in old_score.note_bindings.items()
                      if binding["source_id"] == "midi-t0-e29")
        legacy = score_artifacts.render_layout(old_score, phrase.first_bar, phrase.last_bar,
            p.hand, total_beats=phrase.end-phrase.start, bpm=piece.bpm, continuous=True)
        assert staff_index(legacy, low_id) == 0
        legacy_key = app.preprocessing.key(
            "engraving", "readable-midi-engraving-v2", app.fingerprint, p.identity,
            phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
            p.hand, piece.bpm, True,
            tuple((n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes))
        app.preprocessing.write_json("engraving", legacy_key,
                                    {"pages": list(legacy.pages), "layout": legacy.layout})

        corrected = app.engraving()
        assert staff_index(corrected, low_id) == 1, "Existing cache retained the huge treble-staff chord"
        assert app.score_artifacts.engraving_cache_key != legacy_key
        assert app.preprocessing.read_json("engraving", legacy_key) is not None

        def unexpected(*args, **kwargs):
            raise AssertionError("Corrected warm cache unexpectedly re-engraved the lesson")

        monkeypatch.setattr(score_artifacts, "render_layout", unexpected)
        reopened = create()
        assert reopened.engraving() == corrected
        assert reopened.score_artifacts.engraving_cache_key == app.score_artifacts.engraving_cache_key
    finally:
        for app in engines:
            app.db.close()
