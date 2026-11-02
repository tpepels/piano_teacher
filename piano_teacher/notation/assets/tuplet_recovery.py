"""Recover source-owned tuplets that Verovio did not expose in a full page.

Only the *exact* selected MusicXML notes are re-engraved. This isolates a
tupleting voice from unrelated simultaneous polyphony without changing note
IDs, written durations or the selected lesson. The isolated Verovio SVG is
subjected to the ordinary authenticated fragment extraction and raster checks.
No numbers, brackets, or coordinates are drawn or inferred in this module.
"""
from __future__ import annotations

from copy import deepcopy
from math import ceil
import xml.etree.ElementTree as ET


def _source_notes(notation_xml: str) -> tuple[dict[str, ET.Element], int]:
    root = ET.fromstring(notation_xml)
    result = {}
    divisions = None
    for measure in root.findall("part/measure"):
        attributes = measure.find("attributes")
        if attributes is not None and attributes.find("divisions") is not None:
            value = int(attributes.findtext("divisions", "0"))
            if value <= 0:
                raise ValueError("Invalid original MusicXML divisions")
            if divisions is not None and divisions != value:
                # The isolated single-measure renderer cannot merge
                # independent written divisions without retiming.
                return {}, 0
            divisions = value
        for note in measure.findall("note"):
            identifier = note.get("id")
            if identifier:
                if identifier in result:
                    return {}, 0
                result[identifier] = note
    return result, divisions or 0


def _isolated_score(ids: tuple[str, ...], source: dict[str, ET.Element],
                    divisions: int) -> str | None:
    """Emit only the original attack notes in their original written order."""
    notes = []
    duration = 0
    for identifier in ids:
        original = source.get(identifier)
        if original is None or original.find("chord") is not None:
            return None
        if original.find("pitch") is None and original.find("rest") is None:
            return None
        ticks = original.findtext("duration")
        if ticks is None or not ticks.isdecimal() or int(ticks) <= 0:
            return None
        if original.find("time-modification") is None:
            return None
        copied = deepcopy(original)
        # The isolated score contains a single independent voice; all
        # unrelated expressive connectors would have dangling endpoints.
        for tag in list(copied.findall("tie")):
            copied.remove(tag)
        for tag in list(copied.findall("beam")):
            copied.remove(tag)
        for tag in list(copied.findall("stem")):
            copied.remove(tag)
        for tag in list(copied.findall("voice")):
            copied.remove(tag)
        notation = copied.find("notations")
        if notation is not None:
            for tag in list(notation):
                if tag.tag != "tuplet":
                    notation.remove(tag)
        notes.append(copied)
        duration += int(ticks)
    if not notes or divisions <= 0:
        return None
    # Single wide-free measure: a written 3:2 eighth group occupies one
    # quarter, a quarter-note group two quarters, etc. Use an exact integral
    # meter and omit rests that would introduce new tuplet candidates.
    measure_beats = max(1, ceil(duration / divisions))
    root = ET.Element("score-partwise", version="4.0")
    ET.SubElement(root, "work")
    ET.SubElement(root, "movement-title").text = "Source tuplet"
    parts = ET.SubElement(root, "part-list")
    part_info = ET.SubElement(parts, "score-part", id="P1")
    ET.SubElement(part_info, "part-name").text = "Piano"
    part = ET.SubElement(root, "part", id="P1")
    measure = ET.SubElement(part, "measure", number="1", implicit="yes")
    attributes = ET.SubElement(measure, "attributes")
    ET.SubElement(attributes, "divisions").text = str(divisions)
    meter = ET.SubElement(attributes, "time")
    ET.SubElement(meter, "beats").text = str(measure_beats)
    ET.SubElement(meter, "beat-type").text = "4"
    clef = ET.SubElement(attributes, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"
    measure.extend(notes)
    return ET.tostring(root, encoding="unicode")


def recover_missing_tuplets(notation_xml: str, model: dict,
                            missing: tuple[tuple[str, ...], ...]) -> dict:
    """Return only proved, Verovio-engraved fragments for missing groups."""
    if not notation_xml or not missing:
        return {}
    # Lazy import ensures ordinary cached native scores do not initialize
    # a second Verovio toolkit.
    import verovio
    from .runtime import _create_verovio_toolkit
    from .tuplets import extract_tuplets

    source, divisions = _source_notes(notation_xml)
    if not divisions:
        return {}
    all_events = {str(e["id"]): e for e in model.get("notation_events", [])
                  if e.get("id") and e.get("kind") in {"note", "rest"}}
    toolkit = _create_verovio_toolkit(verovio)
    if not toolkit.setOptions({"inputFrom": "xml", "scale": 48,
                               "pageWidth": 900, "pageHeight": 650,
                               "svgViewBox": True,
                               "svgBoundingBoxes": True,
                               "svgContentBoundingBoxes": True}):
        raise RuntimeError("Verovio rejected isolated source-tuplet options")
    recovered = {}
    for ids in missing:
        if any(identifier not in all_events for identifier in ids):
            continue
        isolated = _isolated_score(ids, source, divisions)
        if isolated is None or not toolkit.loadData(isolated):
            continue
        # Preserve original semantic marks and IDs. Only the beat origin and
        # measure number change for this disposable engraving reference.
        subset = {"notation_events": [
            {**all_events[identifier], "measure": 1}
            for identifier in ids]}
        pages = [toolkit.renderToSVG(1)]
        found = extract_tuplets(pages, subset)
        key = "|".join(ids)
        if key not in found or found[key].get("note_ids") != list(ids):
            continue
        source_mark = next((mark for mark in all_events[ids[0]].get("tuplet_marks", [])
                            if mark.get("type") == "start"), {})
        if (source_mark.get("bracket", "yes") == "yes"
                and not found[key].get("bracket")):
            continue
        item = found[key]
        item["origin"] = "isolated-source-musicxml-verovio"
        recovered[key] = item
    return recovered
