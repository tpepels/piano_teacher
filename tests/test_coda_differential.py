
"""Coda differential rejects written/sounding conflation and cross-voice tie merges."""
from piano_teacher.research.coda_differential import (
    WrittenNote, SoundingNote, sounding_from_written, report_comparison,
)


def test_two_voices_same_pitch_have_independent_tie_chains():
    written = (
        WrittenNote("v0", 0, 4, 60, "start"),
        WrittenNote("v1", 2, 4, 60, "start"),
        WrittenNote("v0", 4, 6, 60, "stop"),
        WrittenNote("v1", 4, 5, 60, "stop"),
    )
    sounding, errors = sounding_from_written(written)
    assert errors == ()
    assert sounding == (
        SoundingNote("v0", 0, 6, 60),
        SoundingNote("v1", 2, 5, 60),
    )


def test_sounding_match_does_not_imply_written_match():
    original = (
        WrittenNote("v0", 0, 1, 60, "start"),
        WrittenNote("v0", 1, 2, 60, "stop"),
    )
    regenerated = (WrittenNote("v0", 0, 2, 60),)
    compared = report_comparison(
        original, (SoundingNote("v0", 0, 2, 60),), regenerated)
    assert compared["sounding"]["status"] == "exact"
    assert compared["written"]["status"] == "different"
    assert compared["sounding"]["native_written_to_plan"] == "exact"


def test_reattack_is_not_collapsed_and_rest_is_not_sounded():
    notes = (
        WrittenNote("v0", 0, 1, 60),
        WrittenNote("v0", 1, 2, None),
        WrittenNote("v0", 2, 3, 60),
    )
    sounded, errors = sounding_from_written(notes)
    assert errors == ()
    assert sounded == (
        SoundingNote("v0", 0, 1, 60),
        SoundingNote("v0", 2, 3, 60),
    )


def test_malformed_tie_fails_instead_of_inventing_attack():
    written = (WrittenNote("v0", 3, 4, 60, "stop"),)
    sound, errors = sounding_from_written(written)
    assert sound == ()
    assert errors and errors[0].startswith("orphan-tie:")
    compared = report_comparison(
        written, (SoundingNote("v0", 3, 4, 60),), None,
        unavailable_reason="not rendered")
    assert compared["written"]["status"] == "unavailable"
    assert compared["sounding"]["status"] == "invalid-reference-ties"


def test_unterminated_tie_and_disconnected_segment_are_errors():
    assert sounding_from_written(
        (WrittenNote("v0", 0, 1, 60, "start"),))[1] == (
            "unterminated-tie:v0:60",)
    sounds, errors = sounding_from_written((
        WrittenNote("v0", 0, 1, 60, "start"),
        WrittenNote("v0", 2, 3, 60, "stop"),
    ))
    assert sounds == ()
    assert errors == ("disconnected-tie:v0:60:2",)


def test_music21_reader_preserves_rests_and_written_tie_segments():
    pytest = __import__("pytest")
    pytest.importorskip("music21")
    from music21 import stream, note, tie
    from piano_teacher.research.coda_differential import written_from_music21
    voice = stream.Voice(id="A")
    first = note.Note(60, quarterLength=1)
    first.tie = tie.Tie("start")
    second = note.Note(60, quarterLength=1)
    second.tie = tie.Tie("stop")
    voice.insert(0, first)
    voice.insert(1, second)
    voice.insert(2, note.Rest(quarterLength=1))
    part = stream.Part()
    part.insert(0, voice)
    written = written_from_music21(part)
    assert [(n.voice,n.onset,n.end,n.pitch,n.tie) for n in written] == [
        ("v0",0,1,60,"start"),("v0",1,2,60,"stop"),
        ("v0",2,3,None,"")]
    sounding,errors = sounding_from_written(written)
    assert errors == ()
    assert sounding == (SoundingNote("v0",0,2,60),)
