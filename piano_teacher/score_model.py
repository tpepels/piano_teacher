"""Renderer-independent, versioned semantic score for a *single exercise*.

Phase A: translate the lesson's source notes and its MusicXML notation into
an explicit transport-agnostic contract. No Verovio, SVG, PNG, Godot or BPM
enters the score model. The MIDI grader and Listen still consume the original
Phrase; this is a lossless, verified projection of that same Phrase.

All beats are quarter-note units relative to phrase.start.  An attack is
one physical source note, even when its printed notation contains several
tied glyphs. Notation events describe all printed glyphs, including rests.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from .lesson_score import DIVISIONS, LessonScore
from .measure_grid import phrase_grid
from .music import Phrase, source_note_id

SCHEMA = "piano-teacher-score-model-v1"
HANDS = ("right", "left")
PART_HAND = {"RH": "right", "LH": "left"}
_TOLERANCE = 1.0 / DIVISIONS + 1e-7


@dataclass(frozen=True)
class ScoreNote:
    id: str
    onset_beats: float
    duration_beats: float
    midi_pitch: int
    velocity: int
    hand: str
    voice: str
    track: int
    channel: int
    spelling: tuple[str, int, int] | None


@dataclass(frozen=True)
class ScoreMeasure:
    number: int
    start_beat: float
    end_beat: float
    meter: tuple[int, int]
    keys: dict[str, int]
    clefs: dict[str, dict]
    left_barline: dict | None = None
    right_barline: dict | None = None


# Compatibility names retained for existing tests and callers.
# Both source import and semantic model use the independent parser.
from .notation.musicxml import BARLINE_STYLES, parse_barline
_barline_data = parse_barline


@dataclass(frozen=True)
class ScoreSymbol:
    id: str
    source_id: str | None
    staff: str
    voice: str
    measure: int
    beat: float
    duration_beats: float
    kind: str
    midi_pitch: int | None
    spelling: dict | None
    note_type: str | None
    dots: int
    chord: bool
    tie_start: bool
    tie_stop: bool
    is_attack: bool
    accidental: str | None
    time_modification: dict | None
    tuplet_marks: tuple[dict, ...]


def _int(element: ET.Element, name: str, default: int | None = None) -> int:
    raw = element.findtext(name)
    if raw is None:
        if default is None:
            raise ValueError(f"Missing MusicXML {name}")
        return default
    return int(raw)


def _notes(phrase: Phrase) -> tuple[ScoreNote, ...]:
    notes = []
    ids = set()
    for index, note in enumerate(phrase.notes):
        identifier = source_note_id(note, index)
        if identifier in ids:
            raise ValueError(f"Duplicate source attack identity: {identifier}")
        if note.hand not in HANDS or not 0 <= note.pitch <= 127:
            raise ValueError(f"Invalid source hand or pitch: {identifier}")
        if not all(math.isfinite(v) for v in (note.start, note.end)):
            raise ValueError(f"Non-finite source note timing: {identifier}")
        if not phrase.start - 1e-7 <= note.start < min(note.end, phrase.end):
            raise ValueError(f"Source note lies outside exercise: {identifier}")
        ids.add(identifier)
        notes.append(ScoreNote(
            identifier, round(note.start - phrase.start, 8),
            round(min(note.end, phrase.end) - note.start, 8),
            note.pitch, note.velocity, note.hand, note.voice,
            note.track, note.channel, note.spelling))
    return tuple(sorted(notes, key=lambda item: (
        item.onset_beats, item.hand, item.midi_pitch, item.id)))


def _parse_notation(score: LessonScore, grid: tuple[float, ...]
                    ) -> tuple[tuple[ScoreMeasure, ...], tuple[ScoreSymbol, ...]]:
    root = ET.fromstring(score.musicxml)
    parts = {part.get("id"): part for part in root.findall("part")}
    if set(parts) != set(PART_HAND):
        raise ValueError("The exercise must contain RH and LH notation parts")
    count = len(grid) - 1
    first_bar = score.phrase.first_bar
    symbols: list[ScoreSymbol] = []
    measures: list[ScoreMeasure] = []
    segment_ids = set()
    meters: dict[int, tuple[int, int]] = {}
    keys: dict[int, dict[str, int]] = {}
    clefs: dict[int, dict[str, dict]] = {}
    barlines: dict[int, dict[str, dict]] = {}
    for part_id, hand in PART_HAND.items():
        part_measures = parts[part_id].findall("measure")
        if len(part_measures) != count:
            raise ValueError(f"{hand} has an incorrect measure count")
        divisions = DIVISIONS
        current_meter: tuple[int, int] | None = None
        current_key = 0
        current_clef: dict = {"sign": "G" if hand == "right" else "F",
                              "line": 2 if hand == "right" else 4,
                              "octave_change": 0}
        for bar_index, measure in enumerate(part_measures):
            number = first_bar + bar_index
            if int(measure.get("number", "-1")) != number:
                raise ValueError("Source measure numbering differs between parts")
            ticks_in_bar = round((grid[bar_index + 1] - grid[bar_index]) * divisions)
            local_barlines: dict[str, dict] = {}
            for tag in measure.findall("barline"):
                location, mark = _barline_data(tag)
                if location in local_barlines and local_barlines[location] != mark:
                    raise ValueError("Conflicting barlines within a MusicXML measure")
                local_barlines[location] = mark
            shared = barlines.setdefault(bar_index, {})
            for location, mark in local_barlines.items():
                if location in shared and shared[location] != mark:
                    raise ValueError("Inconsistent barlines between piano hands")
                shared[location] = mark
            cursor = 0
            last_onset: int | None = None
            for child in measure:
                if child.tag == "attributes":
                    if child.find("divisions") is not None:
                        divisions = _int(child, "divisions")
                        if divisions != DIVISIONS:
                            raise ValueError("Unexpected MusicXML divisions")
                    if child.find("time") is not None:
                        time = child.find("time")
                        current_meter = (_int(time, "beats"), _int(time, "beat-type"))
                    if child.find("key") is not None:
                        current_key = _int(child.find("key"), "fifths", 0)
                    if child.find("clef") is not None:
                        tag = child.find("clef")
                        current_clef = {
                            "sign": tag.findtext("sign", current_clef["sign"]),
                            "line": _int(tag, "line", current_clef["line"]),
                            "octave_change": _int(tag, "clef-octave-change", 0)}
                    continue
                if child.tag in ("backup", "forward"):
                    amount = _int(child, "duration")
                    cursor += amount if child.tag == "forward" else -amount
                    if not 0 <= cursor <= ticks_in_bar:
                        raise ValueError("MusicXML voice cursor crossed a measure boundary")
                    last_onset = None
                    continue
                if child.tag != "note":
                    continue
                duration_ticks = _int(child, "duration")
                if duration_ticks <= 0:
                    raise ValueError("Zero-length engraved symbol")
                chord = child.find("chord") is not None
                if chord and last_onset is None:
                    raise ValueError("Chord tone without an initial note")
                onset_ticks = last_onset if chord else cursor
                if onset_ticks < 0 or onset_ticks + duration_ticks > ticks_in_bar:
                    raise ValueError("Engraved symbol extends past its source measure")
                if not chord:
                    last_onset = onset_ticks
                    cursor += duration_ticks
                at_beat = round(grid[bar_index] + onset_ticks / divisions, 8)
                pitch_tag = child.find("pitch")
                rest = child.find("rest") is not None
                if rest == (pitch_tag is not None):
                    raise ValueError("Notation event must be a note or rest")
                identifier = child.get("id")
                binding = score.note_bindings.get(identifier) if identifier else None
                if pitch_tag is not None:
                    if identifier is None or binding is None:
                        raise ValueError("Engraved source note lost its identity")
                    if identifier in segment_ids:
                        raise ValueError("Duplicated engraved segment identity")
                    segment_ids.add(identifier)
                    step = pitch_tag.findtext("step")
                    alter = _int(pitch_tag, "alter", 0)
                    octave = _int(pitch_tag, "octave")
                    semitone = {"C": 0, "D": 2, "E": 4, "F": 5,
                                "G": 7, "A": 9, "B": 11}.get(step)
                    if semitone is None:
                        raise ValueError("Invalid pitch step")
                    pitch = (octave + 1) * 12 + semitone + alter
                    if pitch != binding["pitch"] or binding["hand"] != hand:
                        raise ValueError("Engraved note pitch/hand diverges from source")
                    if abs(at_beat - binding["display_beat"]) > _TOLERANCE:
                        raise ValueError("Engraved display timing diverges from binding")
                    spelling = {"step": step, "alter": alter, "octave": octave}
                    source_id = binding["source_id"]
                    is_attack = bool(binding["is_attack"])
                else:
                    identifier = f"rest:{hand}:{number}:{len(symbols)}"
                    pitch, spelling, source_id, is_attack = None, None, None, False
                modification = child.find("time-modification")
                time_modification = ({
                    "actual": _int(modification, "actual-notes"),
                    "normal": _int(modification, "normal-notes")}
                    if modification is not None else None)
                tie_types = {tie.get("type") for tie in child.findall("tie")}
                # Preserve MusicXML's explicit group limits. The native
                # renderer must not guess grouping from duration ratios:
                # unusual MIDI timings can also have time-modification.
                tuplet_marks = tuple({
                    "type": tag.get("type"),
                    "number": tag.get("number", "1"),
                    "bracket": tag.get("bracket", "no"),
                    "show_number": tag.get("show-number", "actual"),
                } for tag in child.findall("notations/tuplet"))
                symbols.append(ScoreSymbol(
                    identifier, source_id, hand, child.findtext("voice", "1"),
                    number, at_beat, round(duration_ticks / divisions, 8),
                    "rest" if rest else "note", pitch, spelling,
                    child.findtext("type"), len(child.findall("dot")), chord,
                    "start" in tie_types, "stop" in tie_types,
                    is_attack, child.findtext("accidental"), time_modification,
                    tuplet_marks))
            if current_meter is None:
                raise ValueError("No meter for a source measure")
            if cursor != ticks_in_bar:
                raise ValueError(f"Incomplete {hand} measure {number}")
            if bar_index in meters and meters[bar_index] != current_meter:
                raise ValueError("Inconsistent meter between piano staves")
            meters[bar_index] = current_meter
            # Different written key signatures per staff are legal in
            # imported scores; don't silently force them to agree.
            keys.setdefault(bar_index, {})[hand] = current_key
            clefs.setdefault(bar_index, {})[hand] = current_clef.copy()
    for bar_index in range(count):
        boundary = barlines.get(bar_index, {})
        measures.append(ScoreMeasure(first_bar + bar_index, grid[bar_index],
            grid[bar_index + 1], meters[bar_index], keys[bar_index], clefs[bar_index],
            boundary.get("left"), boundary.get("right", {
                "style": "regular", "repeat": ""})))
    if set(score.note_bindings) != segment_ids:
        raise ValueError("Unmatched printed note segments")
    return tuple(measures), tuple(symbols)


def build_score_model(score: LessonScore, *, boundaries: tuple[float, ...] = (),
                      hand: str = "both", revision: int = 0) -> dict:
    """Export source-accurate score independent of raster layout and BPM.

    The score is static musical content. Playback state and visual coordinates
    deliberately do not belong here; the Godot renderer will choose its own
    pixels-per-beat without changing any notation or MIDI assessment.
    """
    if hand not in (*HANDS, "both"):
        raise ValueError("Invalid active hand")
    phrase = score.phrase
    grid = phrase_grid(phrase, boundaries)
    notes = _notes(phrase)
    measures, symbols = _parse_notation(score, grid)
    sources = {note.id: note for note in notes}
    attacks = {}
    for event in symbols:
        if event.kind != "note":
            continue
        if event.source_id not in sources:
            raise ValueError("Printed note refers to an unknown source attack")
        if event.is_attack:
            if event.source_id in attacks:
                raise ValueError("One source attack has multiple printed attacks")
            attacks[event.source_id] = event
            if abs(event.beat - sources[event.source_id].onset_beats) > _TOLERANCE:
                raise ValueError("Printed attack differs from the MIDI scoring onset")
    if set(attacks) != set(sources):
        raise ValueError("Engraved lesson and MIDI grading have different note sets")
    model = {
        "schema": SCHEMA,
        "revision": revision,
        "first_bar": phrase.first_bar,
        "last_bar": phrase.last_bar,
        "duration_beats": round(phrase.end - phrase.start, 8),
        "beat_unit": "quarter",
        "active_hand": hand,
        "staff_order": list(HANDS),
        # Return genuine JSON value types, not Python tuples that change
        # shape when the HTTP layer serializes the payload.
        "measures": [{**asdict(m), "meter": list(m.meter)} for m in measures],
        "notes": [{**asdict(note), "spelling": (
            list(note.spelling) if note.spelling is not None else None)}
            for note in notes],
        "notation_events": [{**asdict(symbol), "tuplet_marks": [
            dict(mark) for mark in symbol.tuplet_marks]}
            for symbol in symbols],
        "active_note_ids": [note.id for note in notes
                            if hand == "both" or hand == note.hand],
    }
    return model
