"""Small standalone preparation glyphs from the installed Verovio font.

Keep the exact font outlines and origins used by the exercise engraving, without
shipping a second music font or approximating clefs/rests with text characters.
"""
from functools import lru_cache
import xml.etree.ElementTree as ET


@lru_cache(maxsize=1)
def preparation_symbols() -> dict:
    import verovio
    from .runtime import _create_verovio_toolkit, _verovio_resources

    resources = _verovio_resources(verovio)
    toolkit = _create_verovio_toolkit(verovio)
    font = toolkit.getOptions().get("font", "Leipzig")
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    result = {}
    for name, code in (("treble", "E050"), ("bass", "E062"),
                       ("quarter_rest", "E4E5"), ("eighth_rest", "E4E6")):
        glyph = ET.parse(resources / font / f"{code}.xml").getroot()
        box = metrics.find(f"g[@c='{code}']")
        x, y, width, height = (float(box.get(key)) for key in ("x", "y", "w", "h"))
        # Font metrics use y-up; its SVG paths already include scale(1,-1).
        bounds = [x - 12, -y - height - 12, width + 24, height + 24]
        svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                         viewBox=" ".join(str(v) for v in bounds),
                         width=str(bounds[2]), height=str(bounds[3]), fill="#C4CDC6")
        svg.append(glyph)
        result[name] = {"svg": ET.tostring(svg, encoding="unicode"),
                        "bounds": bounds, "units_per_space": 250}
    return result


# The native Godot lesson renderer uses exactly these Verovio font outlines.
# Every catalogue item comes from the active installed engraving font, never
# from hand-built paths, Unicode fallback glyphs, or a synthesized notehead.
# SVG is an interchange format for ONE glyph: Godot rasterizes it once into an
# ImageTexture, then positions/composites the textures on its own beat grid.
_NATIVE_CODES = {
    "brace": "E000",
    "clef_g": "E050", "clef_f": "E062", "clef_c": "E05C",
    # Original SMuFL clefs with octave numbers attached.
    "clef_g_8vb": "E052", "clef_g_8va": "E053",
    "clef_g_15mb": "E051", "clef_g_15ma": "E054",
    "clef_f_8vb": "E064", "clef_f_8va": "E065",
    "clef_f_15mb": "E063", "clef_f_15ma": "E066",
    "clef_c_8vb": "E05D",
    # Compound variants retain E05C plus original octave-number contours.
    "clef_c_8va": "E05C", "clef_c_15ma": "E05C", "clef_c_15mb": "E05C",
    "head_whole": "E0A2", "head_half": "E0A3", "head_black": "E0A4",
    "augmentation_dot": "E1E7",
    "repeat_dot": "E044",
    "rest_whole": "E4E3", "rest_half": "E4E4",
    "rest_quarter": "E4E5", "rest_eighth": "E4E6",
    "rest_16th": "E4E7", "rest_32nd": "E4E8", "rest_64th": "E4E9",
    "rest_128th": "E4EA",
    "acc_flat": "E260", "acc_natural": "E261", "acc_sharp": "E262",
    "acc_double_sharp": "E263", "acc_double_flat": "E264",
    "flag_up_1": "E240", "flag_down_1": "E241",
    "flag_up_2": "E242", "flag_down_2": "E243",
    "flag_up_3": "E244", "flag_down_3": "E245",
    "flag_up_4": "E246", "flag_down_4": "E247",
    "flag_up_5": "E248", "flag_down_5": "E249",
    **{f"time_{n}": f"{0xE080 + n:04X}" for n in range(10)},
}


def _engraved_clef(font: str, name: str, code: str) -> dict:
    """Extract a complete engine-rendered clef when a font contour is absent.

    The inverse source transform changes only the coordinate system. All
    paths, compound placement and bounds come from the actual engraving.
    """
    import copy
    import verovio
    from .runtime import _create_verovio_toolkit
    from .svg_geometry import _transform, _apply

    if not name.startswith("clef_") or _NATIVE_CODES.get(name) != code:
        raise RuntimeError(f"No authentic Verovio compound available for {name}")
    _, sign, *suffix = name.split("_")
    line = {"g": 2, "f": 4, "c": 3}[sign]
    octave = {"8vb": -1, "8va": 1, "15mb": -2, "15ma": 2}.get(
        suffix[0] if suffix else "", 0)
    xml = f'''<score-partwise version="4.0"><part-list><score-part id="P">
      <part-name>Piano</part-name></score-part></part-list><part id="P">
      <measure number="1"><attributes><divisions>1</divisions>
      <clef><sign>{sign.upper()}</sign><line>{line}</line>
      <clef-octave-change>{octave}</clef-octave-change></clef></attributes>
      <note><pitch><step>B</step><octave>4</octave></pitch><duration>1</duration>
      <type>quarter</type></note></measure></part></score-partwise>'''
    toolkit = _create_verovio_toolkit(verovio)
    if not toolkit.setOptions({"font": font, "svgViewBox": True, "svgBoundingBoxes": True,
                               "svgContentBoundingBoxes": True}):
        raise RuntimeError(f"Verovio cannot engrave clef in {font}")
    if not toolkit.loadData(xml):
        raise RuntimeError(f"Verovio rejected clef template {name}")
    root = ET.fromstring(toolkit.renderToSVG(1))
    clef = next(n for n in root.iter() if n.get("class") == "clef")
    use = next(n for n in clef.iter() if n.tag.rsplit("}", 1)[-1] == "use")
    a, b, c, d, e, f = _transform(use.get("transform", ""))
    if b or c or a <= 0 or d <= 0:
        raise RuntimeError(f"Unsupported Verovio clef anchor {name}")
    inverse = (1/a, 0, 0, 1/d, -e/a, -f/d)
    box_group = next(n for n in clef if "content-bounding-box" in
                     n.get("class", "").split())
    box = next(n for n in box_group if n.tag.rsplit("}", 1)[-1] == "rect")
    x, y, w, h = (float(box.get(k)) for k in ("x", "y", "width", "height"))
    x0, y0 = _apply(inverse, x, y)
    x1, y1 = _apply(inverse, x+w, y+h)
    bounds = [x0-12, y0-12, x1-x0+24, y1-y0+24]
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                     viewBox=" ".join(str(v) for v in bounds),
                     width=str(bounds[2]), height=str(bounds[3]), fill="white")
    for defs in root.iter():
        if defs.tag.rsplit("}", 1)[-1] == "defs":
            svg.append(copy.deepcopy(defs))
    normalized = ET.SubElement(svg, "g", transform="matrix(" +
                               " ".join(str(v) for v in inverse) + ")")
    normalized.append(copy.deepcopy(clef))
    definitions = {n.get("id"): n for defs in root.iter()
                   if defs.tag.rsplit("}", 1)[-1] == "defs"
                   for n in defs if n.get("id")}
    # Godot's SVG rasterizer does not reliably resolve namespace-prefixed
    # xlink references. Inline only the referenced ORIGINAL contours, with
    # their original transforms, so no engraving geometry is re-created.
    for node in list(normalized.iter()):
        if node.tag.rsplit("}", 1)[-1] != "use":
            continue
        href = node.get("{http://www.w3.org/1999/xlink}href", node.get("href", ""))
        definition = definitions.get(href.removeprefix("#"))
        if definition is None:
            raise RuntimeError(f"Missing original Verovio clef contour {href}")
        node.tag = "g"
        node.attrib.pop("{http://www.w3.org/1999/xlink}href", None)
        node.attrib.pop("href", None)
        node.append(copy.deepcopy(definition))
    for parent in list(svg.iter()):
        parent.tag = parent.tag.rsplit("}", 1)[-1]
        for child in list(parent):
            if set(child.get("class", "").split()) & {
                    "bounding-box", "content-bounding-box"}:
                parent.remove(child)
    return {"svg": ET.tostring(svg, encoding="unicode"), "bounds": bounds,
            "units_per_space": 250, "source": "verovio", "font": font,
            "code": code, "extraction": "engraved-clef"}


def _c_octave_components(assets: dict, resources, font: str) -> dict:
    """Place original ottava contours around the original C-clef contour.

    Leipzig's C8vb fuses its numeral into the clef's outer path, so splitting
    that path would corrupt the numeral. Use complete E510/E514 font glyphs;
    measure their height from the original C8vb extension instead.
    """
    import copy

    base = assets["clef_c"]
    base_box = base["bounds"]
    source_box = assets["clef_c_8vb"]["bounds"]
    height = source_box[1]+source_box[3]-base_box[1]-base_box[3]
    center = base_box[0]+base_box[2]/2
    clearance = 12.0  # Original font-asset padding, in engraving units.
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    result = {}
    for suffix, above, code in (("8va", True, "E510"),
                                ("15ma", True, "E514"),
                                ("15mb", False, "E514")):
        metric = metrics.find(f"g[@c='{code}']")
        number = ET.parse(resources / font / f"{code}.xml").getroot()
        x, y, w, h = (float(metric.get(k)) for k in ("x", "y", "w", "h"))
        box = [x, -y-h, w, h]
        scale = height/h
        tx = center-(x+w/2)*scale
        top = base_box[1]+12-clearance-height if above else base_box[1]+base_box[3]-12+clearance
        ty = top-box[1]*scale
        left = min(base_box[0], tx+x*scale-12)
        right = max(base_box[0]+base_box[2], tx+(x+w)*scale+12)
        upper = min(base_box[1], top-12)
        lower = max(base_box[1]+base_box[3], top+height+12)
        bounds = [left, upper, right-left, lower-upper]
        svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
            viewBox=" ".join(map(str, bounds)), width=str(bounds[2]),
            height=str(bounds[3]), fill="white")
        for child in ET.fromstring(base["svg"]):
            svg.append(copy.deepcopy(child))
        numeral = ET.SubElement(svg, "g", transform=f"translate({tx},{ty}) scale({scale})")
        numeral.append(number)
        for node in svg.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        result["clef_c_"+suffix] = {
            "svg": ET.tostring(svg, encoding="unicode"), "bounds": bounds,
            "units_per_space": 250, "source": "verovio", "font": font,
            "code": "E05C", "components": ["E05C", code],
            "extraction": "original-clef-octave-components"}
    return result


@lru_cache(maxsize=1)
def native_glyphs() -> dict:
    """Return standalone authentic Verovio glyph assets with origin metadata.

    Coordinates remain in Verovio's font units; its normal staff space is
    250 units. This avoids reinterpreting full Verovio page SVG as a Godot
    page, and never ships or constructs our own music glyph paths.
    """
    import copy
    import verovio
    from .runtime import _create_verovio_toolkit, _verovio_resources

    resources = _verovio_resources(verovio)
    font = _create_verovio_toolkit(verovio).getOptions().get("font", "Leipzig")
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    assets = {}
    for name, code in _NATIVE_CODES.items():
        if name in ('clef_c_8va','clef_c_15ma','clef_c_15mb'):
            continue  # Composed below from the genuine C/ottava components.
        box = metrics.find(f"g[@c='{code}']")
        source = resources / font / f"{code}.xml"
        if name.startswith("clef_") and (box is None or not source.is_file()):
            assets[name] = _engraved_clef(font, name, code)
            continue
        if box is None:
            raise RuntimeError(f"Verovio {font} lacks glyph metrics {name} ({code})")
        if not source.is_file():
            raise RuntimeError(f"Verovio {font} lacks glyph contour {name} ({code})")
        glyph = ET.parse(source).getroot()
        if not any(item.tag.rsplit("}", 1)[-1] == "path" and item.get("d")
                   for item in glyph.iter()):
            raise RuntimeError(f"Verovio glyph {name} has no vector path")
        x, y, w, h = (float(box.get(k)) for k in ("x", "y", "w", "h"))
        # Verovio contours are already y-reflected in the glyph <path>.
        # (0, 0) stays the original SMuFL engraving origin.
        bounds = [x - 12, -y - h - 12, w + 24, h + 24]
        if w <= 0 or h <= 0:
            raise RuntimeError(f"Invalid glyph bounds: {name}")
        svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                         viewBox=" ".join(str(v) for v in bounds),
                         width=str(bounds[2]), height=str(bounds[3]),
                         fill="white")
        svg.append(copy.deepcopy(glyph))
        assets[name] = {
            "svg": ET.tostring(svg, encoding="unicode"),
            "bounds": bounds, "units_per_space": 250, "source": "verovio",
            "code": code, "font": font,
        }
    assets.update(_c_octave_components(assets,resources,font))
    return assets
