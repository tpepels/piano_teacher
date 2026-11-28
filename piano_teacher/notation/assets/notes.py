"""Reusable whole-note engraving *components*, rendered by Verovio once.

These are NOT custom notehead+stem drawings. A real Verovio toolkit engraves
each duration/stem-direction example. We isolate its complete note SVG group
(notehead, stem and any flag), rasterize the genuine artwork, and store a
transparent PNG + pitch-centred staff-space bounds. Godot only positions and
tints those fixed templates. Chords and groups with shared beams are variable-
geometry compounds and intentionally keep the existing native construction.
"""
from __future__ import annotations

import base64
from io import BytesIO
import math
from functools import lru_cache
import xml.etree.ElementTree as ET

from PIL import Image

KINDS = ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th")
BEATS = {"whole": 4, "half": 2, "quarter": 1, "eighth": 0.5,
         "16th": 0.25, "32nd": 0.125, "64th": 0.0625, "128th": 0.03125}
TEMPLATE_VERSION = 6
XML_DIVISIONS = 10080


def keys() -> tuple[str, ...]:
    return ("whole",) + tuple(
        f"{kind}_{direction}" for kind in KINDS[1:]
        for direction in ("up", "down"))


GRACE_KEYS = tuple(f"grace_slash_{kind}_{direction}" for kind in ("eighth", "16th")
                   for direction in ("up", "down"))


def _one_note_xml(kind: str, direction: str) -> str:
    slashed = kind.startswith("grace_slash_")
    kind = kind.removeprefix("grace_slash_")
    duration = round(BEATS[kind] * XML_DIVISIONS)
    timing = "" if slashed else f"<duration>{duration}</duration>"
    grace = '<grace slash="yes"/>' if slashed else ""
    # Middle-line B4 avoids incidental ledger rules, key changes, and
    # accidentals. Direction is explicit so Verovio decides the stem shape.
    stem = f"<stem>{direction}</stem>" if kind != "whole" else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<score-partwise version="4.0">
 <work><work-title> </work-title></work>
 <movement-title> </movement-title>
 <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
 <part id="P1"><measure number="1">
  <attributes><divisions>{XML_DIVISIONS}</divisions><key><fifths>0</fifths></key>
    <time><beats>4</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
  <note id="template">{grace}<pitch><step>B</step><octave>4</octave></pitch>
    {timing}<type>{kind}</type>{stem}</note>
 </measure></part>
</score-partwise>"""


def _only_note_svg(svg: str) -> str:
    root = ET.fromstring(svg)
    note = next((e for e in root.iter()
                 if "note" in e.get("class", "").split()), None)
    if note is None:
        raise ValueError("Verovio did not engrave a note group")

    def prune(element: ET.Element) -> bool:
        if element is note:
            for parent in element.iter():
                for child in list(parent):
                    if set(child.get("class", "").split()) & {
                            "bounding-box", "content-bounding-box"}:
                        parent.remove(child)
            return True
        if element.tag.rsplit("}", 1)[-1] in {"defs", "style"}:
            return True
        retained = False
        for child in list(element):
            if prune(child):
                retained = True
            else:
                element.remove(child)
        return retained

    if not prune(root):
        raise ValueError("Verovio note is outside the rendered SVG hierarchy")
    return ET.tostring(root, encoding="unicode")


def _only_stem_svg(note_svg: str) -> str:
    """Retain only Verovio's original note stem, not a drawn approximation."""
    root = ET.fromstring(note_svg)
    def prune(node: ET.Element) -> bool:
        if "stem" in node.get("class", "").split():
            for parent in node.iter():
                for child in list(parent):
                    if "flag" in child.get("class", "").split():
                        parent.remove(child)
            return True
        if node.tag.rsplit("}", 1)[-1] in {"defs", "style"}:
            return True
        found = False
        for child in list(node):
            if prune(child):
                found = True
            else:
                node.remove(child)
        return found
    if not prune(root):
        raise ValueError("Verovio did not export an individual stem group")
    return ET.tostring(root, encoding="unicode")


def _render_template(toolkit, kind: str, direction: str,
                     head_center_units: float) -> dict:
    from .vector_art import svg_alpha
    from ...source_svg import parse_svg_geometry

    if not toolkit.loadData(_one_note_xml(kind, direction)):
        raise RuntimeError(f"Verovio rejected note template: {kind}/{direction}")
    svg = toolkit.renderToSVG(1)
    geom = parse_svg_geometry(svg)
    if len(geom.elements) != 1:
        raise RuntimeError("A single-note Verovio template must have one note ID")
    note_x, note_y, system_id = next(iter(geom.elements.values()))
    staff = geom.staff_systems[system_id]
    rails = staff["staff_lines"]
    if len(rails) < 5 or rails[1] <= rails[0]:
        raise RuntimeError("Verovio did not return five genuine staff rules")
    filtered = _only_note_svg(svg)
    # A constant resolution independent of the application window: the
    # original vector is rasterized once, not on every Godot frame.
    alpha = svg_alpha(filtered, 1800)
    staff_space = (rails[1] - rails[0]) * alpha.height
    if not (4.0 <= staff_space <= 250.0):
        raise RuntimeError("Verovio's note template has invalid staff scale")
    bbox = alpha.getbbox()
    if bbox is None:
        raise RuntimeError(f"Empty Verovio note template: {kind}/{direction}")
    # The head is positioned by its VISUAL centre in Godot, not the
    # non-centred font-origin used by the original Verovio SVG <use>.
    head_center_x = note_x * alpha.width + (
        head_center_units / 250.0) * staff_space
    head_origin_y = note_y * alpha.height
    left, top, right, bottom = bbox
    glyph = alpha.crop(bbox)
    # Use a white tintable RGBA mask; retain exact engraved alpha, not the
    # font's (possibly black) source ink color.
    opaque_white = Image.new("RGBA", glyph.size, (255, 255, 255, 255))
    opaque_white.putalpha(glyph)
    file = BytesIO()
    opaque_white.save(file, format="PNG", optimize=True)
    bounds = [
        (left - head_center_x) * 250.0 / staff_space,
        (top - head_origin_y) * 250.0 / staff_space,
        (right - left) * 250.0 / staff_space,
        (bottom - top) * 250.0 / staff_space,
    ]
    if not all(math.isfinite(v) for v in bounds):
        raise RuntimeError("Verovio note sprite has invalid anchor geometry")
    if bounds[2] > 1200 or bounds[3] > 2200:
        raise RuntimeError("Stray staff or clef ink entered Verovio note sprite")
    result = {
        "source": "verovio-engraved-note",
        "bounds": bounds, "units_per_space": 250,
        "png_base64": base64.b64encode(file.getvalue()).decode("ascii"),
    }
    if kind != "whole":
        stem_svg = _only_stem_svg(filtered)
        stem_image = svg_alpha(stem_svg, 1800)
        ink = stem_image.getbbox()
        if ink is None:
            raise RuntimeError("Verovio exported an empty individual stem")
        sx0, sy0, sx1, sy1 = ink
        cropped = stem_image.crop(ink)
        white_stem = Image.new("RGBA",cropped.size,(255,255,255,255))
        white_stem.putalpha(cropped)
        stem_bytes = BytesIO()
        white_stem.save(stem_bytes, format="PNG", optimize=True)
        result["stem_only"] = {
            "source": "verovio-engraved-note-stem",
            "units_per_space": 250,
            "bounds": [(sx0-head_center_x)*250.0/staff_space,
                       (sy0-head_origin_y)*250.0/staff_space,
                       (sx1-sx0)*250.0/staff_space,
                       (sy1-sy0)*250.0/staff_space],
            "png_base64": base64.b64encode(stem_bytes.getvalue()).decode("ascii"),
        }
    return result


def _validate(items: dict, names: tuple[str, ...]) -> bool:
    if not isinstance(items, dict) or set(items) != set(names):
        return False
    for name, item in items.items():
        if (not isinstance(item, dict)
                or item.get("source") != "verovio-engraved-note"
                or item.get("units_per_space") != 250
                or not isinstance(item.get("png_base64"), str)
                or len(item["png_base64"]) < 80
                or len(item.get("bounds", [])) != 4):
            return False
        if name != "whole":
            stem = item.get("stem_only")
            if (not isinstance(stem, dict)
                    or stem.get("source") != "verovio-engraved-note-stem"
                    or stem.get("units_per_space") != 250
                    or len(stem.get("bounds", [])) != 4
                    or not isinstance(stem.get("png_base64"), str)
                    or len(stem["png_base64"]) < 80):
                return False
    return True


@lru_cache(maxsize=2)
def _generate(font: str, names: tuple[str, ...]) -> dict:
    import verovio
    from .runtime import create_verovio_toolkit
    from .glyphs import native_glyphs

    atlas = native_glyphs()
    toolkit = create_verovio_toolkit(verovio)
    if not toolkit.setOptions({
        "inputFrom": "xml", "scale": 48, "pageWidth": 900,
        "pageHeight": 650, "adjustPageHeight": True,
        "breaks": "auto", "svgViewBox": True,
        "svgBoundingBoxes": True, "svgContentBoundingBoxes": True,
    }):
        raise RuntimeError("Verovio rejected note-template engraving options")
    result = {}
    for name in names:
        kind, direction = (("whole", "up") if name == "whole"
                           else name.rsplit("_", 1))
        head = atlas["head_" + (kind if kind in {"whole", "half"} else "black")]["bounds"]
        head_center = head[0] + head[2] * 0.5
        if kind.startswith("grace_slash_"):
            head_center *= toolkit.getOptions()["graceFactor"]
        result[name] = _render_template(toolkit, kind, direction, head_center)
    return result


def note_templates(cache=None, *, slashed_graces=False) -> dict:
    regular = _template_set(cache, keys())
    if slashed_graces:
        return {**regular, **_template_set(cache, GRACE_KEYS)}
    return regular


def _template_set(cache, names) -> dict:
    """Disk-versioned and per-process cached isolated authentic notes."""
    import verovio
    from .glyphs import native_glyphs
    font = native_glyphs()["head_black"]["font"]
    version = getattr(verovio, "__version__", "unknown")
    key = (cache.key("verovio-note-templates", TEMPLATE_VERSION, font, version, names)
           if cache is not None else None)
    if key is not None:
        stored = cache.read_json("verovio-notes", key)
        if _validate(stored, names):
            return stored
    templates = _generate(font, names)
    if not _validate(templates, names):
        raise RuntimeError("Generated Verovio note atlas is incomplete")
    if key is not None:
        cache.write_json("verovio-notes", key, templates)
    return templates
