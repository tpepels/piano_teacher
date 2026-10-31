"""Large MIDI scores use a preindexed, near-current-note search."""
from piano_teacher.music import Note, Phrase
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.exercise_contracts import TempoMap, TempoSegment


def test_large_score_onsets_indexed_before_physical_callback():
    notes = tuple(Note(float(i), float(i)+.5, 60+i%12, 0, 0,
                       "right", f"source-{i}") for i in range(6000))
    phrase = Phrase(1, 1, 1500, 0, 6000, notes)
    view = LiveInputView()
    view.prepare(phrase)
    assert view._indexed_phrase is phrase
    assert len(view._ordered_notes) == 6000
    index_id = id(view._ordered_notes)
    # The source does not get re-sorted on every keystroke.
    for i in (0, 2000, 5999):
        view.receive(pitch=60+i%12, is_on=True, now=10.0+i,
                     phrase=phrase, hand="right", bpm=60.0,
                     from_beat=0, run_at=10.0, running=True, paused=False,
                     preview=False, mode="practice", transport_id=1)
        assert view.events[-1]["source_id"] == f"source-{i}"
        assert view.events[-1]["status"] == "on_time"
        assert id(view._ordered_notes) == index_id


def test_unsorted_chord_and_shaped_tempo_preserve_original_source_index():
    notes = (Note(4, 5, 67, 0, 0, "right", "later"),
             Note(0, 1, 60, 0, 0, "right", "first"),
             Note(0, 1, 64, 0, 0, "right", "second"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    tempo = TempoMap("shaped", (TempoSegment(0, 4, 40),
                                TempoSegment(4, 8, 80)))
    view = LiveInputView()
    view.prepare(phrase)
    for pitch, beat, source in ((60, 0, "first"),(64, 0, "second"),(67, 4, "later")):
        view.receive(pitch=pitch, is_on=True, now=10+tempo.seconds_at(beat),
                     phrase=phrase, hand="right", bpm=60, from_beat=0,
                     run_at=10, running=True, paused=False, preview=False,
                     mode="practice", transport_id=1, tempo_map=tempo)
        assert view.events[-1]["source_id"] == source
        assert view.events[-1]["status"] == "on_time"
