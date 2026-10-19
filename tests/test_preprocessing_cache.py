"""Persistent reuse must never change musical identity or serve stale ink."""
from pathlib import Path

import pytest

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
    monkeypatch.setattr(server, "render_layout", unexpected)
    monkeypatch.setattr(server, "rasterize_score", unexpected)
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
