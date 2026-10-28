"""Photographed pale ink and independent SVG alpha masks.

This is raster calibration only: no source binding, native assets, or proof
coordinator is consulted. Cached masks retain the existing 256-entry bound.
"""
from functools import lru_cache
from io import BytesIO

import cairosvg
import numpy as np
from PIL import Image


def bright(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    # Native score ink is pale; native staff rules are dim and the mint
    # playhead has too little red. This does not consult Godot telemetry.
    return ((rgb[:,:,0] > 155) & (rgb[:,:,1] > 160) & (rgb[:,:,2] > 150))


@lru_cache(maxsize=256)
def rasterize_outline(svg: str, width: int, height: int) -> np.ndarray:
    png = cairosvg.svg2png(bytestring=svg.encode(),
                          output_width=width, output_height=height)
    return np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3] > 96


def pixel_runs(values):
    indices = np.flatnonzero(values)
    if not len(indices):
        return []
    return [(int(a[0]), int(a[-1])+1) for a in np.split(indices, np.flatnonzero(np.diff(indices) > 1)+1)]
