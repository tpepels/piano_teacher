"""Compatibility exports for imported pieces and optional Verovio page rendering.

The canonical native score instead consumes the semantic model and native
Verovio assets from their owning packages.
"""
from .importing.pieces import import_piece, _music21
from .notation.assets.runtime import (
    _create_verovio_toolkit, _verovio_resources, _verovio_object,
)
from .rendering.legacy.engraving import (
    _pitches_from_verovio, _fade_inactive_staff, EngravedScore,
    render_layout, _can_remove_repeated_system_headers,
    _safe_reprinted_header_starts, _engrave_xml, _svg_pages,
    render_measures,
)
