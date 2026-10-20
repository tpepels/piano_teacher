"""Compatibility exports for source SVG geometry and legacy page layout."""
from .notation.assets.svg_geometry import (
    Matrix, IDENTITY, TRANSFORM, NUMBERS, _mul, _transform, _apply,
    _classes, _element_position, PageGeometry, parse_svg_geometry,
)
from .rendering.legacy.geometry import layout_from_pages, locate_beat
