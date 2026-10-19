"""Small standalone preparation glyphs from the installed Verovio font.

Keep the exact font outlines and origins used by the exercise engraving, without
shipping a second music font or approximating clefs/rests with text characters.
"""
from functools import lru_cache
import xml.etree.ElementTree as ET


@lru_cache(maxsize=1)
def preparation_symbols() -> dict:
    import verovio
    from .score import _create_verovio_toolkit, _verovio_resources

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
    "clef_g": "E050", "clef_f": "E062", "clef_c": "E05C",
    "head_whole": "E0A2", "head_half": "E0A3", "head_black": "E0A4",
    "augmentation_dot": "E1E7",
    "repeat_dot": "E044",
    "rest_whole": "E4E3", "rest_half": "E4E4",
    "rest_quarter": "E4E5", "rest_eighth": "E4E6",
    "rest_16th": "E4E7", "rest_32nd": "E4E8", "rest_64th": "E4E9",
    "acc_flat": "E260", "acc_natural": "E261", "acc_sharp": "E262",
    "acc_double_sharp": "E263", "acc_double_flat": "E264",
    "flag_up_1": "E240", "flag_down_1": "E241",
    "flag_up_2": "E242", "flag_down_2": "E243",
    "flag_up_3": "E244", "flag_down_3": "E245",
    "flag_up_4": "E246", "flag_down_4": "E247",
    **{f"time_{n}": f"{0xE080 + n:04X}" for n in range(10)},
}


@lru_cache(maxsize=1)
def native_glyphs() -> dict:
    """Return standalone authentic Verovio glyph assets with origin metadata.

    Coordinates remain in Verovio's font units; its normal staff space is
    250 units. This avoids reinterpreting full Verovio page SVG as a Godot
    page, and never ships or constructs our own music glyph paths.
    """
    import copy
    import verovio
    from .score import _create_verovio_toolkit, _verovio_resources

    resources = _verovio_resources(verovio)
    font = _create_verovio_toolkit(verovio).getOptions().get("font", "Leipzig")
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    assets = {}
    for name, code in _NATIVE_CODES.items():
        box = metrics.find(f"g[@c='{code}']")
        if box is None:
            raise RuntimeError(f"Verovio {font} lacks glyph metrics {name} ({code})")
        source = resources / font / f"{code}.xml"
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
    return assets
