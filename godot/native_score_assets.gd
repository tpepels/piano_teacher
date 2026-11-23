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

## Shared source and structural check for current and pre-engraved future
## score bundles. No renderer may be mutated until this contract holds.
static func bundle_error(bundle: Variant, expected: Dictionary) -> String:
    if not bundle is Dictionary or str(bundle.get("status","")) != "ready":
        return "Score bundle was not ready"
    var fingerprint: String = str(bundle.get("fingerprint",""))
    var revision: int = int(bundle.get("revision",-1))
    var hand: String = str(bundle.get("hand",""))
    var stage_key: String = str(bundle.get("stage_key",""))
    if (fingerprint.is_empty() or stage_key.is_empty() or
            hand not in ["right","left","both"] or revision < 0):
        return "Score bundle lacks its canonical source identity"
    for field in ["fingerprint","revision","hand","stage_key"]:
        if expected.has(field) and expected[field] != bundle.get(field):
            return "Score bundle %s differs from selected source" % field
    var layout: Variant = bundle.get("layout")
    var model: Variant = bundle.get("model")
    var source_ids: Variant = bundle.get("source_note_ids")
    if (not layout is Dictionary or not layout.has("anchors") or
            int(layout.get("revision",-1)) != revision or
            not model is Dictionary or int(model.get("revision",-1)) != revision):
        return "Score bundle has mismatched or missing notation revisions"
    if not source_ids is Array or source_ids.is_empty():
        return "Score bundle has no original MIDI note identities"
    var observed: Dictionary = {}
    for note_id in source_ids:
        if not note_id is String or note_id.is_empty() or observed.has(note_id):
            return "Score bundle has empty or duplicate MIDI note identities"
        observed[note_id] = true
    var active_ids: Variant = model.get("active_note_ids")
    if not active_ids is Array:
        return "Score bundle has no semantic active-note identity list"
    for active_id in active_ids:
        if not observed.has(active_id):
            return "Score bundle semantic note is absent from MIDI source"
    return ""


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
