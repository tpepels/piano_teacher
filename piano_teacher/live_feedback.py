"""Incremental student feedback for the most recent two-bar practice window.

Only settled notes are scored. Waiting for the expected release and an onset
grace period avoids false "missed" or "short" flashes while a key is held.
No video-frame clock or Godot interaction is involved.
"""
from __future__ import annotations
from .music import Phrase
from .optional_notes import relative_optional_notes
from .practice import Assessment, NoteAssessment, PlayedNote, evaluate


def settled_assessment(phrase: Phrase, hand: str, bpm: float,
                       played: list[PlayedNote], *, from_beat: float,
                       until_beat: float, beats_per_bar: float,
                       optional_notes: tuple[dict, ...] = ()) -> Assessment | None:
    if bpm <= 0 or beats_per_bar <= 0:
        raise ValueError("Tempo and measure length must be positive")
    grace = .12 * bpm / 60  # 120 ms after expected note release
    earliest = max(from_beat, until_beat - 2*beats_per_bar)
    required = tuple(
        n for n in phrase.notes
        if (hand == "both" or n.hand == hand)
        and phrase.start+earliest-1e-7 <= n.start
        and n.end <= phrase.start+until_beat-grace+1e-7
    )
    if not required:
        return None
    # PlayedNote timestamps have the same origin as the whole current take.
    # Keeping that origin avoids drift at restarts and recovery sub-passages.
    passage = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                     phrase.start+from_beat, phrase.end, required)
    # Do not classify notes that occur later in the take as "extras" yet.
    # This also makes deterministic prerecorded performance fixtures valid.
    upto = (until_beat-from_beat)*60/bpm+.12
    since = max(0.0,(earliest-from_beat)*60/bpm-.15)
    eligible = [n for n in played if since <= n.onset <= upto]
    result = evaluate(passage, hand, bpm, eligible,
                      optional_notes=relative_optional_notes(optional_notes, from_beat))
    # Project only required settled notes here. Early/key mistakes remain
    # marked at their corresponding noteheads; extra-note labels are shown
    # in the final assessment to avoid a misleading moving marker.
    return Assessment(result.notes, 0, ())


def expired_attack_misses(phrase: Phrase, hand: str, bpm: float,
                          played: list[PlayedNote], *, from_beat: float,
                          until_beat: float,
                          window_start_beat: float | None = None,
                          optional_notes: tuple[dict, ...] = ()) -> Assessment | None:
    """Mark only individual missing pitches after their allowable onset window.

    A two-beat held chord must not wait for release before its unplayed
    pitches become red. Use exactly the same pitch/onset matching window as
    evaluate(), so a valid late note cannot first flash as missing.
    This is a display-only assessment: it never increments failure counts.
    optional_notes is accepted for parity with settled/final assessment, but
    grace pitches cannot clear a required miss; only exact required attacks do.
    """
    if bpm <= 0:
        raise ValueError("Tempo must be positive")
    seconds_per_beat = 60.0 / bpm
    search_window = max(.35, .65 * seconds_per_beat)
    elapsed = (until_beat - from_beat) * seconds_per_beat
    start = max(from_beat, window_start_beat if window_start_beat is not None else from_beat)
    required = [
        note for note in phrase.notes
        if (hand == "both" or note.hand == hand)
        and note.start - phrase.start >= start - 1e-7
        and ((note.start - phrase.start - from_beat) * seconds_per_beat
             + search_window <= elapsed + 1e-7)
    ]
    unused = set(range(len(played)))
    misses = []
    for note in required:
        onset = (note.start - phrase.start - from_beat) * seconds_per_beat
        candidates = [
            (abs(played[index].onset - onset), index)
            for index in unused
            if played[index].pitch == note.pitch
            and abs(played[index].onset - onset) <= search_window
        ]
        if candidates:
            unused.remove(min(candidates)[1])
        else:
            misses.append(NoteAssessment(note, "missed"))
    return Assessment(tuple(misses), 0, ()) if misses else None
