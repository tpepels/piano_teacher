"""Authentic bounded SVG vector rasterization for notation fragments.

Beams and tuplets share one recording/rasterization owner; neither module
imports private graphics helpers from the other.
"""
from __future__ import annotations

import base64
from io import BytesIO
import math
import sys

from PIL import Image

MAX_RASTER_PIXELS = 8_000_000
def local_vector_art(svg, staff_space, origin, source):
    """Rasterize small source ink at up to 32px/space in a local bitmap.

    A recording surface retains the genuine vector paths and inherited SVG
    transforms without allocating a giant page image. Its actual ink extent
    determines the bounded bitmap; viewport width never limits glyph detail.
    """
    from cairosvg.parser import Tree
    from cairosvg.surface import Surface, cairo

    if (not math.isfinite(staff_space) or staff_space <= 0
            or not all(math.isfinite(v) for v in origin)):
        return None

    class RecordingSurface(Surface):
        device_units_per_user_units = 1

        def _create_surface(self, width, height):
            return cairo.RecordingSurface(cairo.CONTENT_COLOR_ALPHA, None), width, height

    recording = RecordingSurface(Tree(bytestring=svg.encode()), None, 96, output_width=1600)
    pixels = staff_space*recording.height
    x, y, width, height = recording.cairo.ink_extents()
    if (min(width, height, pixels) <= 0
            or not all(math.isfinite(v) for v in (
                x, y, width, height, pixels, x+width, y+height))):
        return None

    def raster_bounds(density):
        scale = density/pixels
        edges = (x*scale, y*scale, (x+width)*scale, (y+height)*scale)
        if not math.isfinite(scale) or not all(math.isfinite(v) for v in edges):
            return None
        left, top = math.floor(edges[0])-1, math.floor(edges[1])-1
        right, bottom = math.ceil(edges[2])+1, math.ceil(edges[3])+1
        w, h = right-left, bottom-top
        if not (0 < w <= 1500 and 0 < h <= 850 and w*h <= MAX_RASTER_PIXELS):
            return None
        return left, top, right, bottom

    density = 32.0
    bounds = raster_bounds(density)
    if bounds is None:
        # Keep at least the previous recovery path's 8px/space detail.
        density, upper = 8.0, 32.0
        bounds = raster_bounds(density)
        if bounds is None:
            return None
        # Include integer rounding and padding in every allocation check.
        for _ in range(24):
            candidate = (density+upper)*.5
            fitted = raster_bounds(candidate)
            if fitted is None:
                upper = candidate
            else:
                density, bounds = candidate, fitted
    scale = density/pixels
    offset_x, offset_y = origin[0]*recording.width*scale, origin[1]*recording.height*scale
    if not all(math.isfinite(v) for v in (offset_x, offset_y)):
        return None
    left, top, right, bottom = bounds
    w, h = right-left, bottom-top
    bitmap = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    context = cairo.Context(bitmap)
    context.translate(-left, -top)
    context.scale(scale, scale)
    context.set_source_surface(recording.cairo, 0, 0)
    context.paint()
    # Cairo stores native-endian premultiplied ARGB. Only coverage is
    # published: the retained scene supplies the final ink colour.
    bitmap.flush()
    alpha_offset = 3 if sys.byteorder == "little" else 0
    alpha_bytes = memoryview(bitmap.get_data())[alpha_offset::4].tobytes()
    alpha = Image.frombytes("L", (w, h), alpha_bytes, "raw", "L", bitmap.get_stride() // 4)
    bbox = alpha.getbbox()
    if bbox is None:
        return None
    a, b, c, d = bbox
    clipped = alpha.crop(bbox)
    white = Image.new("RGBA", clipped.size, (255, 255, 255, 255))
    white.putalpha(clipped)
    encoded = BytesIO()
    white.save(encoded, format='PNG', optimize=True)
    return {'source': source, 'units_per_space': 250,
            'bounds': [(left+a-offset_x)*250/density,
                       (top+b-offset_y)*250/density,
                       (c-a)*250/density, (d-b)*250/density],
            'png_base64': base64.b64encode(encoded.getvalue()).decode()}
