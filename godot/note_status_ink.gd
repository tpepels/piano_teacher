extends RefCounted
## Single authentic-notehead color/glow painter. All light is drawn using
## the exact Verovio notehead alpha mask, never a circle, arc, badge,
## particle, ColorRect or separate bloom positioned near the note.
const Status := preload("res://note_status_registry.gd")
const Design := preload("res://practice_theme.gd")
const COLORS := {
    "hit": Color("#53E7B7"),
    "missed": Color("#F17978"),
    "late": Color("#F0B661"),
    "early_release": Color("#BCA4F1"),
    "early_onset": Color("#EBCF81"),
}
const CORE_ALPHA := 0.97
const INNER_GLOW_ALPHA := 0.105
const OUTER_GLOW_ALPHA := 0.045
const INNER_SCALE := 1.024
const OUTER_SCALE := 1.052

static func color_for(status: String) -> Color:
    return COLORS.get(status,Design.SCORE_INK)

static func glow_strength(status: String) -> float:
    return 0.0 if status == Status.UNPLAYED else OUTER_GLOW_ALPHA

static func paint(canvas: CanvasItem, glyphs,
        head: String, point: Vector2, gap: float, status: String) -> bool:
    if status == Status.UNPLAYED or not COLORS.has(status):
        return false
    if not is_instance_valid(canvas) or glyphs == null or \
            not glyphs.has_method("paint"):
        return false
    var tint: Color = COLORS[status]
    # The same genuine notehead texture is composited three times. The
    # 2.4% and 5.2% expansion adds only an extremely soft contour-bound
    # light at the very edge of the note (about 1 px at normal staff size).
    # The inner core is the changed note itself. Hollow notes remain hollow.
    glyphs.paint(canvas,head,point.x,point.y,gap*OUTER_SCALE,
        Color(tint,OUTER_GLOW_ALPHA),true)
    glyphs.paint(canvas,head,point.x,point.y,gap*INNER_SCALE,
        Color(tint,INNER_GLOW_ALPHA),true)
    return bool(glyphs.paint(canvas,head,point.x,point.y,gap,
        Color(tint,CORE_ALPHA),true))
