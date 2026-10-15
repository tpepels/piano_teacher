"""Compile exactly the active generated exercise events into MusicXML.

The same ExerciseVariant.phrase is used for grading, recovery and engraving.
No notes from the imported score can leak into a simplified lesson.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from collections import defaultdict
from xml.etree import ElementTree as ET
from .music import Phrase
from .measure_grid import phrase_grid

DIVISIONS = 10080


@dataclass(frozen=True)
class LessonScore:
    musicxml: str
    phrase: Phrase


def _ticks(beat: float) -> int:
    return round(beat * DIVISIONS)


def _signature(beats: float) -> tuple[int, int]:
    # Imported time signature preservation beyond bar length is Phase 2.
    fraction = Fraction(beats).limit_denominator(16)
    if abs(float(fraction) - beats) > .005:
        raise ValueError(f"Cannot express exercise bar duration: {beats}")
    if fraction.denominator == 1:
        return fraction.numerator, 4
    return fraction.numerator, 4 * fraction.denominator


def _pitch(parent: ET.Element, value: int) -> None:
    chromatic = ("C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B")
    alterations = (0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0)
    if not 0 <= value <= 127:
        raise ValueError(f"Invalid MIDI pitch {value}")
    p = ET.SubElement(parent, "pitch")
    index = value % 12
    ET.SubElement(p, "step").text = chromatic[index]
    if alterations[index]:
        ET.SubElement(p, "alter").text = "1"
    ET.SubElement(p, "octave").text = str(value // 12 - 1)


def _type(duration: int) -> tuple[str, bool] | None:
    # Spell ordinary durations. Compound values are split before emission.
    lengths = {4: "whole", 2: "half", 1: "quarter", .5: "eighth",
               .25: "16th", .125: "32nd", .0625: "64th"}
    for beats, label in lengths.items():
        if duration == round(beats * DIVISIONS):
            return label, False
        if duration == round(beats * DIVISIONS * 1.5):
            return label, True
    return None


def _duration_parts(duration: int) -> tuple[int, ...]:
    """Spell compounds without relying on Verovio to infer missing types."""
    ordinary = sorted({round(beats * DIVISIONS * dot)
                       for beats in (4, 2, 1, .5, .25, .125, .0625)
                       for dot in (1, 1.5)}, reverse=True)
    parts = []
    remaining = duration
    for length in ordinary:
        while remaining >= length:
            parts.append(length)
            remaining -= length
    if remaining:
        parts.append(remaining)  # Exact residual is represented as a tuplet.
    return tuple(parts)


def _append_note(measure: ET.Element, pitch: int | None, duration: int,
                 voice: int, *, chord=False, begin_tie=False, end_tie=False) -> None:
    el = ET.SubElement(measure, "note")
    if chord:
        ET.SubElement(el, "chord")
    if pitch is None:
        ET.SubElement(el, "rest")
    else:
        _pitch(el, pitch)
    ET.SubElement(el, "duration").text = str(duration)
    ET.SubElement(el, "voice").text = str(voice)
    spelling = _type(duration)
    if spelling:
        ET.SubElement(el, "type").text = spelling[0]
        if spelling[1]:
            ET.SubElement(el, "dot")
    else:
        # MIDI onsets can lie between ordinary note values. MusicXML duration
        # alone is insufficient: Verovio derives its timemap from type and
        # time-modification. Preserve the integer duration with an exact ratio.
        ET.SubElement(el, "type").text = "64th"
        ratio = Fraction(duration, DIVISIONS // 16)
        modification = ET.SubElement(el, "time-modification")
        ET.SubElement(modification, "actual-notes").text = str(ratio.denominator)
        ET.SubElement(modification, "normal-notes").text = str(ratio.numerator)
    if pitch is not None and (begin_tie or end_tie):
        if begin_tie:
            ET.SubElement(el, "tie", type="stop")
        if end_tie:
            ET.SubElement(el, "tie", type="start")
    if (pitch is not None and (begin_tie or end_tie)) or not spelling:
        notations = ET.SubElement(el, "notations")
    if pitch is not None and (begin_tie or end_tie):
        if begin_tie:
            ET.SubElement(notations, "tied", type="stop")
        if end_tie:
            ET.SubElement(notations, "tied", type="start")
    if not spelling:
        # Verovio requires explicit tuplet notation as well as the ratio;
        # a time-modification by itself is ignored in its quarter-beat map.
        ET.SubElement(notations, "tuplet", type="start", number="1",
                      bracket="no", **{"show-number": "none"})
        ET.SubElement(notations, "tuplet", type="stop", number="1")


def _append_event(measure: ET.Element, pitches: list[int] | list[None], duration: int,
                  voice: int, *, begin_tie=False, end_tie=False) -> None:
    parts = _duration_parts(duration)
    for index, length in enumerate(parts):
        # Emit every chord tone together in each tied segment. Splitting each
        # pitch independently would attach chord tags to the wrong time slot.
        for chord_index, pitch in enumerate(pitches):
            _append_note(measure, pitch, length, voice, chord=chord_index > 0,
                         begin_tie=begin_tie or index > 0,
                         end_tie=end_tie or index < len(parts)-1)


def _render_measure(measure: ET.Element, segments: list[tuple[int, int, int, bool, bool]],
                    length: int) -> None:
    # Merge simultaneous equal-length notes into chords, assign overlapping
    # notes to independent voices, fill gaps with rests.
    chords = defaultdict(list)
    for start, end, pitch, begin_tie, end_tie in segments:
        chords[start, end, begin_tie, end_tie].append(pitch)
    events = []
    for (start, end, first, last), pitches in chords.items():
        # Same-pitch unisons from different source tracks are separate
        # assessable events; retain one in each independent voice.
        remaining = sorted(pitches)
        while remaining:
            layer = sorted(set(remaining))
            events.append((start, end, first, last, layer))
            for pitch in layer:
                remaining.remove(pitch)
    events.sort()
    lanes: list[list[tuple]] = []
    endings: list[int] = []
    for event in events:
        start, end, *_ = event
        lane = next((i for i, finished in enumerate(endings) if finished <= start), None)
        if lane is None:
            lane = len(lanes)
            lanes.append([])
            endings.append(0)
        lanes[lane].append(event)
        endings[lane] = end
    if not lanes:
        lanes = [[]]
    for lane_idx, events in enumerate(lanes):
        if lane_idx:
            backup = ET.SubElement(measure, "backup")
            ET.SubElement(backup, "duration").text = str(length)
        position = 0
        for start, end, first, last, pitches in events:
            if start > position:
                _append_event(measure, [None], start-position, lane_idx+1)
            _append_event(measure, pitches, end-start, lane_idx+1,
                          begin_tie=first, end_tie=last)
            position = end
        if position < length:
            _append_event(measure, [None], length-position, lane_idx+1)


def build_lesson_score(phrase: Phrase, *, boundaries: tuple[float, ...] = (),
                       time_signatures: tuple[tuple[float, int, int], ...] = ()) -> LessonScore:
    """Create notation from the source measure grid, not averaged bars."""
    grid = phrase_grid(phrase, boundaries)
    bars = len(grid) - 1
    changes = sorted(time_signatures)

    def meter_at(beat: float, length: float) -> tuple[int, int]:
        active = [(n, d) for offset, n, d in changes if offset <= beat + 1e-7]
        return active[-1] if active else _signature(length)

    root = ET.Element("score-partwise", version="4.0")
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = " "
    partlist = ET.SubElement(root, "part-list")
    for ident, name in (("RH", "Right hand"), ("LH", "Left hand")):
        scorepart = ET.SubElement(partlist, "score-part", id=ident)
        ET.SubElement(scorepart, "part-name").text = name
        ET.SubElement(scorepart, "part-abbreviation").text = "R.H." if ident == "RH" else "L.H."
    for hand, ident, sign, line in (("right", "RH", "G", "2"),
                                    ("left", "LH", "F", "4")):
        part = ET.SubElement(root, "part", id=ident)
        last_meter = None
        for b in range(bars):
            bar_start, bar_end = _ticks(grid[b]), _ticks(grid[b+1])
            if bar_end <= bar_start:
                raise ValueError("Source measure has no duration")
            beats, beat_type = meter_at(phrase.start + grid[b], grid[b+1] - grid[b])
            if beats <= 0 or beat_type <= 0:
                raise ValueError("Invalid imported time signature")
            measure = ET.SubElement(part, "measure", number=str(phrase.first_bar+b))
            if abs((beats * 4.0 / beat_type) - (grid[b+1] - grid[b])) > 1e-5:
                measure.set("implicit", "yes")
            if b == 0 or (beats, beat_type) != last_meter:
                attrs = ET.SubElement(measure, "attributes")
                if b == 0:
                    ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
                    ET.SubElement(ET.SubElement(attrs, "key"), "fifths").text = "0"
                time = ET.SubElement(attrs, "time")
                ET.SubElement(time, "beats").text = str(beats)
                ET.SubElement(time, "beat-type").text = str(beat_type)
                if b == 0:
                    clef = ET.SubElement(attrs, "clef")
                    ET.SubElement(clef, "sign").text = sign
                    ET.SubElement(clef, "line").text = line
            last_meter = (beats, beat_type)
            segments = []
            for note in phrase.notes:
                if note.hand != hand:
                    continue
                start = _ticks(note.start-phrase.start)
                end = _ticks(min(note.end, phrase.end)-phrase.start)
                # MIDI key-off timings commonly stop slightly before a beat
                # (e.g. 0.90 beats). That is expressive release timing, not
                # necessarily a notated 0.10-beat rest. Snap *only* a nearby
                # note ending to a 16th-note boundary for readable MusicXML.
                # The original Note retains its exact timestamp for scoring.
                duration_grid = DIVISIONS // 4
                rounded_end = round(end / duration_grid) * duration_grid
                if 0 < rounded_end - start and abs(rounded_end-end) <= _ticks(.12):
                    end = min(rounded_end, _ticks(phrase.end-phrase.start))
                if start >= bar_end or end <= bar_start:
                    continue
                segment_start=max(start,bar_start)
                segment_end=min(end,bar_end)
                if segment_end > segment_start:
                    segments.append((segment_start-bar_start, segment_end-bar_start,
                                     note.pitch, start < bar_start, end > bar_end))
            _render_measure(measure,segments,bar_end-bar_start)
    return LessonScore(ET.tostring(root, encoding="unicode"), phrase)
