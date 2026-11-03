"""Assemble native score assets from selected notation and existing cache.

A stateless application collaborator: no PracticeEngine access, no new cache.
"""
from __future__ import annotations


class NativeScorePreparationError(RuntimeError):
    """Selected score cannot publish an incomplete native ink fragment."""


def _failed(stage: str, exc: Exception) -> NativeScorePreparationError:
    return NativeScorePreparationError(
        f"Native score {stage} preparation failed: {type(exc).__name__}: {exc}")


def assemble_layout(source_score, *,
                    native_model: dict,
                    notation_xml: str,
                    cache=None, cache_key: str = "",
                    revision: int | None = None) -> dict:
    if native_model is None or not notation_xml:
        raise ValueError("Score preparation requires selected notation and semantic model")
    from ..notation.assets.glyphs import native_glyphs, preparation_symbols
    layout = {**source_score.layout, "symbols": preparation_symbols(),
              "native_glyphs": native_glyphs()}
    if revision is not None:
        layout["revision"] = revision
    # Build the identity-preserving model once for all fragment
    # extractors, rather than reparsing the lesson four times.
    from ..notation.assets.notes import note_templates
    from ..notation.assets.ties import tie_templates
    from ..notation.assets.chords import chord_templates
    # Variable chord patterns are pre-engraved individually and
    # reused via a disk cache; unsupported patterns remain native.
    layout["native_note_templates"] = note_templates(cache)
    # Missing required Verovio assets cannot be published as a partially
    # usable native score. The caller retries the same selected source.
    try:
        layout["native_tie_templates"] = tie_templates(cache)
    except Exception as exc:
        raise _failed("tie templates", exc) from exc
    # These fragments are cut directly from this lesson's original
    # Verovio engraving. They retain the two real note identities,
    # leaving the Godot transport in complete control of timing.
    try:
        from ..notation.assets.beams import (
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
        raise _failed("beam fragments", exc) from exc
    try:
        directions = {str(identifier): bool(fragment["stem_up"])
            for fragment in layout["native_beam_fragments"].values()
            for identifier in fragment["note_ids"]}
        layout["native_chord_templates"] = chord_templates(
            native_model, cache, stem_directions=directions)
    except Exception as exc:
        raise _failed("chord templates", exc) from exc
    try:
        from ..notation.assets.tuplets import tuplet_fragments
        layout["native_tuplet_fragments"] = tuplet_fragments(
            source_score.pages, native_model,
            cache, cache_key, notation_xml=notation_xml)
    except Exception as exc:
        raise _failed("tuplet fragments", exc) from exc
    try:
        from ..notation.assets.slurs import (
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
        raise _failed("slur fragments", exc) from exc
    return layout

