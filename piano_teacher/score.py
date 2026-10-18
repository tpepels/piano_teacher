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
from .reading_spacing import space_for_reading, space_for_continuous_reading

from .music import Note, Piece, _bar_boundaries, _phrases, load_midi


def _music21():
    try:
        from music21 import converter, chord, note, stream, tempo, meter, clef, key
    except ImportError as exc:
        raise RuntimeError("Sheet music requires music21: pip install -e '.[godot]'") from exc
    return converter, chord, note, stream, tempo, meter, clef, key


def import_piece(path: str | Path) -> tuple[Piece, object]:
    """Return matching scored note sequence and score for engraving.

    MIDI performance events come from Mido and are engraved later from the
    canonical Piece. MusicXML events and original notation come from music21.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    if path.suffix.lower() not in {".mid", ".midi", ".musicxml", ".xml", ".mxl"}:
        raise ValueError("Supported files: .mid, .midi, .musicxml, .xml, .mxl")
    # All MIDI lessons are engraved from the canonical imported Piece via
    # build_lesson_score, not from music21's loose MIDI transcription. Parsing
    # the raw MIDI a second time used to reject perfectly usable performances
    # with stray note-offs, grace placeholders or odd meter metadata.
    if path.suffix.lower() in {".mid", ".midi"}:
        return load_midi(path), None
    converter, chord, note, stream, tempo, meter, clef, key = _music21()
    from .xml_import import load_musicxml
    piece = load_musicxml(path, bpm=120)
    try:
        notation = converter.parse(str(path))
    except Exception as exc:
        raise ValueError(f"Cannot convert the source notation: {exc}") from exc
    if not isinstance(notation, stream.Score):
        wrapped = stream.Score()
        wrapped.insert(0, notation)
        notation = wrapped
    first_tempo = next(iter(notation.recurse().getElementsByClass(tempo.MetronomeMark)), None)
    bpm = first_tempo.getQuarterBPM() if first_tempo else 120
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("MusicXML tempo needs a positive numeric quarter-note BPM")
    return replace(piece, bpm=round(bpm)), notation


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
                  *, total_beats: float, bpm: float | None = None,
                  continuous: bool = False) -> EngravedScore:
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
        return _engrave_xml(notation.musicxml, hand, total_beats, bpm=bpm,
                            note_bindings=notation.note_bindings, staff_clefs=notation.staff_clefs,
                            continuous=continuous)
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
    return _engrave_xml(xml, hand, total_beats, bpm=bpm, continuous=continuous)


def _can_remove_repeated_system_headers(xml: str, note_bindings: dict | None) -> bool:
    """Only flatten generated piano parts when all subsequent headers are repeats.

    Verovio reprints clefs/key/meter at each system start. In the scrolling
    strip that is a large, unscored gap between adjacent beats. A generated
    lesson with unchanged notation context can omit those *repeat* headers
    at the system joins while retaining the original first clefs, all notes,
    accidental ink, barlines, ties and source IDs. Never do this to imported
    notation or a lesson containing mid-passage notation changes.
    """
    if note_bindings is None:
        return False
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    parts = root.findall("part")
    if [part.get("id") for part in parts] != ["RH", "LH"]:
        return False
    for part in parts:
        measures = part.findall("measure")
        if not measures:
            return False
        for measure in measures[1:]:
            for attrs in measure.findall("attributes"):
                if any(attrs.find(name) is not None for name in (
                        "clef", "key", "time", "transpose", "staff-details")):
                    return False
            # Repeats, segnos and written navigation marks must never be lost
            # from the first measure of a fresh printed system.
            for tag in ("direction", "harmony", "barline"):
                if measure.find(tag) is not None:
                    return False
    return True


def _engrave_xml(xml: str, hand: str, total_beats: float,
                 *, bpm: float | None = None, note_bindings: dict | None = None,
                 staff_clefs: dict | None = None,
                 continuous: bool = False) -> EngravedScore:
    import verovio
    if note_bindings is not None:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        identities = []
        for part in root.findall('part'):
            for note in part.findall('.//note'):
                if note.find('pitch') is None:
                    continue
                identifier = note.get('id')
                binding = note_bindings.get(identifier)
                if binding is None or binding['hand'] != {'RH':'right','LH':'left'}.get(part.get('id')):
                    raise ValueError('Source-note identity/hand mapping does not match emitted notation')
                identities.append(identifier)
        if len(set(identities)) != len(identities) or set(identities) != set(note_bindings):
            raise ValueError('Source-note identity mapping is missing or duplicated')
    toolkit = _create_verovio_toolkit(verovio)
    # Use one common layout for the SVGs and timing map. Timemap qstamps are
    # quarter-note units and remain correct when the practice tempo changes.
    options = {"inputFrom": "xml", "scale": 48,
               "pageWidth": 2200, "pageHeight": 1350,
               "adjustPageHeight": True, "breaks": "auto",
               "svgViewBox": True, "smuflTextFont": "embedded",
               "svgBoundingBoxes": True, "svgContentBoundingBoxes": True}
    if bpm is not None:
        xml, spacing = (space_for_continuous_reading(xml, bpm)
                        if continuous else space_for_reading(xml, bpm))
        options.update(spacing)
    if not toolkit.setOptions(options):
        raise RuntimeError("Verovio rejected its engraving options")
    if not toolkit.loadData(xml):
        raise ValueError("Verovio could not engrave this passage")
    pages = _svg_pages(toolkit)
    if continuous:
        # A continuous exercise must consist of precisely one newly engraved
        # staff system. Never silently show a multi-system raster collage.
        # If Verovio cannot satisfy this (complex imports/format changes),
        # use the proven standard renderer for this specific exercise.
        systems = sum(len(parse_svg_geometry(page).staff_systems) for page in pages)
        if len(pages) != 1 or systems != 1:
            return _engrave_xml(xml, hand, total_beats, bpm=bpm,
                note_bindings=note_bindings, staff_clefs=staff_clefs,
                continuous=False)
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
    layout = layout_from_pages(list(pages), events, total_beats, pitches=pitches,
                               note_bindings=note_bindings)
    layout["strip_trim_repeated_headers"] = (False if continuous else
        _can_remove_repeated_system_headers(xml, note_bindings))
    layout["continuous_score"] = continuous
    # Keeping a genuine clef/key/meter change must not disable the temporal
    # layout. Header safety and equal musical beat spacing are independent.
    layout["strip_time_proportional"] = (
        not continuous and (bpm is not None or layout["strip_trim_repeated_headers"]))
    if staff_clefs is not None:
        layout['staff_clefs'] = staff_clefs
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
