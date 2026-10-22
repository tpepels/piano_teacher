"""Read the external engraving font without consulting production asset code.

SMuFL codepoints and font metrics are the reference. In particular, never read
fixture.json's renderer atlas to decide what a correct glyph looks like.
"""
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree as ET


@lru_cache(maxsize=1)
def reference_glyphs() -> dict:
    import verovio

    # The application engraving contract uses Leipzig. Read the installed
    # wheel's immutable resources directly: toolkit defaults can be mutated
    # by another engraver and are not an independent reference location.
    resources = Path(verovio.__file__).resolve().parent / "data"
    font = "Leipzig"
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    codes = {"head_whole":"E0A2", "head_half":"E0A3", "head_black":"E0A4"}
    codes.update(zip(("rest_"+n for n in
                     ("whole","half","quarter","eighth","16th","32nd","64th","128th")),
                    (f"{code:04X}" for code in range(0xE4E3,0xE4EB))))
    result = {}
    for name, code in codes.items():
        metric = metrics.find(f"g[@c='{code}']")
        if metric is None:
            continue
        x,y,w,h = (float(metric.get(k)) for k in ("x","y","w","h"))
        bounds = [x-12,-y-h-12,w+24,h+24]
        svg = ET.Element("svg",xmlns="http://www.w3.org/2000/svg",
                         viewBox=" ".join(map(str,bounds)),fill="white")
        svg.append(ET.parse(resources/font/f"{code}.xml").getroot())
        result[name] = {"svg":ET.tostring(svg,encoding="unicode"),
                        "bounds":bounds,"font":font,"code":code}
    return result
