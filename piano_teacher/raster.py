"""Rasterize Verovio notation for Godot's PNG image loader.

The original SVG is retained for exact engraving geometry and optional
browser diagnostics. PNG rendering avoids differences in SVG <use>/<symbol>
support between Godot versions.
"""
from __future__ import annotations
from io import BytesIO


def rasterize_score(svg: str, *, width: int = 2000) -> bytes:
    """Convert sheet music to a verified, visible PNG image."""
    # Continuous one-system lessons can require a wider source PNG to
    # avoid enlarging small note glyphs on HiDPI/fullscreen displays.
    # The engine restricts these requests to short, single-system passages.
    if not 600 <= width <= 12000:
        raise ValueError("Invalid engraving image width")
    try:
        import cairosvg
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Sheet music display requires CairoSVG and Pillow: "
            "python -m pip install -e '.[godot,test]'"
        ) from exc
    try:
        output = cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=width)
        with Image.open(BytesIO(output)) as image:
            if image.width < 600 or image.height < 30:
                raise ValueError("Rasterized score image has invalid dimensions")
            if image.width * image.height > 24_000_000:
                raise ValueError("Rasterized score image is too large")
            on_white = Image.new("RGBA", image.size, (255, 255, 255, 255))
            on_white.alpha_composite(image.convert("RGBA"))
            # Detect empty SVG pages rather than silently showing a white texture.
            minimum, maximum = on_white.convert("L").getextrema()
            if minimum > 220:
                raise ValueError(
                    "Engraving produced a blank page. Check Verovio font "
                    "resources and inspect /score.svg in a browser."
                )
    except Exception as exc:
        raise RuntimeError(f"Cannot rasterize engraved score: {exc}") from exc
    return output
