"""Preparation uses the installed engraving font's real musical symbols."""
from io import BytesIO
import xml.etree.ElementTree as ET

from PIL import Image


def test_preparation_symbols_have_real_visible_outlines_and_staff_units():
    from piano_teacher.notation_symbols import preparation_symbols
    from piano_teacher.raster import rasterize_score

    symbols = preparation_symbols()
    assert set(symbols) == {"treble", "bass", "quarter_rest", "eighth_rest"}
    for symbol in symbols.values():
        root = ET.fromstring(symbol["svg"])
        assert any(e.tag.endswith("path") and e.get("d") for e in root.iter())
        assert symbol["units_per_space"] == 250
        assert symbol["bounds"][2] > 0 and symbol["bounds"][3] > 0
        image = Image.open(BytesIO(rasterize_score(symbol["svg"], width=600)))
        assert image.convert("RGBA").getchannel("A").getbbox() is not None
