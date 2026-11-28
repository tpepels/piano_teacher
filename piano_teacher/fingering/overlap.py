"""Physical fingering constraints for simultaneous and still-held keys."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import accumulate, groupby
from operator import attrgetter

EPS = 1e-5
BLACK_PITCH_CLASSES = {1, 3, 6, 8, 10}


@dataclass(frozen=True, slots=True, eq=False)
class HandNote:
    source_id: str
    pitch: int
    time: float
    duration: float
    left: bool
    finger: int | None

    @property
    def end(self):
        return self.time + self.duration


def overlaps(a, b):
    return a.time < b.end - EPS and b.time < a.end - EPS


class FixedOverlapIndex:
    def __init__(self, fixed):
        self._notes = sorted(fixed, key=attrgetter("time"))
        self._starts = [note.time for note in self._notes]
        # A note starting much earlier can still overlap the whole chord.
        self._prefix_ends = list(accumulate((note.end for note in self._notes), max))

    def overlapping(self, note):
        first = bisect_right(self._prefix_ends, note.time + EPS)
        last = bisect_left(self._starts, note.end - EPS, lo=first)
        for index in range(first, last):
            candidate = self._notes[index]
            if overlaps(candidate, note):
                yield candidate


def _ordinal(finger, left):
    return 6 - finger if left else finger


def _shared_thumb(a, b):
    same_height = (a.pitch % 12 in BLACK_PITCH_CLASSES) == (
        b.pitch % 12 in BLACK_PITCH_CLASSES
    )
    return (a.left == b.left and a.time == b.time and 0 < abs(a.pitch - b.pitch) <= 2
            and same_height)


def _compatible(note, finger, other):
    if note.pitch == other.pitch:
        return finger == other.finger
    return finger != other.finger or (finger == 1 and _shared_thumb(note, other))


def chord_fingers(chord, current, occupied):
    keys = [tuple(members) for _, members in groupby(chord, key=attrgetter("pitch"))]
    if len(keys) > 6:
        return set()
    left = current.left
    fingers = range(5, 0, -1) if left else range(1, 6)
    choices = [
        [finger for finger in fingers
         if all(note.finger in (None, finger) for note in members)
         and all(_compatible(note, finger, other)
                 for note in members for other in occupied if overlaps(note, other))]
        for members in keys
    ]
    allowed = set()

    # Every distinct pitch must fit in order, including earlier unknown notes.
    # Only a pair of simultaneous neighbouring keys may share a thumb.
    def visit(position, previous, thumbs, selected):
        if position == len(keys):
            allowed.add(selected)
            return
        key = keys[position][0]
        for finger in choices[position]:
            ordinal = _ordinal(finger, left)
            if ordinal < previous or (finger == 1 and thumbs == 2):
                continue
            if ordinal == previous and not (
                finger == 1 and thumbs == 1
                and _shared_thumb(keys[position - 1][0], key)
            ):
                continue
            visit(position + 1, ordinal, thumbs + (finger == 1),
                  finger if key.pitch == current.pitch else selected)

    visit(0, 0, 0, None)
    return allowed


def partial_allowed(note, finger, occupied):
    """Keep individually playable notes when the whole chord cannot fit."""
    ordinal = _ordinal(finger, note.left)
    thumb_keys = {note.pitch}
    for other in occupied:
        if not overlaps(note, other):
            continue
        if not _compatible(note, finger, other):
            return False
        if other.pitch == note.pitch:
            continue
        if other.finger == finger:
            thumb_keys.add(other.pitch)
            if len(thumb_keys) > 2:
                return False
        elif other.time == note.time:
            other_ordinal = _ordinal(other.finger, note.left)
            if ((other.pitch < note.pitch and other_ordinal >= ordinal)
                or (other.pitch > note.pitch and other_ordinal <= ordinal)):
                return False
    return True
