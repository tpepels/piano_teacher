"""Offline tests for the public-domain spoken count-in asset cache."""
from pathlib import Path

from scripts import fetch_countin_voices as voices


def test_manifest_has_four_distinct_public_domain_samples() -> None:
    assert set(voices.SAMPLES) == {"ichi", "ni", "san", "shi"}
    assert len(set(voices.SAMPLES.values())) == 4
    assert all(filename.endswith(".ogg") for filename in voices.SAMPLES.values())


def test_ogg_validation_never_accepts_missing_or_partial_audio(tmp_path: Path) -> None:
    missing = tmp_path / "missing.ogg"
    assert not voices.valid_ogg(missing)
    missing.write_bytes(b"not vorbis" * 400)
    assert not voices.valid_ogg(missing)
    missing.write_bytes(b"OggS" + bytes(2500))
    assert voices.valid_ogg(missing)


def test_verified_cache_requires_no_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(voices, "DESTINATION", tmp_path)
    for name in voices.SAMPLES:
        (tmp_path / f"{name}.ogg").write_bytes(b"OggS" + bytes(2500))
    assert voices.fetch_samples(offline=True)
    (tmp_path / "shi.ogg").unlink()
    assert not voices.fetch_samples(offline=True)
