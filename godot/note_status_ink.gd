extends RefCounted
## Single authentic-notehead recoloring painter. All light is drawn using the
## exact Verovio notehead alpha mask, never a circle, arc, badge, particle,
## ColorRect or separate bloom positioned near the note.
##
## A status head is recolored IN PLACE, inside the retained source strip that
## owns the note, with three passes of the same head mask:
##   ERASE  blend SUB: subtract the exact ink the strip painted for this head
##          (the template's own head texels, same rectangle, staff space and
##          ink color -- see glyphs.gd head_cutout);
##   CORE   blend ADD: add the status tint with the same coverage;
##   GLOW   blend MIX: two barely larger copies at very low alpha.
## For coverage a over background b, the strip held b(1-a)+ink*a. ERASE+CORE
## leave exactly b(1-a)+tint*a: the white head is replaced, not overpainted,
## so no white contour survives under or around the colored one.
const Status := preload("res://note_status_registry.gd")
const Design := preload("res://practice_theme.gd")
const EARLY_ONSET := Color("#F08FCB")
const COLORS := {
    "hit": Color("#53E7B7"),
    "missed": Color("#F17978"),
    "late": Color("#F0B661"),
    "early_release": Color("#BCA4F1"),
    # C6: a soft orchid pink, clearly apart from mint (hue 160), coral (0),
    # amber (36) and lavender (258) at practice distance, and still 7:1 on the
    # stage. One constant: change it here (and nowhere else).
    "early_onset": EARLY_ONSET,
}
const PASSES := ["erase", "core", "fill", "glow"]
## C5: hollow (half, whole) heads also get their enclosed interior softly
## tinted, inside the head's own glyph region, so the status reads without a
## ring. Solid heads have no interior and are unaffected.
const INTERIOR_ALPHA := 0.55
const CORE_ALPHA := 1.0
const INNER_GLOW_ALPHA := 0.105
const OUTER_GLOW_ALPHA := 0.045
const INNER_SCALE := 1.024
const OUTER_SCALE := 1.052

static func color_for(status: String) -> Color:
    return COLORS.get(status,Design.SCORE_INK)

static func glow_strength(status: String) -> float:
    return 0.0 if status == Status.UNPLAYED else OUTER_GLOW_ALPHA

static func material_for(pass_name: String) -> CanvasItemMaterial:
    var material := CanvasItemMaterial.new()
    material.blend_mode = (CanvasItemMaterial.BLEND_MODE_SUB if pass_name == "erase"
        else CanvasItemMaterial.BLEND_MODE_ADD if pass_name == "core"
        else CanvasItemMaterial.BLEND_MODE_MIX)  # fill and glow are plain mixes
    return material

## Paint one pass for one physical head. ``instance`` is the immutable record
## the strip stored when it engraved the head: position, head mask, ink, staff
## space and the exact artwork (template, head index, anchor) it came from.
static func paint(canvas: CanvasItem, glyphs, instance: Dictionary,
        status: String, pass_name: String) -> bool:
    if status == Status.UNPLAYED or not COLORS.has(status):
        return false
    if not is_instance_valid(canvas) or glyphs == null or \
            not glyphs.has_method("paint_head"):
        return false
    var tint: Color = COLORS[status]
    match pass_name:
        "erase":
            # Exactly the ink the strip painted for this head, subtracted.
            return bool(glyphs.paint_head(canvas,instance,instance["ink"]))
        "core":
            return bool(glyphs.paint_head(canvas,instance,Color(tint,CORE_ALPHA)))
        "fill":
            return bool(glyphs.paint_head_interior(canvas,instance,
                Color(tint,INTERIOR_ALPHA)))
        "glow":
            # 2.4% and 5.2% expansion of the authentic head mask about its
            # centre: an extremely soft, contour-bound light about 1 px wide.
            glyphs.paint_head(canvas,instance,Color(tint,OUTER_GLOW_ALPHA),OUTER_SCALE)
            return bool(glyphs.paint_head(canvas,instance,
                Color(tint,INNER_GLOW_ALPHA),INNER_SCALE))
    return false
