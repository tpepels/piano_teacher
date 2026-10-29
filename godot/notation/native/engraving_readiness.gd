extends RefCounted

# Validate only authentic Verovio components before native painting.
# No layout mutation, fallback generation or score-inference decisions.
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")

static func missing(layout, glyphs, connector_geometry,
        expected_beam_groups: Array, beam_extraction_complete: bool,
        expected_slur_pairs: Array, slur_extraction_complete: bool) -> String:
    if not beam_extraction_complete:
        return "Source Verovio beam extraction failed"
    for key in expected_beam_groups:
        if not glyphs.beam_textures.has(str(key)):
            return "Missing original Verovio beam: "+str(key)
    if not slur_extraction_complete:
        return "Source Verovio slur extraction failed"
    for group in layout.notation_tuplets:
        if SymbolPainter.tuplet_hidden(group):
            continue
        var ids := PackedStringArray()
        for event in group.get("events",[]):
            ids.append(str(event.get("id","")))
        if ids.is_empty() or not glyphs.has_tuplet("|".join(ids),
                str(group.get("bracket","yes")) == "yes"):
            return "Missing engraved Verovio tuplet: "+("|".join(ids))
    for leader_id in layout.chord_members:
        var event: Dictionary = {}
        for candidate in layout.chord_members[leader_id]:
            if str(candidate.get("id","")) == str(leader_id):
                event = candidate
                break
        if event.is_empty():
            return "Missing original chord leader: "+str(leader_id)
        var key: String = layout.chord_template_key(event)
        if key.is_empty() or not glyphs.has_chord(key):
            return "Missing engraved Verovio chord: "+str(leader_id)+ \
                " (pattern="+key+", atlas="+ \
                str(glyphs.chord_textures.size())+" templates)"
        if layout.beamed_note_ids.has(str(leader_id)) and ( \
                not glyphs.has_chord_heads(key) or \
                not glyphs.has_chord_stem(key)):
            return "Missing Verovio beamed chord components: "+str(leader_id)
    for pair in expected_slur_pairs:
        if not pair is Array or pair.size() != 2:
            return "Invalid original Verovio slur identity"
        var key: String = str(pair[0])+"|"+str(pair[1])
        if not glyphs.slur_metadata.has(key) or \
                glyphs.slur_note_ids(key) != pair:
            return "Missing original Verovio slur: "+key
    for pair in layout.tie_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var key: String = connector_geometry.tie_template_key(first,last,{"down":connector_geometry.tie_bow_down(first,last,1.0)},1.0)
        if not glyphs.tie_metadata.has(key):
            return "Missing authentic flag-aware tie contour: "+key
    return ""
