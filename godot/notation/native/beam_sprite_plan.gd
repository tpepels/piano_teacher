extends RefCounted
## Immutable source-space beam mask slices. Prepared once for a score revision.
## A moving camera only supplies an X translation when painting these rectangles.
## This is exactly the original Verovio beam sampling, without per-frame
## interpolation, texture inspection, or mask geometry allocation.

static func build(atlas, art_key: String, anchors: Array, y0: float,
        gap: float, source_offsets: Array) -> Array:
    var texture: Texture2D = atlas.beam_textures.get(art_key)
    if texture == null or anchors.size() < 2:
        return []
    var metadata: Dictionary = atlas.beam_metadata.get(art_key,{})
    var offsets: Array = source_offsets if not source_offsets.is_empty() else         metadata.get("head_offsets", [])
    if offsets.size() != anchors.size():
        return []
    var bounds: Array = metadata.get("bounds", [])
    if bounds.size() != 4 or float(bounds[2]) <= 0.0:
        return []
    var width: float = float(bounds[2])
    var tw: float = float(texture.get_width())
    var th: float = float(texture.get_height())
    var scale: float = tw/width
    var top: float = y0+float(bounds[1])*gap/250.0
    var height: float = float(bounds[3])*gap/250.0
    var positions: Array = []
    for offset in offsets:
        positions.append((float(offset)-float(bounds[0]))*scale)
    var regions: Array = []
    for i in range(anchors.size()-1):
        var src0: float = float(positions[i])
        var src1: float = float(positions[i+1])
        var dst0: float = float(anchors[i])
        var dst1: float = float(anchors[i+1])
        if src1 <= src0+.01 or dst1 <= dst0:
            return []
        var a: float = clampf(src0,0.0,tw)
        var b: float = clampf(src1,0.0,tw)
        if b <= a:
            continue
        var x0: float = lerpf(dst0,dst1,(a-src0)/(src1-src0))
        var x1: float = lerpf(dst0,dst1,(b-src0)/(src1-src0))
        regions.append({"dest":Rect2(x0,top,x1-x0,height),
            "source":Rect2(a,0.0,b-a,th)})
    var left: float = clampf(float(positions[0]),0.0,tw)
    if left > .01:
        var cap_width: float = left*gap*width/(250.0*tw)
        regions.append({"dest":Rect2(float(anchors[0])-cap_width,top,cap_width,height),
            "source":Rect2(0.0,0.0,left,th)})
    var right: float = clampf(float(positions[-1]),0.0,tw)
    if right < tw-.01:
        var cap_width: float = (tw-right)*gap*width/(250.0*tw)
        regions.append({"dest":Rect2(float(anchors[-1]),top,cap_width,height),
            "source":Rect2(right,0.0,tw-right,th)})
    return regions
