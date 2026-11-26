"""Live projection of the canonical grader, without a second note matcher."""
from __future__ import annotations

from .assessment_clock import expected_note_seconds
from .exercise_contracts import TempoMap
from .lesson_settings import SETTINGS
from .grading_tolerance import onset_tolerance
from .music import Phrase
from .practice import Assessment, PlayedNote, evaluate
from .application.musical_scheduler import SCHEDULER


def live_scope(phrase: Phrase, *, from_beat: float, elapsed_seconds: float,
               bpm: float, tempo: TempoMap | None = None) -> tuple[float, float]:
    """Bound display work only; canonical matching still sees the full take."""
    origin = tempo.seconds_at(from_beat) if tempo is not None else 0.0
    beat = (tempo.beat_at(origin+max(0.,elapsed_seconds)) if tempo is not None
            else from_beat+SCHEDULER.seconds_beats(max(0.,elapsed_seconds),bpm))
    bar = (phrase.end-phrase.start)/max(1,phrase.last_bar-phrase.first_bar+1)
    start = max(from_beat,beat-2*bar)
    seconds = (tempo.seconds_at(start)-origin if tempo is not None else
               SCHEDULER.beats_seconds(start-from_beat,bpm))
    return start, seconds


def live_assessment(phrase: Phrase, hand: str, bpm: float,
                    played: list[PlayedNote], *, from_beat: float,
                    elapsed_seconds: float,
                    tempo: TempoMap | None = None,
                    grade_note_holds: bool = False,
                    whole_take: bool = False) -> Assessment:
    """Use final scoring's assignment and recorded time, with no mutable matches.

    An accepted early attack may light its upcoming head. An erroneous early
    attack waits until that source onset; missing notes wait for the canonical
    matching window. No live view ever claims a distant future head.
    """
    if bpm <= 0:
        raise ValueError("Tempo must be positive")
    notes = tuple(note for note in phrase.notes
                  if note.start - phrase.start >= from_beat - 1e-7)
    selected = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                      phrase.start + from_beat, phrase.end, notes)
    eligible = [event for event in played if event.onset <= elapsed_seconds + 1e-7]
    _, since = live_scope(phrase,from_beat=from_beat,
        elapsed_seconds=elapsed_seconds,bpm=bpm,tempo=tempo)
    slowest = min((segment.bpm for segment in tempo.segments),default=bpm) if tempo else bpm
    result = evaluate(selected, hand, bpm, eligible,
                      expected_seconds=(expected_note_seconds(phrase, tempo, from_beat)
                                        if tempo is not None else None),
                      observation_window=(None if whole_take else
                          (since,elapsed_seconds+onset_tolerance(
                              SCHEDULER.seconds_per_beat(slowest)))),
                      grade_note_holds=grade_note_holds)
    visible = []
    provisional_extra = []
    for entry in result.notes:
        observation = entry.observation
        if observation is None:
            continue
        onset = observation.expected_onset
        if observation.actual_onset is None:
            window = max(SETTINGS.grading_match_window_min_seconds,
                         SETTINGS.grading_match_window_beats * observation.local_seconds_per_beat)
            deadline = onset + window
            if observation.next_attack_onset is not None:
                deadline = min(deadline, observation.next_attack_onset)
            if deadline > elapsed_seconds:
                continue
        elif onset > elapsed_seconds + 1e-7:
            if (onset - elapsed_seconds > observation.onset_tolerance + 1e-7
                    or observation.timing_error is not None or observation.pitch_error):
                # An already played attack cannot disappear from the live
                # score merely because its provisional assignment is future.
                if whole_take and observation.played_index is not None:
                    provisional_extra.append(eligible[observation.played_index])
                continue
        visible.append(entry)
    # Unmatched physical presses already travel through FeedbackEventLog as
    # actual-pitch ghosts. Never invent a second estimated ghost position.
    if whole_take:
        # Unmatched presses count against accuracy immediately. Future notes
        # do not count until matched near their onset or their window expires.
        extras = result.unmatched_played + tuple(provisional_extra)
        return Assessment(tuple(visible), len(extras), extras)
    return Assessment(tuple(visible), 0)
