"""Assemble native score assets from selected notation and existing cache.

A stateless application collaborator: no PracticeEngine access, no new cache.
"""
from __future__ import annotations


def assemble_layout(source_score, *, native_notes: bool = False,
                    native_model: dict | None = None,
                    notation_xml: str | None = None,
                    cache=None, cache_key: str = "") -> dict:
    from ..notation_symbols import native_glyphs, preparation_symbols
    layout = {**source_score.layout, "symbols": preparation_symbols(),
              "native_glyphs": native_glyphs()}
    if native_notes:
        if native_model is None or not notation_xml:
            raise ValueError("Native score preparation requires the selected lesson model and MusicXML")
        # Build the identity-preserving model once for all fragment
        # extractors, rather than reparsing the lesson four times.
        from ..verovio_note_templates import note_templates
        from ..verovio_tie_templates import tie_templates
        from ..verovio_chord_templates import chord_templates
        # Variable chord patterns are pre-engraved individually and
        # reused via a disk cache; unsupported patterns remain native.
        layout["native_note_templates"] = note_templates(cache)
        # The backend's raster notation must remain available even if
        # the installed Verovio version changes its compound SVG markup.
        # Never fail the entire /score/layout response for optional art.
        try:
            layout["native_tie_templates"] = tie_templates(cache)
        except Exception as exc:
            print("VEROVIO_TIE_TEMPLATE_UNAVAILABLE:", type(exc).__name__, exc)
            layout["native_tie_templates"] = {}
        try:
            layout["native_chord_templates"] = chord_templates(
                native_model, cache)
        except Exception as exc:
            print("VEROVIO_CHORD_TEMPLATE_UNAVAILABLE:", type(exc).__name__, exc)
            layout["native_chord_templates"] = {}
        # These fragments are cut directly from this lesson's original
        # Verovio engraving. They retain the two real note identities,
        # leaving the Godot transport in complete control of timing.
        try:
            from ..verovio_beam_fragments import (
                beam_fragments, expected_beam_groups)
            layout["native_required_beam_groups"] = expected_beam_groups(
                source_score.pages,native_model)
            layout["native_beams_complete"] = True
            layout["native_beam_fragments"] = beam_fragments(
                source_score.pages, native_model, cache,
                cache_key)
            if layout["native_beam_fragments"]:
                print("VEROVIO_NATIVE_BEAMS:",
                      len(layout["native_beam_fragments"]))
        except Exception as exc:
            print("VEROVIO_BEAM_FRAGMENTS_UNAVAILABLE:",
                  type(exc).__name__,exc)
            layout["native_beam_fragments"] = {}
            layout["native_required_beam_groups"] = []
            layout["native_beams_complete"] = False
        try:
            from ..verovio_tuplet_fragments import tuplet_fragments
            layout["native_tuplet_fragments"] = tuplet_fragments(
                source_score.pages, native_model,
                cache, cache_key)
        except Exception as exc:
            print("VEROVIO_TUPLET_FRAGMENTS_UNAVAILABLE:",
                  type(exc).__name__,exc)
            layout["native_tuplet_fragments"] = {}
        try:
            from ..verovio_slur_fragments import (
                slur_fragments, slur_pairs_from_xml)
            expected = slur_pairs_from_xml(notation_xml)
            available = {str(e["id"]) for e in
                         native_model.get("notation_events",[])
                         if e.get("kind")=="note" and e.get("id")}
            layout["native_required_slur_pairs"] = [
                list(pair) for pair in expected
                if pair[0] in available and pair[1] in available]
            layout["native_slurs_complete"] = True
            layout["native_slur_fragments"] = slur_fragments(
                source_score.pages,notation_xml,
                native_model,cache,
                cache_key)
        except Exception as exc:
            print("VEROVIO_SLUR_FRAGMENTS_UNAVAILABLE:",
                  type(exc).__name__,exc)
            layout["native_slur_fragments"] = {}
            layout["native_required_slur_pairs"] = []
            layout["native_slurs_complete"] = False
    return layout

