extends RefCounted
## Single authentic-notehead status painter. All light uses the exact
## Verovio notehead alpha mask, never a circle, badge, particle or ColorRect.
##
## The status colour seeps out of the head rather than being drawn over it
## (owner request 2026-11-24), in passes of the same head mask:
##   BLEED  blend ADD: widening, fading copies of the head: light spreading
##          into the dark stage around the note, strongest at its contour;
##   CORE   blend MIX: a translucent tint over the authentic white head, so
##          the head reads coloured yet stays lit from within;
##   FILL   blend MIX: a soft wash inside hollow (half/whole) heads.
const Status := preload("res://note_status_registry.gd")
const Design := preload("res://practice_theme.gd")
const EARLY_ONSET := Color("#F08FCB")
const COLORS := {
    "sounding": Color("#53E7B7"),
    "hit": Color("#53E7B7"),
    "missed": Color("#F17978"),
    # Practice flow (docs/practice-flow.md): two colours only. An attack
    # clearly too early or late is an error (red); key-release timing is
    # not graded on screen (green).
    "late": Color("#F17978"),
    "early_release": Color("#53E7B7"),
    "early_onset": Color("#F17978"),
}
const PASSES := ["bleed", "core", "fill"]
## Core: a paler full-head tint plus a denser inner copy, so colour is
## strongest at the centre and thins toward the head's own edge.
const CORE_ALPHA := 0.38
const CORE_INNER := [0.72, 0.34]
const INTERIOR_ALPHA := 0.32
## (scale about the head centre, alpha): a gradual falloff, no hard ring.
const BLEED := [[1.08, .24], [1.18, .17], [1.3, .12], [1.45, .08],
    [1.62, .05], [1.85, .03], [2.1, .015]]

static func color_for(status: String) -> Color:
    return COLORS.get(status,Design.SCORE_INK)

static func material_for(pass_name: String) -> CanvasItemMaterial:
    var material := CanvasItemMaterial.new()
    material.blend_mode = (CanvasItemMaterial.BLEND_MODE_ADD if pass_name == "bleed"
        else CanvasItemMaterial.BLEND_MODE_MIX)
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
        "bleed":
            var painted := false
            for ring in BLEED:
                painted = bool(glyphs.paint_head(canvas,instance,
                    Color(tint,float(ring[1])),float(ring[0]))) or painted
            return painted
        "core":
            glyphs.paint_head(canvas,instance,Color(tint,float(CORE_INNER[1])),float(CORE_INNER[0]))
            return bool(glyphs.paint_head(canvas,instance,Color(tint,CORE_ALPHA)))
        "fill":
            return bool(glyphs.paint_head_interior(canvas,instance,
                Color(tint,INTERIOR_ALPHA)))
    return false
