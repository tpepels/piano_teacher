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

# Expand blank horizontal space whenever possible. Stretching a Verovio
# raster interval used to elongate *rest glyphs, accidentals, beams and tied
# noteheads*, particularly at slow tempo. A safe split contains only staff
# rules (repainted by StaffContinuity) or transparency; all other source
# columns are copied at their original width.
static func _clean_gap(image: Image, source_a: int, source_b: int,
        staff_rows: Array, ink: PackedByteArray) -> int:
    var span: int = source_b - source_a
    if span < 8:
        return -1
    var center: int = (source_a + source_b) / 2
    var left: int = source_a + maxi(2, int(span * .16))
    var right: int = source_b - maxi(2, int(span * .16))
    var height: int = image.get_height()
    if left >= right or height <= 0:
        return -1
    var excluded := PackedByteArray()
    excluded.resize(height)
    for row in staff_rows:
        var center_y: int = int(row)
        for y in range(maxi(0, center_y-3), mini(height, center_y+4)):
            excluded[y] = 1
    var width: int = image.get_width()
    # Search from the interval's centre outwards so note spacing remains
    # visually balanced. Reject a cut intersecting any non-staff glyph.
    for offset in range(span / 2 + 1):
        for sign in [-1, 1]:
            var x: int = center + sign * offset
            if x < left or x >= right:
                continue
            var safe := true
            for y in range(0, height, 2):
                if excluded[y] != 0:
                    continue
                var at: int = (y * width + x) * 4
                if ink[at+3] > 40 and (ink[at] < 235 or
                        ink[at+1] < 235 or ink[at+2] < 235):
                    safe = false
                    break
            if safe:
                return x
    return -1


static func warp_image(image: Image, points: Array,
        staff_rows: Array = []) -> Image:
    if points.size() < 2:
        return image
    var target_width: int = roundi(float(points[-1].y))
    if target_width == image.get_width():
        return image
    if target_width < image.get_width() or target_width > 16384:
        return image # Never compress music or create an oversized GPU tile.
    # PNG page decoders may return RGB8 or RGBA8. The gap classifier indexes
    # exactly four channels, so normalize format before examining source ink.
    if image.get_format() != Image.FORMAT_RGBA8:
        image.convert(Image.FORMAT_RGBA8)
    var out := Image.create(target_width, image.get_height(), false, image.get_format())
    out.fill(Color.TRANSPARENT)
    # One immutable CPU copy per tile, not a multi-megabyte allocation for
    # every interval between consecutive noteheads.
    var source_pixels: PackedByteArray = image.get_data()
    for index in range(points.size() - 1):
        var left: Vector2 = points[index]
        var right: Vector2 = points[index+1]
        var source_a: int = clampi(roundi(left.x), 0, image.get_width())
        var source_b: int = clampi(roundi(right.x), 0, image.get_width())
        var dest_a: int = clampi(roundi(left.y), 0, target_width)
        var dest_b: int = clampi(roundi(right.y), 0, target_width)
        if source_b <= source_a or dest_b <= dest_a:
            continue
        var original_width: int = source_b-source_a
        var target_span: int = dest_b-dest_a
        if target_span >= original_width:
            var cut: int = _clean_gap(image, source_a, source_b, staff_rows,
                source_pixels) if target_span > original_width else -1
            if cut >= 0:
                # Exact unscaled Verovio pixels on BOTH sides. The inserted
                # transparent interval gains continuous lines from the
                # independent staff layer and cannot smear musical symbols.
                var left_width: int = cut-source_a
                var right_width: int = source_b-cut
                out.blit_rect(image, Rect2i(source_a,0,left_width,
                    image.get_height()), Vector2i(dest_a,0))
                out.blit_rect(image, Rect2i(cut,0,right_width,
                    image.get_height()), Vector2i(dest_b-right_width,0))
            elif original_width == target_span:
                out.blit_rect(image, Rect2i(source_a,0,original_width,
                    image.get_height()), Vector2i(dest_a,0))
            else:
                # A tie or beam crosses every possible cut. Preserve its
                # connectivity rather than severing the actual notation.
                var region := image.get_region(Rect2i(source_a,0,
                    original_width,image.get_height()))
                region.resize(target_span,image.get_height(),
                    Image.INTERPOLATE_BILINEAR)
                out.blit_rect(region,Rect2i(0,0,target_span,
                    image.get_height()),Vector2i(dest_a,0))
        else:
            var region := image.get_region(Rect2i(source_a,0,
                original_width,image.get_height()))
            region.resize(target_span,image.get_height(),
                Image.INTERPOLATE_BILINEAR)
            out.blit_rect(region,Rect2i(0,0,target_span,
                image.get_height()),Vector2i(dest_a,0))
    return out
