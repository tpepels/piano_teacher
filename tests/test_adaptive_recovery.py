"""Two-measure recovery: wrong vs missed pitch, window and hand filtering."""
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import PlayedNote
from piano_teacher.recovery import check_rolling_two_bar_window, check_two_bar_window


def phrase():
    notes = tuple(Note(float(i), float(i)+.5, 60+i, 0, 0, "right") for i in range(8))
    return Phrase(1, 1, 2, 0, 8, notes)


def test_five_missing_notes_trigger_rewind():
    played = [PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (0,1,2)]
    decision = check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                    end_beat=8, beats_per_bar=4)
    assert decision.errors == 5 and decision.restart_beat == 0


def test_four_misses_do_not_trigger_retry():
    played = [PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (0,1,2,3)]
    assert check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                end_beat=8, beats_per_bar=4) is None


def test_wrong_note_does_not_count_twice():
    played = [PlayedNote(90, 0, .25)] + [
        PlayedNote(60+i, i*.5, (i+.5)*.5) for i in (1,2,3)]
    decision = check_two_bar_window(phrase(), "right", 120, played, from_beat=0,
                                    end_beat=8, beats_per_bar=4)
    assert decision.errors == 5 and decision.wrong == 1 and decision.missed == 4


def test_four_bar_rewind_selects_last_two_bars():
    notes = tuple(Note(float(i), float(i)+.5, 60+i, 0, 0, "right") for i in range(16))
    passage = Phrase(1,1,4,0,16,notes)
    decision = check_two_bar_window(passage, "right", 120, [], from_beat=8,
                                    end_beat=16, beats_per_bar=4)
    assert decision.restart_beat == 8 and decision.errors == 8


def test_other_hand_does_not_trigger_rewind():
    notes = tuple(Note(n.start,n.end,n.pitch,n.track,n.channel,"left") for n in phrase().notes)
    passage = Phrase(1,1,2,0,8,notes)
    assert check_two_bar_window(passage,"right",120,[],from_beat=0,
                                end_beat=8,beats_per_bar=4) is None


def test_rolling_window_is_not_limited_to_bar_aligned_ranges():
    # Five attacks fit between beats 7.5 and 15.2, but span three printed bars.
    # No pair of complete printed bars contains all five.
    notes = tuple(Note(32+beat, 32+beat+.2, 60+i, 0, 0, 'right')
                  for i, beat in enumerate((7.5, 8, 14.5, 15.1, 15.2)))
    passage = Phrase(1, 9, 12, 32, 48, notes)
    decision = check_rolling_two_bar_window(passage, 'right', 120, [], from_beat=0,
                                          end_beat=16, grid=(0, 4, 8, 12, 16))
    assert decision.errors == decision.missed == 5 and decision.wrong == 0
    assert (decision.restart_beat, decision.end_beat) == (8, 16)


def test_rolling_wrong_pitch_replaces_one_miss_and_extras_do_not_inflate_errors():
    passage = Phrase(1, 1, 4, 0, 16,
                     tuple(Note(i, i+.5, 60+i, 0, 0, 'right') for i in range(16)))
    misses = {4, 5, 6, 8, 9}
    played = [PlayedNote(n.pitch, n.start*.5, n.end*.5)
              for n in passage.notes if n.start not in misses]
    played += [PlayedNote(90, 2, 2.25), PlayedNote(91, 2, 2.25)]
    decision = check_rolling_two_bar_window(passage, 'right', 120, played, from_beat=0,
                                          end_beat=16, grid=(0, 4, 8, 12, 16))
    assert (decision.errors, decision.wrong, decision.missed) == (5, 1, 4)
    played.append(PlayedNote(66, 3, 3.25))  # Four required errors plus an extra.
    assert check_rolling_two_bar_window(passage, 'right', 120, played, from_beat=0,
                                       end_beat=16, grid=(0, 4, 8, 12, 16)) is None


def test_rolling_retry_cannot_invent_misses_before_its_recording_start():
    notes = tuple(Note(i, i+.5, 60+i, 0, 0, 'right') for i in range(16))
    passage = Phrase(1, 1, 4, 0, 16, notes)
    # The previous attempt's three misses in bar two are absent from this take.
    played = [PlayedNote(n.pitch, (n.start-8)*.5, (n.end-8)*.5)
              for n in notes if n.start >= 10]
    assert check_rolling_two_bar_window(passage, 'right', 120, played, from_beat=8,
                                       end_beat=16, grid=(0, 4, 8, 12, 16)) is None


def test_rolling_window_uses_two_source_measures_across_meter_changes():
    # In 3/4 -> 5/4, beats 3..10 are within two source bars but exceed the
    # first meter's fixed six-beat window.
    notes = tuple(Note(beat, beat+.2, 60+i, 0, 0, 'right')
                  for i, beat in enumerate((3, 4, 5, 9, 10)))
    passage = Phrase(1, 1, 4, 0, 16, notes)
    decision = check_rolling_two_bar_window(passage, 'right', 120, [], from_beat=0,
                                          end_beat=16, grid=(0, 3, 6, 11, 16))
    assert decision.errors == 5 and decision.restart_beat == 6


def test_rolling_window_excludes_errors_exactly_two_measures_apart():
    notes = tuple(Note(beat, beat+.2, 60+i, 0, 0, 'right')
                  for i, beat in enumerate((4, 5, 6, 8, 12)))
    passage = Phrase(1, 1, 4, 0, 16, notes)
    assert check_rolling_two_bar_window(passage, 'right', 120, [], from_beat=0,
                                       end_beat=16, grid=(0, 4, 8, 12, 16)) is None


def test_rolling_errors_follow_required_hand_and_count_repeated_attacks():
    notes = tuple(Note(beat, beat+.2, 60, 0, 0, 'left') for beat in (4, 5, 6, 8, 9))
    passage = Phrase(1, 1, 4, 0, 16, notes)
    assert check_rolling_two_bar_window(passage, 'right', 120, [], from_beat=0,
                                       end_beat=16, grid=(0, 4, 8, 12, 16)) is None
    decision = check_rolling_two_bar_window(passage, 'left', 120, [], from_beat=0,
                                          end_beat=16, grid=(0, 4, 8, 12, 16))
    assert decision.errors == 5
