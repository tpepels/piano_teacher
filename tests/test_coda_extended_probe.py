"""Contract for a wider *diagnostic* corpus, no new blanket parity promise."""
from hashlib import sha256
from pathlib import Path

from piano_teacher.research.coda_auto_chord_levels import original_chord_levels
from piano_teacher.research.coda_extended_sources import SOURCES, REFERENCE_SHA

ROOT = Path(__file__).resolve().parents[1]


def test_extended_sources_are_independent_and_present():
    assert REFERENCE_SHA == "a4eb85dfc2bd418818ca9ff775c0a11ccccb3530"
    assert len(SOURCES) == 10
    assert len({case[0] for case in SOURCES}) == 10
    assert len({case[1] for case in SOURCES}) == 10
    for name, filename, first, last in SOURCES:
        source=ROOT/filename
        assert source.is_file(), name
        assert sha256(source.read_bytes()).hexdigest()
        assert 1 <= first <= last
    assert any("autumn-source" in x[1] for x in SOURCES)
    assert any("danny-stripe" in x[1] for x in SOURCES)


def test_auto_levels_are_source_derived_and_zero_is_not_silently_skipped():
    assert original_chord_levels(4,4,4)==(2,4,8,16)
    assert original_chord_levels(3,3,4)==(1,2,3,4,6,8,12)
    assert 0 in original_chord_levels(1,3,4)
