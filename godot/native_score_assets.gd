extends RefCounted

# Score loading's authentic Verovio asset boundary. Installation happens
# before semantic-score rendering, never by approximating missing glyphs.
const ASSET_KEYS := [
    "native_glyphs", "native_note_templates", "native_tie_templates",
    "native_chord_templates", "native_beam_fragments",
    "native_tuplet_fragments", "native_slur_fragments",
    "native_required_slur_pairs", "native_slurs_complete",
    "native_required_beam_groups", "native_beams_complete",
]

static func install(renderer, source: Dictionary) -> Dictionary:
    var accepted: bool = renderer.set_verovio_glyphs(
        source.get("native_glyphs", {}),
        source.get("native_note_templates", {}),
        source.get("native_tie_templates", {}),
        source.get("native_chord_templates", {}),
        source.get("native_beam_fragments", {}),
        source.get("native_tuplet_fragments", {}),
        source.get("native_slur_fragments", {}),
        source.get("native_required_slur_pairs", []),
        bool(source.get("native_slurs_complete", false)),
        source.get("native_required_beam_groups", []),
        bool(source.get("native_beams_complete", false)))
    if not accepted:
        return {"ok":false, "error":str(renderer.failure_reason)}
    # Strip large SVG/Sprite payloads before saving compact layout metadata.
    # Preserve caller's original reply in case another consumer inspects it.
    var layout: Dictionary = source.duplicate(false)
    for key in ASSET_KEYS:
        layout.erase(key)
    return {"ok":true, "layout":layout}
