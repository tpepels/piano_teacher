"""Compatibility exports for source SVG geometry and legacy page layout."""
from .source_svg import (
    Matrix, IDENTITY, TRANSFORM, NUMBERS, PageGeometry, parse_svg_geometry,
)
from .rendering.legacy.geometry import layout_from_pages, locate_beat

__all__ = ("Matrix", "IDENTITY", "TRANSFORM", "NUMBERS", "PageGeometry",
           "parse_svg_geometry", "layout_from_pages", "locate_beat")
