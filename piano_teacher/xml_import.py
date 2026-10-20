"""Compatibility exports for the public source MusicXML import API.

Implementation belongs to piano_teacher.importing.musicxml.
"""
from .importing.musicxml import _xml_root, _number, load_musicxml

__all__ = ["load_musicxml"]
