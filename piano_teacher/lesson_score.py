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
    # Spell ordinary durations; retain precise integer durations for others.
    lengths = {4: "whole", 2: "half", 1: "quarter", .5: "eighth",
               .25: "16th", .125: "32nd", .0625: "64th"}
    for beats, label in lengths.items():
        if duration == round(beats * DIVISIONS):
            return label, False
        if duration == round(beats * DIVISIONS * 1.5):
            return label, True
    return None


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
    if pitch is not None and (begin_tie or end_tie):
        if begin_tie:
            ET.SubElement(el, "tie", type="stop")
        if end_tie:
            ET.SubElement(el, "tie", type="start")
        notations = ET.SubElement(el, "notations")
        if begin_tie:
            ET.SubElement(notations, "tied", type="stop")
        if end_tie:
            ET.SubElement(notations, "tied", type="start")


def _render_measure(measure: ET.Element, segments: list[tuple[int, int, int, bool, bool]],
                    length: int) -> None:
    # Merge simultaneous equal-length notes into chords, assign overlapping
    # notes to independent voices, fill gaps with rests.
    chords = defaultdict(list)
    for start, end, pitch, begin_tie, end_tie in segments:
        chords[start, end, begin_tie, end_tie].append(pitch)
    events = sorted([(start, end, first, last, sorted(set(pitches)))
                     for (start, end, first, last), pitches in chords.items()])
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
                _append_note(measure, None, start-position, lane_idx+1)
            for n, pitch in enumerate(pitches):
                _append_note(measure, pitch, end-start, lane_idx+1,
                             chord=n>0, begin_tie=first, end_tie=last)
            position = end
        if position < length:
            _append_note(measure, None, length-position, lane_idx+1)


def build_lesson_score(phrase: Phrase) -> LessonScore:
    if phrase.end <= phrase.start or phrase.last_bar < phrase.first_bar:
        raise ValueError("Lesson must have positive measure duration")
    bars = phrase.last_bar-phrase.first_bar+1
    bar_length = (phrase.end-phrase.start)/bars
    beats, beat_type = _signature(bar_length)
    ticks_per_bar = _ticks(bar_length)
    if ticks_per_bar <= 0:
        raise ValueError("Empty measure")
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
        for b in range(bars):
            measure = ET.SubElement(part, "measure", number=str(phrase.first_bar+b))
            if b == 0:
                attrs = ET.SubElement(measure, "attributes")
                ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
                ET.SubElement(ET.SubElement(attrs, "key"), "fifths").text = "0"
                time = ET.SubElement(attrs, "time")
                ET.SubElement(time, "beats").text = str(beats)
                ET.SubElement(time, "beat-type").text = str(beat_type)
                clef = ET.SubElement(attrs, "clef")
                ET.SubElement(clef, "sign").text = sign
                ET.SubElement(clef, "line").text = line
            bar_start = _ticks(b*bar_length)
            bar_end = _ticks((b+1)*bar_length)
            segments = []
            for note in phrase.notes:
                if note.hand != hand:
                    continue
                start = _ticks(note.start-phrase.start)
                end = _ticks(min(note.end, phrase.end)-phrase.start)
                if start >= bar_end or end <= bar_start:
                    continue
                segment_start=max(start,bar_start)
                segment_end=min(end,bar_end)
                if segment_end > segment_start:
                    segments.append((segment_start-bar_start, segment_end-bar_start,
                                     note.pitch, start < bar_start, end > bar_end))
            _render_measure(measure,segments,bar_end-bar_start)
    return LessonScore(ET.tostring(root, encoding="unicode"), phrase)
