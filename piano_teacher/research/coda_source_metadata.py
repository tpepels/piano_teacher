"""Ordered, source-identical MusicXML elements for Coda research.

Keeps the *written* score alongside MIDI attack timing. This is a lossless
source-XML element inventory, not a reconstruction of Coda's published MMR
or a claim that every MusicXML construct is engravable after retiming.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET

from .coda_written_rests import _positive_fraction


@dataclass(frozen=True)
class MatrixSourceElement:
    source_id: str
    part_index: int
    measure: int
    ordinal: int
    kind: str
    onset: float
    end: float | None
    voice_id: str | None
    xml: str

    @property
    def is_timed_note(self) -> bool:
        return self.kind == "note" and self.end is not None

    @property
    def is_rest(self) -> bool:
        return self.is_timed_note and ET.fromstring(self.xml).find("{*}rest") is not None


def source_elements(source_musicxml: str, *, first_bar: int, last_bar: int,
                    boundaries: tuple[float, ...]) -> tuple[MatrixSourceElement, ...]:
    """Preserve every direct measure child and its source order/position.

    Meter, key, clef, barlines, dynamics, pedal, lyrics, slurs, ties,
    beams, articulations, ornaments and tuplet metadata remain in their
    original XML subtrees. Unknown tags are kept rather than discarded.
    """
    if not source_musicxml:
        return ()
    if (first_bar < 1 or last_bar < first_bar
            or len(boundaries) != last_bar - first_bar + 2):
        raise ValueError("Source metadata requires a complete phrase grid")
    root = ET.fromstring(source_musicxml)
    if root.tag.rsplit("}", 1)[-1] != "score-partwise":
        raise ValueError("Source metadata requires score-partwise MusicXML")
    result: list[MatrixSourceElement] = []
    for pi, part in enumerate(root.findall("{*}part")):
        measures = part.findall("{*}measure")
        if len(measures) < last_bar:
            raise ValueError("MusicXML missing requested measures")
        divisions = Fraction(1)
        for mi, measure in enumerate(measures[:last_bar]):
            cursor = Fraction(0)
            previous: Fraction | None = None
            for ordinal, element in enumerate(measure):
                kind = element.tag.rsplit("}", 1)[-1]
                location = cursor
                end: Fraction | None = None
                voice_id: str | None = None
                if kind == "attributes":
                    value = element.findtext("{*}divisions")
                    if value is not None:
                        divisions = _positive_fraction(value, "divisions")
                elif kind in ("backup", "forward"):
                    duration = _positive_fraction(
                        element.findtext("{*}duration"), "cursor duration") / divisions
                    cursor += duration if kind == "forward" else -duration
                    if cursor < 0:
                        raise ValueError("MusicXML backup precedes measure")
                    previous = None
                elif kind == "note":
                    staff = element.findtext("{*}staff", "1")
                    voice = element.findtext("{*}voice", "1")
                    voice_id = f"xml-p{pi}-s{staff}-v{voice}"
                    if element.find("{*}grace") is None:
                        duration = _positive_fraction(
                            element.findtext("{*}duration"), "note duration") / divisions
                        if element.find("{*}chord") is not None:
                            if previous is None:
                                raise ValueError("MusicXML chord without predecessor")
                            location = previous
                        else:
                            previous = cursor
                            cursor += duration
                        end = location + duration
                    else:
                        location = previous if element.find("{*}chord") is not None and previous is not None else cursor
                elif kind == "direction":
                    staff = element.findtext("{*}staff", "1")
                    voice = element.findtext("{*}voice")
                    if voice is not None:
                        voice_id = f"xml-p{pi}-s{staff}-v{voice}"
                    offset = element.findtext("{*}offset")
                    if offset is not None:
                        location += Fraction(offset) / divisions
                if first_bar - 1 <= mi < last_bar:
                    local = mi + 1 - first_bar
                    beginning = Fraction(str(boundaries[local]))
                    absolute = float(beginning + location)
                    ending = float(beginning + end) if end is not None else None
                    if (absolute < boundaries[local] - 1e-7
                            or absolute > boundaries[local+1] + 1e-7
                            or ending is not None and ending > boundaries[local+1]+1e-7):
                        raise ValueError("Source element outside selected measure grid")
                    result.append(MatrixSourceElement(
                        f"xml-p{pi}-m{mi}-e{ordinal}", pi, first_bar+local,
                        ordinal, kind, absolute, ending, voice_id,
                        ET.tostring(element, encoding="unicode")))
    return tuple(result)
