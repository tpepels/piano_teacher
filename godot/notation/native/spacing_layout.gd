extends RefCounted
# Collision geometry is read from the ORIGINAL Verovio alpha masks. These
# rectangles are a conservative occupancy index, never replacement artwork.
const CELL := .10
const CLEARANCE := .12
var profiles: Dictionary = {}

func components(texture: Texture2D, bounds: Array, centered: bool = false) -> Array:
    var key: String = str(texture.get_instance_id())+str(centered)
    if profiles.has(key):
        return profiles[key]
    var image: Image = texture.get_image()
    var width: int = image.get_width()
    var height: int = image.get_height()
    var unit_x: float = float(bounds[2])/250.0/float(width)
    var unit_y: float = float(bounds[3])/250.0/float(height)
    var origin_x: float = -float(bounds[2])/500.0 if centered else float(bounds[0])/250.0
    var origin_y: float = float(bounds[1])/250.0
    var cells: Dictionary = {}
    for y in range(height):
        for x in range(width):
            if image.get_pixel(x,y).a <= 0.0:
                continue
            var left: int = floori((origin_x+float(x)*unit_x)/CELL)
            var right: int = ceili((origin_x+float(x+1)*unit_x)/CELL)-1
            var top: int = floori((origin_y+float(y)*unit_y)/CELL)
            var bottom: int = ceili((origin_y+float(y+1)*unit_y)/CELL)-1
            for row in range(top,bottom+1):
                if not cells.has(row):
                    cells[row] = {}
                for col in range(left,right+1):
                    cells[row][col] = true
    var output: Array = []
    var rows: Array = cells.keys()
    rows.sort()
    var active: Dictionary = {}
    for row in rows:
        var columns: Array = cells[row].keys()
        columns.sort()
        var start: int = int(columns[0])
        var last: int = start
        var runs: Array = []
        for i in range(1,columns.size()):
            var col: int = int(columns[i])
            if col != last+1:
                runs.append(Vector2i(start,last+1))
                start = col
            last = col
        runs.append(Vector2i(start,last+1))
        var next: Dictionary = {}
        for run in runs:
            var run_key: String = str(run.x)+":"+str(run.y)
            if active.has(run_key) and absf(output[active[run_key]].end.y-float(row)*CELL)<.0001:
                var rect: Rect2 = output[active[run_key]]
                rect.size.y += CELL
                output[active[run_key]] = rect
                next[run_key] = active[run_key]
            else:
                next[run_key] = output.size()
                output.append(Rect2(float(run.x)*CELL,float(row)*CELL,
                    float(run.y-run.x)*CELL,CELL))
        active = next
    profiles[key] = output
    return output


static func footprint(parts: Array) -> Rect2:
    var result := Rect2()
    for part in parts:
        result = part if not result.has_area() else result.merge(part)
    return result


static func translated(parts: Array, offset: Vector2) -> Array:
    var output: Array = []
    for part in parts:
        output.append(Rect2(part.position+offset,part.size))
    return output


static func separation(first: Array, last: Array) -> float:
    var result := -INF
    for a in first:
        for b in last:
            if b.position.y >= a.end.y+CLEARANCE or a.position.y >= b.end.y+CLEARANCE:
                continue
            result = maxf(result,a.end.x-b.position.x+CLEARANCE)
    return result


static func solve(groups: Array, gap: float, density: float) -> Dictionary:
    # Difference constraints on rigid original sprites: x[j]-x[i] >= need.
    # Lower/upper bounds include EVERY source-displaced chord head. A failed
    # constraint is reported, never hidden with clipping or dropped ink.
    var shifts: Array[float] = []
    var edges: Array = []
    var low: Array[float] = []
    var high: Array[float] = []
    for group in groups:
        low.append(-2.0-float(group.get("min_head",0.0)))
        high.append(2.0-float(group.get("max_head",0.0)))
        shifts.append(low[-1])
        edges.append([])
    for j in range(groups.size()):
        var current: Dictionary = groups[j]
        for i in range(j-1,-1,-1):
            var previous: Dictionary = groups[i]
            var distance: float = (float(current["beat"])-float(previous["beat"]))*density/gap
            # All rigid source footprints (heads, stems, flags and dots) enter
            # the sweep reach. No assumption that adjacent heads bound ink.
            if distance > float(current["sweep_reach"]):
                break
            if str(current["staff"]) != str(previous["staff"]):
                continue
            var needed: float = separation(previous["parts"],current["parts"])-distance
            if not is_finite(needed) or needed <= low[j]-high[i]:
                continue
            edges[j].append({"from":i,"need":needed})
            shifts[j] = maxf(shifts[j],shifts[i]+needed)
        if shifts[j] > high[j]+.00001:
            var blockers: Array = []
            for edge in edges[j]:
                var i: int = int(edge["from"])
                if shifts[i]+float(edge["need"]) > high[j]+.00001:
                    blockers.append({"id":groups[i]["id"],"beat":groups[i]["beat"],
                        "shift":shifts[i],"need":edge["need"]})
            return {"ok":false,"reason":"Bounded source ink collision at "+str(current["id"])+
                " beat="+str(current["beat"])+" shift="+str(shifts[j])+" upper="+str(high[j])+" blockers="+str(blockers)}
    # Prefer the unchanged source placement wherever possible. Project back
    # from the right, retaining the already-proven feasible ordering.
    for j in range(groups.size()-1,-1,-1):
        shifts[j] = maxf(shifts[j],minf(0.0,high[j]))
        for edge in edges[j]:
            var i: int = int(edge["from"])
            high[i] = minf(high[i],shifts[j]-float(edge["need"]))
    var output: Dictionary = {}
    for i in range(groups.size()):
        output[str(groups[i]["id"])] = shifts[i]
    return {"ok":true,"shifts":output,"edges":edges}
