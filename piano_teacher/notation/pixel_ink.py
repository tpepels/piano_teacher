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


def translating_ink(image: Image.Image) -> np.ndarray:
    """Pale score ink without the fixed, pale-mint timing overlay.

    bright() once excluded the playhead because it was saturated mint with
    too little red. Since 13598000/39caeee0 the rule's core (about
    201,248,230) and its beat knob are pale mint and pass bright(). They stay
    put while the score moves, so motion estimates must not let them vote.
    This drops every mint-tinted pixel (green and blue clearly above red);
    neutral score ink is never tinted in a canonical capture.
    """
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    overlay = (rgb[:,:,1]-rgb[:,:,0] > 30) & (rgb[:,:,2]-rgb[:,:,0] > 15)
    return bright(image) & ~overlay


SUPERSAMPLE = 4
# Template sub-pixel phases, in 1/SUPERSAMPLE pixel steps along x and y.
PHASES = tuple((fx, fy) for fy in range(0, SUPERSAMPLE, 2)
               for fx in range(SUPERSAMPLE))
# The native view draws each glyph at display scale with antialiased edges
# (glyphs.gd _display_texture), so screen ink is the glyph's pixel COVERAGE.
# A template is the same outline's coverage at the same size and sub-pixel
# phase, binarized at the coverage bright() needs to call a pixel ink.
INK_COVERAGE = .63


@lru_cache(maxsize=1024)
def _outline_coverage(svg: str, width: int, height: int) -> np.ndarray:
    n = SUPERSAMPLE
    png = cairosvg.svg2png(bytestring=svg.encode(),
                          output_width=width*n, output_height=height*n)
    alpha = np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3]/255.0
    return np.pad(alpha, ((0, n), (0, n)))


# The unexpected-symbol scanner deliberately claims any symbol-like ink,
# including faint antialiased rims; it keeps the generous original cut.
SCAN_COVERAGE = 96/255


@lru_cache(maxsize=1024)
def rasterize_outline(svg: str, width: int, height: int,
                      phase: tuple[int, int] = (0, 0),
                      coverage: float = INK_COVERAGE) -> np.ndarray:
    """Outline coverage at display size, moved right/down by phase/SUPERSAMPLE px."""
    n = SUPERSAMPLE
    fx, fy = phase
    alpha = np.roll(_outline_coverage(svg, width, height), (fy, fx), axis=(0, 1))
    covered = alpha[:height*n, :width*n].reshape(height, n, width, n).mean(axis=(1, 3))
    return covered > coverage if coverage < INK_COVERAGE else covered >= coverage


def pixel_runs(values):
    indices = np.flatnonzero(values)
    if not len(indices):
        return []
    return [(int(a[0]), int(a[-1])+1) for a in np.split(indices, np.flatnonzero(np.diff(indices) > 1)+1)]
