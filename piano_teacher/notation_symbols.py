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
