from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote, Recorder, evaluate


def sample_piece():
    notes = (Note(0, 1, 60, 0, 0, 'right'),
             Note(0, 2, 48, 1, 0, 'left'),
             Note(2, 2.5, 64, 0, 0, 'right'))
    phrase = Phrase(1, 1, 2, 0, 4, notes)
    return Piece('test', 100, notes, (phrase,))


def test_pitch_rhythm_and_duration_are_all_required():
    phrase = sample_piece().phrases[0]
    correct = [PlayedNote(60, 0, 1), PlayedNote(64, 2, 2.5)]
    assert evaluate(phrase, 'right', 60, correct).clean
    assert not evaluate(phrase, 'both', 60, correct).clean  # left-hand note missing
    early = [PlayedNote(60, -.3, .7), PlayedNote(64, 2, 2.5)]
    assert evaluate(phrase, 'right', 60, early).notes[0].status == 'early'
    too_short = [PlayedNote(60, 0, .2), PlayedNote(64, 2, 2.5)]
    assert evaluate(phrase, 'right', 60, too_short).notes[0].status == 'short'
    assert not evaluate(phrase, 'right', 60, correct + [PlayedNote(70, 1, 1.2)]).clean


def test_note_releases_and_velocity_zero_equivalent():
    r = Recorder()
    r.add(60, True, 0)
    r.add(60, False, 1.1)
    assert r.presses == [PlayedNote(60, 0, 1.1)]
    r.add(62, True, -4)  # count-in is ignored
    assert len(r.presses) == 1


def test_overlapping_repeated_pitch_matches_nearest():
    notes = (Note(0, .5, 60, 0, 0), Note(1, 1.5, 60, 0, 0))
    phrase = Phrase(1, 1, 1, 0, 2, notes)
    attempts = [PlayedNote(60, 0, .5), PlayedNote(60, 1, 1.5)]
    assert evaluate(phrase, 'right', 60, attempts).clean


def test_relaxed_onset_and_release_tolerance():
    from piano_teacher.practice import PlayedNote, evaluate
    from piano_teacher.music import Note, Phrase
    expected = Note(0, 1, 60, 0, 0, 'right')
    phrase = Phrase(1, 1, 1, 0, 4, (expected,))
    # 120 BPM: reference duration = 0.5 seconds.
    assert evaluate(phrase,'right',120,[PlayedNote(60,0.129,0.629)]).clean
    assert not evaluate(phrase,'right',120,[PlayedNote(60,0.131,0.631)]).clean
    assert evaluate(phrase,'right',120,[PlayedNote(60,0.0,0.251)]).clean
    assert not evaluate(phrase,'right',120,[PlayedNote(60,0.0,0.24)]).clean
