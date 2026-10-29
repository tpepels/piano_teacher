"""Metrical beam grouping for reconstructed MIDI notation, never source MusicXML.

MIDI records performed onsets and releases, not engraved beam choices.
Write MusicXML beam metadata here; Verovio owns the ink and Godot consumes its
extracted SVG fragments. No timing, attack identity or exercise selection changes.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET


LEVELS = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}


@dataclass(frozen=True)
class _Event:
    element: ET.Element
    onset: int
    duration: int
    level: int
    rest: bool
    hidden: bool


def _beat_boundaries(beats: int, beat_type: int, divisions: int,
                     measure_ticks: int) -> tuple[int, ...]:
    """Conventional metrical cells; compound 6/8 etc. use dotted beats.

    Odd eighth meters use a documented 2+...+3 default, rather than assuming
    the performed timing encodes an unrecorded composer's accent pattern.
    """
    if beats <= 0 or beat_type <= 0 or divisions <= 0:
        raise ValueError("Invalid meter for MIDI beaming")
    unit = Fraction(4 * divisions, beat_type)
    if unit.denominator != 1:
        return (0, measure_ticks)
    if beat_type in (8, 16) and beats >= 3 and beats % 3 == 0:
        cells = [3] * (beats // 3)
    elif beat_type in (8, 16) and beats >= 5 and beats % 2:
        cells = [2] * ((beats - 3) // 2) + [3]
    elif beat_type in (8, 16):
        cells = [2] * (beats // 2) + ([1] if beats % 2 else [])
    else:
        cells = [1] * beats
    boundaries = [0]
    for count in cells:
        boundaries.append(boundaries[-1] + count * int(unit))
    # A pickup/shortened exercise measure may end before the nominal meter.
    return tuple(sorted({0, measure_ticks, *(
        position for position in boundaries if 0 < position < measure_ticks)}))


def _voice_events(measure: ET.Element) -> dict[str, list[_Event]]:
    lanes: dict[str, list[_Event]] = defaultdict(list)
    cursor = previous_onset = 0
    for child in measure:
        if child.tag in ("backup", "forward"):
            delta = int(child.findtext("duration", "0"))
            cursor += -delta if child.tag == "backup" else delta
            continue
        if child.tag != "note":
            continue
        duration = int(child.findtext("duration", "0"))
        chord = child.find("chord") is not None
        onset = previous_onset if chord else cursor
        if not chord:
            previous_onset = cursor
            cursor += duration
        # Only the chord leader carries beaming. Chord members share its stem.
        if chord:
            continue
        rest = child.find("rest") is not None
        # A nonstandard MIDI release may use an exact time-modification ratio,
        # which should not be misrepresented as a conventional subdivision.
        level = LEVELS.get(child.findtext("type"), 0) if (
            not rest and child.find("time-modification") is None
            and not child.findall("beam")) else 0
        lanes[child.findtext("voice", "1")].append(_Event(
            child, onset, duration, level, rest,
            rest and child.get("print-object") == "no"))
    return lanes


def _mark(note: ET.Element, level: int, label: str) -> None:
    beam = ET.Element("beam", number=str(level))
    beam.text = label
    # MusicXML orders beam before notations, following type/dots/stem/staff.
    index = next((i for i, item in enumerate(note)
                  if item.tag == "notations"), len(note))
    note.insert(index, beam)


def _mark_group(run: list[_Event]) -> None:
    if len(run) < 2:
        return
    for depth in range(1, max(event.level for event in run) + 1):
        cursor = 0
        while cursor < len(run):
            if run[cursor].level < depth:
                cursor += 1
                continue
            end = cursor + 1
            while end < len(run) and run[end].level >= depth:
                end += 1
            if end - cursor == 1:
                if depth > 1:
                    _mark(run[cursor].element, depth,
                          "forward hook" if cursor < len(run) - 1
                          else "backward hook")
            else:
                for i in range(cursor, end):
                    _mark(run[i].element, depth,
                          "begin" if i == cursor else
                          "end" if i == end - 1 else "continue")
            cursor = end


def beam_midi_measure(measure: ET.Element, beats: int, beat_type: int,
                      divisions: int, measure_ticks: int) -> None:
    """Beam only complete adjacent pitched runs in one voice and metric cell.

    Visible rests, rhythmic irregularities, voice boundaries and barlines
    terminate groups. Tiny hidden MIDI-release padding is not an authored rest
    and may be spanned by the beam without altering its underlying duration.
    """
    boundaries = _beat_boundaries(beats, beat_type, divisions, measure_ticks)

    def cell(event: _Event) -> int | None:
        index = bisect_right(boundaries, event.onset) - 1
        if (index < 0 or index >= len(boundaries) - 1
                or event.onset + event.duration > boundaries[index + 1]
                or event.onset < boundaries[index]):
            return None
        return index

    for events in _voice_events(measure).values():
        run: list[_Event] = []
        run_cell: int | None = None
        # Hidden micro-rests represent MIDI key-release articulation, not
        # the composer's written rests. Keep exact cursor positions intact.
        for event in events:
            if event.hidden and event.duration <= divisions // 8:
                continue
            current = cell(event) if event.level else None
            separation = (event.onset - (run[-1].onset + run[-1].duration)
                          if run else 0)
            if (run and (current != run_cell or current is None
                         or separation < 0 or separation > divisions // 8)):
                _mark_group(run)
                run = []
            if current is None:
                if run:
                    _mark_group(run)
                    run = []
                run_cell = None
                continue
            if not run:
                run_cell = current
            run.append(event)
        _mark_group(run)
