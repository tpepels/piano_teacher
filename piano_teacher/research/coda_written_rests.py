"""Source-backed written rests for Coda research, separate from MIDI silence.

This is an immutable notation sidecar, not a complete implementation of
Coda's hierarchical MMR. It preserves original MusicXML identities and
voice/staff ownership without guessing a piano hand for rest-only voices.
Forward/backup cursor moves are never fabricated as authored rests.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET


@dataclass(frozen=True)
class MatrixWrittenRest:
    source_id: str
    part_index: int
    staff: str
    voice: str
    measure: int
    onset: float
    end: float
    note_type: str
    dots: int
    visible: bool
    full_measure: bool

    @property
    def voice_id(self) -> str:
        return f"xml-p{self.part_index}-s{self.staff}-v{self.voice}"


def _positive_fraction(value: str | None, label: str) -> Fraction:
    try:
        number = Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid MusicXML {label}") from exc
    if number <= 0:
        raise ValueError(f"MusicXML {label} must be positive")
    return number


def extract_written_rests(source_musicxml: str, *, first_bar: int,
                          last_bar: int, boundaries: tuple[float, ...]
                          ) -> tuple[MatrixWrittenRest, ...]:
    """Read original rests using source divisions and per-part MusicXML cursors.

    The grid covers the selected phrase. Read earlier measures to inherit
    the correct divisions, but emit only rests in the selected bar range.
    """
    if not source_musicxml:
        return ()
    if (first_bar < 1 or last_bar < first_bar
            or len(boundaries) != last_bar - first_bar + 2):
        raise ValueError("Written rests require a complete phrase measure grid")
    root = ET.fromstring(source_musicxml)
    if root.tag.rsplit("}", 1)[-1] != "score-partwise":
        raise ValueError("Written rests require score-partwise MusicXML")
    result: list[MatrixWrittenRest] = []
    for part_index, part in enumerate(root.findall("{*}part")):
        measures = part.findall("{*}measure")
        if len(measures) < last_bar:
            raise ValueError("MusicXML is missing requested source measures")
        divisions = Fraction(1)
        for mi, measure in enumerate(measures[:last_bar]):
            cursor = Fraction(0)
            previous_onset: Fraction | None = None
            for ordinal, element in enumerate(measure):
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "attributes":
                    value = element.findtext("{*}divisions")
                    if value is not None:
                        divisions = _positive_fraction(value, "divisions")
                elif tag in ("backup", "forward"):
                    delta = _positive_fraction(
                        element.findtext("{*}duration"), "cursor duration") / divisions
                    cursor += delta if tag == "forward" else -delta
                    if cursor < 0:
                        raise ValueError("MusicXML backup precedes measure")
                    previous_onset = None
                elif tag == "note":
                    if element.find("{*}grace") is not None:
                        continue
                    duration = _positive_fraction(
                        element.findtext("{*}duration"), "note duration") / divisions
                    is_chord = element.find("{*}chord") is not None
                    if is_chord:
                        if previous_onset is None:
                            raise ValueError("MusicXML chord without preceding attack")
                        onset = previous_onset
                    else:
                        onset = cursor
                        previous_onset = cursor
                        cursor += duration
                    rest_tag = element.find("{*}rest")
                    if rest_tag is None:
                        continue
                    if is_chord:
                        raise ValueError("MusicXML rest cannot be a chord tone")
                    if first_bar - 1 <= mi < last_bar:
                        local = mi - (first_bar - 1)
                        start = float(Fraction(str(boundaries[local])) + onset)
                        end = start + float(duration)
                        if start < boundaries[local] - 1e-7 or end > boundaries[local + 1] + 1e-7:
                            raise ValueError("Written rest exceeds source measure grid")
                        result.append(MatrixWrittenRest(
                            f"xml-p{part_index}-m{mi}-e{ordinal}", part_index,
                            element.findtext("{*}staff", "1"),
                            element.findtext("{*}voice", "1"),
                            first_bar + local, start, end,
                            element.findtext("{*}type", ""),
                            len(element.findall("{*}dot")),
                            element.get("print-object", "yes") != "no",
                            rest_tag.get("measure") == "yes"))
    return tuple(result)
