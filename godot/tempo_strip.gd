extends RefCounted

# Time-proportional score spacing. Images are rearranged horizontally once
# when engraving is loaded, never on each frame. Protect a native-width
# interval around every Verovio event so noteheads and accidentals retain
# their original size. Only the gaps between event cores are stretched.
# The horizontal staff itself is owned by StaffContinuity.
static func project(source_x: float, points: Array) -> float:
    if points.is_empty():
        return source_x
    for index in range(points.size() - 1):
        var a: Vector2 = points[index]
        var b: Vector2 = points[index + 1]
        if source_x <= b.x:
            var span: float = b.x - a.x
            if span < .00001:
                return b.y
            return lerpf(a.y, b.y, clampf((source_x-a.x)/span, 0.0, 1.0))
    var last: Vector2 = points[-1]
    return last.y + maxf(0.0, source_x-last.x)

static func controls(source_positions: Array, target_positions: Array,
        native_width: int, staff_gap: float) -> Array:
    if source_positions.size() != target_positions.size() or source_positions.is_empty():
        return []
    var count: int = source_positions.size()
    var final_width: int = maxi(native_width, roundi(native_width +
        float(target_positions[-1]) - float(source_positions[-1])))
    var points: Array = [Vector2(0,0)]
    for index in range(count):
        var x: float = float(source_positions[index])
        var destination: float = float(target_positions[index])
        var span_left: float = minf(x, destination)
        var span_right: float = minf(native_width-x, final_width-destination)
        if index > 0:
            span_left = minf(span_left, .42 * minf(
                x-float(source_positions[index-1]),
                destination-float(target_positions[index-1])))
        if index+1 < count:
            span_right = minf(span_right, .42 * minf(
                float(source_positions[index+1])-x,
                float(target_positions[index+1])-destination))
        var left_guard: float = maxf(0.0, minf(staff_gap * 1.1, span_left))
        var right_guard: float = maxf(0.0, minf(staff_gap * .7, span_right))
        var left := Vector2(x-left_guard, destination-left_guard)
        var right := Vector2(x+right_guard, destination+right_guard)
        if left.x >= points[-1].x and left.y >= points[-1].y:
            points.append(left)
        if right.x >= points[-1].x and right.y >= points[-1].y:
            points.append(right)
    points.append(Vector2(native_width, final_width))
    return points

static func warp_image(image: Image, points: Array) -> Image:
    if points.size() < 2:
        return image
    var target_width: int = roundi(float(points[-1].y))
    if target_width == image.get_width():
        return image
    if target_width < image.get_width() or target_width > 16384:
        return image # Never compress music or create an oversized GPU tile.
    var out := Image.create(target_width, image.get_height(), false, image.get_format())
    out.fill(Color.TRANSPARENT)
    for index in range(points.size() - 1):
        var left: Vector2 = points[index]
        var right: Vector2 = points[index+1]
        var source_a: int = clampi(roundi(left.x), 0, image.get_width())
        var source_b: int = clampi(roundi(right.x), 0, image.get_width())
        var dest_a: int = clampi(roundi(left.y), 0, target_width)
        var dest_b: int = clampi(roundi(right.y), 0, target_width)
        if source_b <= source_a or dest_b <= dest_a:
            continue
        var region := image.get_region(Rect2i(source_a,0,
            source_b-source_a,image.get_height()))
        if dest_b-dest_a != source_b-source_a:
            # Staff lines are handled separately. Continuous beams and ties
            # can stretch between intact noteheads without breaking.
            region.resize(dest_b-dest_a, image.get_height(),
                Image.INTERPOLATE_BILINEAR)
        out.blit_rect(region, Rect2i(0,0,region.get_width(),
            region.get_height()), Vector2i(dest_a,0))
    return out
