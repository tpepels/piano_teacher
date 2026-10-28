extends RefCounted
# Source-independent spatial packing of fingering labels. The native view
# owns the actual Verovio glyph obstacles and source note locations; this
# component only deduplicates placement candidates and resolves collisions.
const FingeringPlacement := preload("res://notation/native/fingering_placement.gd")

static func block(rect: Rect2, bins: Dictionary, cell: float) -> void:
    for column in range(floori(rect.position.x/cell), floori(rect.end.x/cell)+1):
        if not bins.has(column):
            bins[column] = []
        bins[column].append(rect)

static func is_clear(rect: Rect2, bins: Dictionary, cell: float,
        staff_lines: Array, viewport_height: float) -> bool:
    if rect.position.y < 4.0 or rect.end.y > viewport_height-4.0:
        return false
    for line in staff_lines:
        if rect.grow(.5).intersects(line):
            return false
    for column in range(floori((rect.position.x-3.0)/cell),
            floori((rect.end.x+3.0)/cell)+1):
        for other in bins.get(column, []):
            if rect.grow(3.0).intersects(other):
                return false
    return true

static func pack(candidates: Array, metrics: Dictionary, gap: float,
        viewport_height: float, cell: float, bins: Dictionary,
        staff_lines: Array, font_size: int) -> Dictionary:
    # Retain source order within a beat, right-hand staff orientation and
    # independent physical note identities exactly as the original painter.
    candidates.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        var ea: Dictionary = a["event"]
        var eb: Dictionary = b["event"]
        if absf(float(ea["beat"])-float(eb["beat"])) > .000001:
            return float(ea["beat"]) < float(eb["beat"])
        if a["assignment"]["hand"] != b["assignment"]["hand"]:
            return a["assignment"]["hand"] < b["assignment"]["hand"]
        var ya: float = (a["head"] as Vector2).y
        var yb: float = (b["head"] as Vector2).y
        if absf(ya-yb)<.001:
            return str(ea.get("source_id",ea["id"]))<str(eb.get("source_id",eb["id"]))
        return ya > yb if a["assignment"]["hand"] == "right" else ya < yb)
    var layout: Array = []
    var issues: Array = []
    var extent: Vector2 = metrics["cell"]
    var ink_offset: Vector2 = metrics["ink_offset"]
    var ink_size: Vector2 = metrics["ink_size"]
    for item in candidates:
        var assignment: Dictionary = item["assignment"]
        var hand: String = assignment["hand"]
        var head: Vector2 = item["head"]
        var up: bool = bool(item["up"])
        var direction: float = float(item["direction"])
        var chord: bool = bool(item["chord"])
        var hint: Dictionary = assignment.get("placement",{}) if assignment.get("placement") is Dictionary else {}
        var placed := false
        for local_search in [false,true]:
            if placed:
                break
            var positions: Array = FingeringPlacement.fallback_candidates(head,ink_size,gap,direction,up) if local_search else \
                FingeringPlacement.candidates(head,ink_size,gap,direction,chord,up,float(item["staff_center"]),hint)
            for candidate in positions:
                var ink_rect := Rect2(candidate["position"],ink_size)
                var rect := Rect2(ink_rect.position-ink_offset,extent)
                if rect.position.y < 0.0 or rect.end.y > viewport_height or not is_clear(
                        ink_rect,bins,cell,staff_lines,viewport_height):
                    continue
                layout.append({"rect":rect,"ink_rect":ink_rect,"head":head,
                    "finger":int(assignment["finger"]), "hand":hand,
                    "event_ids":item["event_ids"],"orientation":candidate["orientation"],
                    "font_size":font_size,"text_offset_x":1.0})
                block(ink_rect,bins,cell)
                placed = true
                break
        if not placed:
            issues.append({"source_id":str(assignment["source_id"]),
                "event_ids":item["event_ids"],
                "reason":"No local fingering position clears the musical ink"})
    return {"layout":layout,"issues":issues}
