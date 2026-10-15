"""MusicXML/MIDI to a common performance model and engraved sheet music."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import math
from pathlib import Path
from dataclasses import dataclass

from .score_geometry import layout_from_pages, parse_svg_geometry
from .lesson_score import LessonScore
from .reading_spacing import space_for_reading

from .music import Note, Piece, _bar_boundaries, _phrases, load_midi


def _music21():
    try:
        from music21 import converter, chord, note, stream, tempo, meter, clef, key
    except ImportError as exc:
        raise RuntimeError("Sheet music requires music21: pip install -e '.[godot]'") from exc
    return converter, chord, note, stream, tempo, meter, clef, key


def import_piece(path: str | Path) -> tuple[Piece, object]:
    """Return matching scored note sequence and score for engraving.

    MIDI performance events come from Mido; music21 is used for notation.
    MusicXML events are read from the notation directly.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    if path.suffix.lower() not in {".mid", ".midi", ".musicxml", ".xml", ".mxl"}:
        raise ValueError("Supported files: .mid, .midi, .musicxml, .xml, .mxl")
    converter, chord, note, stream, tempo, meter, clef, key = _music21()
    notation = converter.parse(str(path))
    if not isinstance(notation, stream.Score):
        wrapped = stream.Score()
        wrapped.insert(0, notation)
        notation = wrapped
    if path.suffix.lower() in {".mid", ".midi"}:
        piece = load_midi(path)
        return piece, notation
    parts = list(notation.parts)
    if not parts:
        parts = [notation]
    ranking = []
    for part in parts:
        pitches = [p.midi for item in part.flatten().notes for p in (item.pitches if isinstance(item, chord.Chord) else [item.pitch])]
        ranking.append(sum(pitches) / len(pitches) if pitches else 60)
    low_part = min(range(len(parts)), key=lambda i: ranking[i]) if len(parts) > 1 else -1
    events: list[Note] = []
    tied: dict[tuple[int, int], int] = {}
    for index, part in enumerate(parts):
        hand = "left" if index == low_part else "right"
        for item in part.recurse().notes:
            start = float(item.getOffsetInHierarchy(notation))
            length = float(item.duration.quarterLength)
            members = item.notes if isinstance(item, chord.Chord) else [item]
            for member in members:
                pitch = member.pitch.midi
                identifier = (index, pitch)
                tie_type = member.tie.type if member.tie is not None else None
                if tie_type in ("continue", "stop") and identifier in tied:
                    previous = tied[identifier]
                    events[previous] = replace(events[previous], end=start + length)
                else:
                    events.append(Note(start, start + length, pitch, index, 0, hand))
                if tie_type in ("start", "continue"):
                    tied[identifier] = len(events) - 1 if tie_type == "start" or identifier not in tied else tied[identifier]
                else:
                    tied.pop(identifier, None)
    if not events:
        raise ValueError("The score has no playable notes")
    signatures = [(float(t.getOffsetInHierarchy(notation)), t.numerator, t.denominator)
                  for t in notation.recurse().getElementsByClass(meter.TimeSignature)]
    first_tempo = next(iter(notation.recurse().getElementsByClass(tempo.MetronomeMark)), None)
    bpm = round(first_tempo.getQuarterBPM()) if first_tempo else 120
    events.sort(key=lambda e: (e.start, e.pitch, e.track))
    boundaries = _bar_boundaries(max(n.end for n in events), signatures)
    phrases = _phrases(events, boundaries, 2)
    return Piece(path.stem, bpm, tuple(events), phrases, bar_boundaries=tuple(boundaries), time_signatures=tuple(sorted(set(signatures)))), notation


def _pitches_from_verovio(toolkit, events: list[dict]) -> dict[str, int]:
    """Read sounding MIDI pitches of Verovio note IDs, not displayed accidental glyphs.

    getMIDIValuesForElement resolves key signatures, chromatic spelling and
    accidentals, unlike manually interpreting an SVG notehead's height.
    """
    note_ids = {str(identifier) for event in events for identifier in event.get("on", [])}
    try:
        toolkit.renderToMIDI()  # Required before getMIDIValuesForElement
    except Exception:
        return {}
    result = {}
    for identifier in note_ids:
        try:
            data = _verovio_object(toolkit.getMIDIValuesForElement(identifier), "MIDI pitch")
            pitch = data.get("pitch") if isinstance(data, dict) else None
            if isinstance(pitch, (int, float)) and 0 <= pitch <= 127:
                result[identifier] = int(pitch)
        except (TypeError, ValueError, AttributeError, KeyError):
            continue
    return result


def _verovio_resources(verovio_module) -> Path:
    """Resolve fonts next to the installed Python module, not a build-time path.

    The Verovio Python wheel includes Bravura and Leipzig in verovio/data.
    """
    module_file = getattr(verovio_module, "__file__", None)
    if not module_file:
        raise RuntimeError("Verovio installation has no module location; cannot find its music fonts")
    path = Path(module_file).resolve().parent / "data"
    missing = [name for name in ("Bravura.xml", "Leipzig.xml") if not (path / name).is_file()]
    if missing:
        raise RuntimeError(
            f"Verovio music fonts are missing from {path}: {', '.join(missing)}. "
            "Reinstall the complete Python wheel with "
            "python -m pip install --force-reinstall --no-cache-dir 'verovio>=5,<6'"
        )
    return path


def _create_verovio_toolkit(verovio_module):
    """Load the bundled fonts explicitly before importing or engraving music."""
    resources = _verovio_resources(verovio_module)
    # Avoid the default font path baked into some wheels at build time.
    toolkit = verovio_module.toolkit(False)
    if not toolkit.setResourcePath(str(resources)):
        raise RuntimeError(f"Verovio could not load its Bravura/Leipzig fonts from {resources}")
    return toolkit


def _verovio_object(value, description: str):
    """Accept native Python results from the 5.x binding or older JSON strings."""
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Verovio returned invalid {description}") from exc
    raise ValueError(f"Verovio returned unexpected {description} type: {type(value).__name__}")


def _fade_inactive_staff(svg: str, hand: str) -> str:
    """De-emphasize every inactive staff element: beams, ledger lines and notes.

    Verovio emits both staves separately in every measure, ordered from upper
    to lower. We preserve IDs and geometry intact and leave larger ensembles
    unchanged when the inactive piano hand cannot be inferred safely.
    """
    if hand not in ("left", "right"):
        return svg
    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg)
    changed = False
    for system in root.iter():
        if "system" not in system.get("class", "").split():
            continue
        measures = [item for item in system.iter()
                    if "measure" in item.get("class", "").split()]
        for measure in measures or [system]:
            staves = [item for item in measure
                      if "staff" in item.get("class", "").split()]
            if len(staves) != 2:
                continue
            inactive = staves[1] if hand == "right" else staves[0]
            inactive.set("opacity", "0.48")
            changed = True
    if not changed:
        return svg
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ET.tostring(root, encoding="unicode")


@dataclass(frozen=True)
class EngravedScore:
    pages: tuple[str, ...]
    layout: dict


def render_layout(notation: object, first: int, last: int, hand: str = "both",
                  *, total_beats: float, bpm: float | None = None) -> EngravedScore:
    """Render *all* score pages and bind their noteheads to Verovio qstamps.

    The returned layout has exact engraved onset anchors, page/system IDs, and
    SVG viewBox dimensions. A mismatched engraving raises an explicit error;
    there is deliberately no fake percentage-based cursor fallback.
    """
    try:
        import verovio
        from music21 import stream, clef, key, tempo, metadata
        from music21.musicxml.m21ToXml import GeneralObjectExporter
    except ImportError as exc:
        raise RuntimeError("Engraving requires verovio and music21: pip install -e '.[godot]'") from exc
    if isinstance(notation, LessonScore):
        return _engrave_xml(notation.musicxml, hand, total_beats, bpm=bpm)
    sc = copy.deepcopy(notation)
    if not list(sc.recurse().getElementsByClass(stream.Measure)):
        sc.makeMeasures(inPlace=True)
    out = stream.Score()
    # Do not insert a generic Music21 Fragment title above every short lesson.
    out.metadata = metadata.Metadata(title=" ")
    parts = list(sc.parts) or [sc]
    for index, part in enumerate(parts):
        p = stream.Part()
        p.id = part.id
        measures = list(part.getElementsByClass(stream.Measure))
        selected = [m for m in measures if first <= int(m.number) <= last]
        if not selected:
            continue
        for i, measure in enumerate(selected):
            copied = copy.deepcopy(measure)
            if i == 0:
                for element_type in (clef.Clef, key.KeySignature):
                    if not list(copied.getElementsByClass(element_type)):
                        context = measure.getContextByClass(element_type)
                        if context is not None:
                            copied.insert(0, copy.deepcopy(context))
            # MIDI imports may have many original tempo changes. The practice
            # lesson uses one selected BPM, shown in the header instead.
            for metronome in list(copied.recurse().getElementsByClass(tempo.MetronomeMark)):
                if metronome.activeSite is not None:
                    metronome.activeSite.remove(metronome)
            if hand != "both" and len(parts) >= 2:
                # For ordinary two-part piano MusicXML: top right, bottom left.
                inactive = (hand == "right" and index == len(parts) - 1) or (hand == "left" and index == 0)
                if inactive:
                    for item in copied.recurse().notes:
                        item.style.color = "#BFC5C1"
            p.append(copied)
        out.append(p)
    if not list(out.parts):
        raise ValueError(f"No notation found for measures {first}-{last}")
    xml = GeneralObjectExporter(out).parse().decode("utf-8")
    return _engrave_xml(xml, hand, total_beats, bpm=bpm)


def _engrave_xml(xml: str, hand: str, total_beats: float,
                 *, bpm: float | None = None) -> EngravedScore:
    import verovio
    toolkit = _create_verovio_toolkit(verovio)
    # Use one common layout for the SVGs and timing map. Timemap qstamps are
    # quarter-note units and remain correct when the practice tempo changes.
    options = {"inputFrom": "xml", "scale": 48,
               "pageWidth": 2200, "pageHeight": 1350,
               "adjustPageHeight": True, "breaks": "auto",
               "svgViewBox": True, "smuflTextFont": "embedded",
               "svgBoundingBoxes": True, "svgContentBoundingBoxes": True}
    if bpm is not None:
        xml, spacing = space_for_reading(xml, bpm)
        options.update(spacing)
    if not toolkit.setOptions(options):
        raise RuntimeError("Verovio rejected its engraving options")
    if not toolkit.loadData(xml):
        raise ValueError("Verovio could not engrave this passage")
    pages = _svg_pages(toolkit)
    gaps = []
    for page in pages:
        for system in parse_svg_geometry(page).staff_systems.values():
            lines = system["staff_lines"]
            if len(lines) == 10 and lines[1] > lines[0]:
                gaps.append((lines[5] - lines[0]) / (lines[1] - lines[0]))
    if gaps and max(gaps) - min(gaps) > .0001:
        # Automatic collision avoidance can move only the bass staff in some
        # systems. A scrolling strip requires both five-line staves to stay
        # level. Use the space actually required by this passage, rather than
        # imposing a large fixed gap or stretching its raster vertically.
        # One MEI unit is half a staff space; the upper staff itself is four.
        spacing = math.ceil(2 * (max(gaps) - 4) - .0001)
        if not toolkit.setOptions({"spacingStaff": spacing, "spacingBraceGroup": spacing}):
            raise ValueError("This passage requires unsupported spacing between piano staves")
        toolkit.redoLayout()
        pages = _svg_pages(toolkit)
    if bpm is not None:
        # Accidentals, flags and dense voices can need more room than the
        # duration budget used to choose breaks. Measure native staff ends
        # after collision avoidance, then enlarge the viewport once. Encoded
        # breaks keep note spacing and glyph sizes unchanged by this relayout.
        right = max((system["right"] for page in pages
                     for system in parse_svg_geometry(page).staff_systems.values()),
                    default=1.0)
        if right > 1.0:
            width = math.ceil(options["pageWidth"] * right + 100)
            if not toolkit.setOptions({"pageWidth": width}):
                raise ValueError("This passage requires an unsupported engraving width")
            toolkit.redoLayout()
            pages = _svg_pages(toolkit)
    pages = tuple(_fade_inactive_staff(page, hand) for page in pages)
    try:
        events = _verovio_object(toolkit.renderToTimemap(
            {"includeRests": True, "includeMeasures": True}), "note timing map")
    except (ValueError, TypeError) as exc:
        raise ValueError("Verovio produced an invalid note timing map") from exc
    if not isinstance(events, list):
        raise ValueError("Verovio produced no note timing map")
    pitches = _pitches_from_verovio(toolkit, events)
    layout = layout_from_pages(list(pages), events, total_beats, pitches=pitches)
    # Geometry consumes the native event bounds; diagnostic rectangles never
    # enter the returned score or its raster/GPU textures.
    import xml.etree.ElementTree as ET
    cleaned = []
    for page in pages:
        root = ET.fromstring(page)
        for parent in root.iter():
            for child in list(parent):
                if set(child.get("class", "").split()) & {"bounding-box", "content-bounding-box"}:
                    parent.remove(child)
        cleaned.append(ET.tostring(root, encoding="unicode"))
    return EngravedScore(tuple(cleaned), layout)


def _svg_pages(toolkit) -> tuple[str, ...]:
    count = toolkit.getPageCount()
    if count < 1 or count > 256:
        raise ValueError(f"Unexpected engraving page count: {count}")
    pages = tuple(toolkit.renderToSVG(i) for i in range(1, count + 1))
    if any("<svg" not in page for page in pages):
        raise ValueError("Verovio returned an invalid SVG page")
    return pages


def render_measures(notation: object, first: int, last: int, hand: str = "both") -> str:
    """Legacy single-page SVG API. Prefer render_layout for synchronized UI."""
    # When no exact phrase duration is available, only SVG rendering is needed;
    # use a duration larger than any excerpt (the caller ignores anchors).
    return render_layout(notation, first, last, hand, total_beats=1_000_000).pages[0]
