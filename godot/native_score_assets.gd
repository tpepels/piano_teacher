extends RefCounted

# Score loading's authentic Verovio asset boundary. Installation happens
# before semantic-score rendering, never by approximating missing glyphs.
const ASSET_KEYS := [
    "native_glyphs", "native_note_templates", "native_tie_templates",
    "native_chord_templates", "native_beam_fragments",
    "native_tuplet_fragments", "native_slur_fragments",
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
    if (not layout is Dictionary or not layout.get("anchors") is Array or
            not layout.get("notes") is Array or not layout.get("attack_map") is Dictionary or
            int(layout.get("revision",-1)) != revision or
            not model is Dictionary or int(model.get("revision",-1)) != revision):
        return "Score bundle has mismatched or missing notation revisions"
    for name in ASSET_KEYS:
        if not layout.get(name) is Dictionary:
            return "Score bundle has a malformed %s catalog" % name
        for entry in layout[name].values():
            if not entry is Dictionary:
                return "Score bundle has a malformed %s entry" % name
    for name in ["native_required_slur_pairs","native_required_beam_groups"]:
        if not layout.get(name) is Array:
            return "Score bundle has a malformed %s list" % name
    for name in ["native_slurs_complete","native_beams_complete"]:
        if not layout.get(name) is bool:
            return "Score bundle lacks its %s extraction status" % name
    if not source_ids is Array or source_ids.is_empty():
        return "Score bundle has no original MIDI note identities"
    var observed: Dictionary = {}
    for note_id in source_ids:
        if not note_id is String or note_id.is_empty() or observed.has(note_id):
            return "Score bundle has empty or duplicate MIDI note identities"
        observed[note_id] = true
    var active_ids: Variant = model.get("active_note_ids")
    if not active_ids is Array or active_ids.is_empty():
        return "Score bundle has no semantic active-note identity list"
    var attacks: Dictionary = layout["attack_map"]
    for active_id in active_ids:
        if not observed.has(active_id) or str(attacks.get(active_id,"")).is_empty():
            return "Score bundle active attack is missing from the source engraving"
    return ""


# Same authenticated loader, on a detached CPU engraving rather than a view.
static func prepare_engraving(engraving, source: Dictionary) -> bool:
    return engraving.load_assets(
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
