extends RefCounted
## Native annotation placement and editing, with explicit drawing/frame inputs.
## Musical geometry and immutable source indices belong to ScoreLayout.
const Design := preload("res://practice_theme.gd")
const FingeringPlacement := preload("res://notation/native/fingering_placement.gd")
const FingeringSpatialLayout := preload("res://notation/native/fingering_spatial_layout.gd")
const FingeringObstacles := preload("res://notation/native/fingering_obstacles.gd")
const SourceVisibility := preload("res://notation/native/source_visibility.gd")
const FINGERING_FONT_SIZE := 16

signal fingering_change_requested(source_id: String, finger: Variant)

var score_layout
var connector_geometry
var obstacles
var fingering_layout: Array = []
var widest_fingering := 0.0
var drawn_fingerings: Array = []
var fingering_layout_gap := -1.0
var fingering_layout_height := -1.0
var fingering_popup: PopupMenu
var fingering_annotations_enabled := true
var fingering_placement_issues: Array = []
var fingering_metrics_cache: Dictionary = {}

func _init(layout, connectors) -> void:
    score_layout = layout
    connector_geometry = connectors
    obstacles = FingeringObstacles.new(layout,connectors)

## Clear once before painting all source-copy passes of a frame.
func begin_frame() -> void:
    drawn_fingerings.clear()

func clear() -> void:
    fingering_layout.clear()
    widest_fingering = 0.0
    drawn_fingerings.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = -1.0
    obstacles.clear()
    if fingering_popup != null:
        fingering_popup.hide()

func set_enabled(enabled: bool) -> void:
    fingering_annotations_enabled = enabled
    drawn_fingerings.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = -1.0
    if not enabled and fingering_popup != null:
        fingering_popup.hide()

func layout_fingerings(gap: float, play_from_beat: float = 0.0) -> void:
    fingering_layout.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = gap
    fingering_layout_height = score_layout.size.y
    var cell: float = maxf(64.0,score_layout.timeline.pixels_per_beat)
    var bins: Dictionary = {}
    obstacles.build(gap,bins,cell,play_from_beat)
    var candidates: Array = []
    var physical_keys: Dictionary = {}
    for event in score_layout.ordered_events:
        var assignment: Dictionary = FingeringPlacement.assignment(event)
        if assignment.is_empty():
            continue
        var key: String = "%.8f|%s|%s|%d" % [float(event["beat"]),assignment["hand"],
            str(event.get("midi_pitch",event.get("spelling",{}))),int(assignment["finger"])]
        if physical_keys.has(key):
            physical_keys[key]["event_ids"].append(str(event["id"]))
            continue
        var id: String = str(event["id"])
        var up: bool = bool(score_layout.chord_extents(event,gap,score_layout.cached_head_offsets)["up"])
        var direction: float = -1.0 if assignment["hand"] == "right" else 1.0
        if score_layout.voice_stem_up_by_note.has(id):
            direction = -1.0 if up else 1.0
        var item: Dictionary = {
            "event":event, "assignment":assignment, "event_ids":[id],
            "head":Vector2(float(event["beat"])*score_layout.timeline.pixels_per_beat
                +float(score_layout.cached_head_offsets.get(id,0.0)),score_layout.event_y(event,gap)),
            "up":up, "direction":direction,
            "chord":bool(event.get("chord",false)) or score_layout.chord_members.has(id),
            "staff_center":score_layout.staff_center(str(event["staff"]))}
        physical_keys[key] = item
        candidates.append(item)
    var font_size: int = clampi(roundi(gap*.75),11,FINGERING_FONT_SIZE)
    var cell_metrics: Dictionary = metrics(font_size)
    var packed: Dictionary = FingeringSpatialLayout.pack(candidates, cell_metrics,
        gap, score_layout.size.y, cell, bins, obstacles.staff_lines, font_size)
    fingering_layout = packed["layout"]
    # Layout packing is source-space work. Sort once so the dynamic
    # overlay never scans annotations in offscreen measures.
    fingering_layout.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return a["rect"].position.x < b["rect"].position.x)
    widest_fingering = 0.0
    for item in fingering_layout:
        widest_fingering = maxf(widest_fing,float(item["rect"].size.x))
    fingering_placement_issues = packed["issues"]


func metrics(font_size: int) -> Dictionary:
    if fingering_metrics_cache.has(font_size):
        return fingering_metrics_cache[font_size]
    var font: Font = ThemeDB.fallback_font
    var server := TextServerManager.get_primary_interface()
    var ink := Rect2()
    var width := 0.0
    for digit in range(1,6):
        width = maxf(width,font.get_string_size(str(digit),HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x)
        var rid: RID = font.get_rids()[0]
        var glyph: int = server.font_get_glyph_index(rid,font_size,str(digit).unicode_at(0),0)
        var box := Rect2(server.font_get_glyph_offset(rid,Vector2i(font_size,0),glyph),
            server.font_get_glyph_size(rid,Vector2i(font_size,0),glyph))
        ink = box if digit == 1 else ink.merge(box)
    var value := {"cell":Vector2(ceilf(width)+2.0,ceilf(font.get_height(font_size))),
        "ink_offset":Vector2(1.0,font.get_ascent(font_size))+ink.position,"ink_size":ink.size}
    fingering_metrics_cache[font_size] = value
    return value


## Context: active_hand, play_from_beat, score_loop_enabled, preparation_history.
## The canvas is used only for drawing; no canvas/view reference is retained.
func paint(canvas, clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0, context: Dictionary = {}) -> void:
    if not fingering_annotations_enabled:
        return
    if absf(fingering_layout_gap-gap) > .001 or absf(fingering_layout_height-score_layout.size.y) > .001:
        layout_fingerings(gap,float(context.get("play_from_beat",0.0)))
    var translation := Vector2(score_layout.timeline.screen_x(0.0,clock,playhead_x,float(context.get("play_from_beat",0.0))),0.0)
    var earliest: float = 30.0-translation.x-widest_fingering
    var latest: float = score_layout.size.x-translation.x
    var low := 0
    var high: int = fingering_layout.size()
    while low < high:
        var mid: int = (low+high)>>1
        if float(fingering_layout[mid]["rect"].position.x) < earliest:
            low = mid+1
        else:
            high = mid
    for index in range(low,fingering_layout.size()):
        var item: Dictionary = fingering_layout[index]
        if float(item["rect"].position.x) > latest:
            break
        if not SourceVisibility.event_visible(score_layout.expression_note_index.get(str(item["event_ids"][0]),{}),
                pass_start,bool(context.get("score_loop_enabled",false)),context.get("preparation_history",{})):
            continue
        var rect: Rect2 = item["rect"]
        rect.position += translation
        # A partial numeral can look like a different finger. Keep annotation
        # cells whole at the brace and viewport edges, without reflowing them.
        if rect.position.x < 30.0 or rect.end.x > score_layout.size.x:
            continue
        var active_hand: String = str(context.get("active_hand","both"))
        var selected: bool = active_hand == "both" or active_hand == str(item["hand"])
        var ink: Color = Design.SCORE_INK if selected else Color(Design.STAFF_MUTED,.46)
        if item["hand"] == "left":
            ink = ink.lerp(Design.BLUE,.32)
        var font_size: int = int(item["font_size"])
        canvas.draw_string(ThemeDB.fallback_font,rect.position+Vector2(1.0,ThemeDB.fallback_font.get_ascent(font_size)),
            str(item["finger"]),HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
        var shown: Dictionary = item.duplicate()
        shown["pass_index"] = pass_index
        shown["rect"] = rect
        shown["head"] = item["head"]+translation
        shown["ink_rect"] = Rect2(item["ink_rect"].position+translation,item["ink_rect"].size)
        drawn_fingerings.append(shown)


func fill_menu(menu: PopupMenu, event: Dictionary) -> void:
    var assignment: Dictionary = FingeringPlacement.assignment(event)
    menu.add_item(score_layout.performing_hand(event).capitalize()+" hand · fingering", 100)
    menu.set_item_disabled(0,true)
    for finger in range(1,6):
        menu.add_radio_check_item(str(finger),finger)
        menu.set_item_checked(menu.item_count-1,int(assignment.get("finger",0)) == finger)
    menu.add_separator()
    menu.add_item("Use original / automatic",0)
    menu.id_pressed.connect(func(finger: int):
        fingering_change_requested.emit(FingeringPlacement.source(event),null if finger == 0 else finger)
        fingering_popup.hide())


func open_editor(canvas, point: Vector2, gap: float, drawn_note_instances: Array) -> bool:
    if not fingering_annotations_enabled:
        return false
    var selected: Dictionary = {}
    var radius: float = maxf(12.0,gap*.8)
    for item in drawn_fingerings:
        if item["rect"].grow(5.0).has_point(point):
            for id in item["event_ids"]:
                selected[id] = true
    for instance in drawn_note_instances:
        if instance["position"].distance_to(point) <= radius:
            selected[instance["event_id"]] = true
    var targets: Array = []
    var sources: Dictionary = {}
    for id in selected:
        var event: Dictionary = score_layout.expression_note_index.get(str(id),{})
        var source: String = FingeringPlacement.source(event)
        if not bool(event.get("is_attack",false)) or source.is_empty() or sources.has(source):
            continue
        sources[source] = true
        targets.append(event)
    if targets.is_empty():
        return false
    if fingering_popup != null:
        fingering_popup.hide()
        fingering_popup.queue_free()
    fingering_popup = PopupMenu.new()
    canvas.add_child(fingering_popup)
    if targets.size() == 1:
        fill_menu(fingering_popup,targets[0])
    else:
        for i in range(targets.size()):
            var event: Dictionary = targets[i]
            var submenu := PopupMenu.new()
            submenu.name = "Note%d" % i
            fingering_popup.add_child(submenu)
            fill_menu(submenu,event)
            var pitch: Dictionary = event.get("spelling",{})
            fingering_popup.add_submenu_item("%s · voice %s · %s%s" % [
                score_layout.performing_hand(event).capitalize(),str(event.get("voice","1")),
                str(pitch.get("step","")),str(pitch.get("octave",""))],submenu.name)
    var screen: Vector2 = canvas.get_screen_transform()*point
    fingering_popup.popup(Rect2i(Vector2i(screen),Vector2i.ZERO))
    return true
