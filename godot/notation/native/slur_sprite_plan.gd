extends RefCounted
## Authentic slur quad in immutable source coordinates. Only the score camera's
## horizontal translation and hand color are supplied to the drawing thread.

static func build(atlas, key: String, x0: float, y0: float, x1: float,
        y1: float, gap: float) -> PackedVector2Array:
    if not atlas.slur_textures.has(key) or x1 <= x0:
        return PackedVector2Array()
    var data: Dictionary = atlas.slur_metadata.get(key,{})
    var span: float = float(data.get("span",0.0))
    var bounds: Array = data.get("bounds",[])
    if span <= 0.0 or bounds.size()!=4:
        return PackedVector2Array()
    var unit: float = gap/250.0
    var change: float = (y1-y0)-float(data.get("original_end_y",0.0))*unit
    var left: float = x0+float(bounds[0])*(x1-x0)/span
    var right: float = x0+(float(bounds[0])+float(bounds[2]))*(x1-x0)/span
    var top: float = y0+float(bounds[1])*unit
    var bottom: float = top+float(bounds[3])*unit
    var y_left: float = change*float(bounds[0])/span
    var y_right: float = change*(float(bounds[0])+float(bounds[2]))/span
    return PackedVector2Array([
        Vector2(left,top+y_left),Vector2(right,top+y_right),
        Vector2(right,bottom+y_right),Vector2(left,bottom+y_left)])
