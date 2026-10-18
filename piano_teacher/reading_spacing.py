"""Give slow practice more horizontal time while retaining native engraving."""
from __future__ import annotations

from fractions import Fraction
import math
from xml.etree import ElementTree as ET


# Horizontal density of freshly engraved exercise scores. Independent of BPM.
# Larger values spread the notes farther apart. Start around 0.03; tune
# this one value if the app needs denser or more open notation.
NOTE_SPACING = 0.03

# Preserve a fixed musical-time axis under the stationary playhead.
# A value of 1.0 makes rhythmic duration proportional to engraved distance.
# Lower values would make isolated notes look more equally spaced, but they
# would also force the scrolling score to accelerate/decelerate between notes
# to hit the correct beats. That reintroduces the tempo wobble.
RHYTHM_SPACING = 1.0


def _measure_lengths(root: ET.Element) -> list[float]:
    """Read actual voice durations, including pickups, backups and chords."""
    lengths: list[float] = []
    for part in root.findall("part"):
        divisions = 1
        meter = Fraction(4)
        for index, measure in enumerate(part.findall("measure")):
            position = Fraction(0)
            end = Fraction(0)
            previous_start = Fraction(0)
            for item in measure:
                if item.tag == "attributes":
                    divisions = int(item.findtext("divisions", str(divisions)))
                    time = item.find("time")
                    if time is not None:
                        meter = Fraction(int(time.findtext("beats", "4")) * 4,
                                         int(time.findtext("beat-type", "4")))
                    continue
                duration = Fraction(int(item.findtext("duration", "0")), divisions)
                if item.tag == "backup":
                    position -= duration
                elif item.tag == "forward":
                    position += duration
                    end = max(end, position)
                elif item.tag == "note":
                    if item.find("chord") is None:
                        previous_start = position
                        position += duration
                    end = max(end, previous_start + duration)
            length = float(end or meter)
            if index == len(lengths):
                lengths.append(length)
            else:
                lengths[index] = max(lengths[index], length)
    return lengths


def space_for_reading(xml: str, bpm: float) -> tuple[str, dict]:
    """Encode bounded systems with the same quarter-beat distance everywhere.

    Verovio's automatic castoff estimates justification before layout, even
    when final justification is disabled. Explicit breaks avoid that second
    source of spacing changes. The native engraver still draws every glyph,
    stem, beam and tie at its ordinary size.
    """
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("Practice tempo must be a positive, finite BPM")
    root = ET.fromstring(xml)
    lengths = _measure_lengths(root)
    if not lengths:
        raise ValueError("Practice score contains no measures")
    linear = min(1.0, 4.0 / bpm)
    # At nonlinear=1, Verovio uses 2560 page units per quarter times the
    # linear factor. Reserve opening clefs/meter plus each bar's fixed margin.
    # The renderer measures collision clearance before finalizing page width.
    widths = [2560 * linear * length + 64 for length in lengths]
    page_width = max(2200, math.ceil(500 + max(widths)))
    budget = page_width - 500
    breaks: dict[int, str] = {}
    used = 0.0
    system = 0
    for index, width in enumerate(widths):
        if used and used + width > budget:
            system += 1
            breaks[index] = "new-page" if system % 2 == 0 else "new-system"
            used = 0.0
        used += width
    for part in root.findall("part"):
        for index, measure in enumerate(part.findall("measure")):
            for instruction in measure.findall("print"):
                instruction.attrib.pop("new-system", None)
                instruction.attrib.pop("new-page", None)
            if index in breaks:
                instruction = measure.find("print")
                if instruction is None:
                    instruction = ET.Element("print")
                    measure.insert(0, instruction)
                instruction.set(breaks[index], "yes")
    return ET.tostring(root, encoding="unicode"), {
        "spacingLinear": linear,
        "spacingNonLinear": 1.0,
        "noJustification": True,
        "breaks": "encoded",
        "pageWidth": page_width,
    }


def space_for_continuous_reading(xml: str, bpm: float) -> tuple[str, dict]:
    """Engrave one practice exercise as ONE continuous Verovio system.

    Every note, rest, barline, accidental and staff is laid out afresh by
    Verovio from the exercise's MusicXML. No printed systems are later
    stretched, spliced, or pasted together by Godot. Long works continue to
    use the ordinary multi-system renderer instead.
    """
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("Practice tempo must be a positive, finite BPM")
    root = ET.fromstring(xml)
    lengths = _measure_lengths(root)
    if not lengths:
        raise ValueError("Practice score contains no measures")
    # The score's horizontal density is independent of practice tempo.
    # BPM controls the transport clock; changing tempo must not re-space
    # half/whole/quarter-note glyphs or move upcoming notes off-screen.
    # Keep NOTE_SPACING small; Verovio's collision detection provides the
    # additional space needed around dense chords and accidentals.
    linear = NOTE_SPACING
    # Keep the native note glyph sizes: reserve enough horizontal room for
    # every quarter beat, clefs/meters and per-measure barline clearance.
    # Unlike the previous reading_spacing mode, no internal page/system
    # cast-off is inserted at ANY measure.
    page_width = max(2200, math.ceil(
        1200 + sum(2560.0 * linear * length + 100 for length in lengths)))
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            for instruction in list(measure.findall("print")):
                instruction.attrib.pop("new-system", None)
                instruction.attrib.pop("new-page", None)
                if not instruction.attrib and len(instruction) == 0:
                    measure.remove(instruction)
    return ET.tostring(root, encoding="unicode"), {
        "spacingLinear": linear,
        "spacingNonLinear": RHYTHM_SPACING,
        "noJustification": True,
        "breaks": "none",
        "pageWidth": page_width,
    }
