"""Attack admission for authored measure tails on the existing grading clock.

This is an input gate, not an additional matcher. Keep all ordinary
attacks within a measure until its last attack's established matching
window expires; preserve early access to the next measure's first attack.
Releases and Free are handled independently by MIDI ingress.
"""
from bisect import bisect_right

from ..grading_tolerance import match_window
from ..measure_grid import phrase_grid
from .musical_scheduler import SCHEDULER


def accepts_attack(phrase, *, hand, boundaries, bpm, tempo, from_beat,
                   elapsed):
    if phrase is None:
        return False
    grid = phrase_grid(phrase, boundaries)
    origin = SCHEDULER.source_seconds(tempo, from_beat, bpm)

    def at(beat):
        return SCHEDULER.source_seconds(tempo, beat, bpm) - origin

    def window(beat):
        local_bpm = tempo.bpm_at(beat) if tempo is not None else bpm
        return match_window(SCHEDULER.seconds_per_beat(local_bpm))

    attacks = [[] for _ in range(len(grid)-1)]
    for note in phrase.notes:
        beat = note.start-phrase.start
        if beat < from_beat-1e-7 or (hand != "both" and note.hand != hand):
            continue
        index = bisect_right(grid, beat+1e-7)-1
        if 0 <= index < len(attacks):
            attacks[index].append(beat)
    if elapsed < 0:
        first = min((beat for bar in attacks for beat in bar), default=None)
        return first is not None and at(first)-window(first) <= elapsed
    if elapsed >= at(phrase.sounding_end-phrase.start):
        return False
    beat = from_beat+SCHEDULER.elapsed_beats(tempo, from_beat, elapsed, bpm)
    index = bisect_right(grid, beat+1e-7)-1
    if 0 <= index < len(attacks):
        bar = attacks[index]
        if bar:
            last = max(bar)
            if elapsed <= at(last)+window(last):
                return True
    # A first attack of the next measure can legitimately be played early
    # while the current measure is already in its ungraded tail.
    if 0 <= index+1 < len(attacks) and attacks[index+1]:
        first = min(attacks[index+1])
        return at(first)-window(first) <= elapsed
    return False
