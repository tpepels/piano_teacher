extends RefCounted

# The practice score uses the real grand-staff geometry rather than a
# fixed zoom or the whitespace surrounding a rasterized Verovio page.
const MAX_PNG_WIDTH := 5200
const MIN_PNG_WIDTH := 2000
const MAX_PAGE_PIXELS := 10000000

static func staff_gap(viewport_height: float, lines: Array) -> float:
    if lines.size() < 2:
        return maxf(1.0, viewport_height * .055)
    var gap_fraction: float = absf(float(lines[1]) - float(lines[0]))
    var extent_fraction: float = absf(float(lines[-1]) - float(lines[0]))
    if gap_fraction < .000001 or extent_fraction < .000001:
        return maxf(1.0, viewport_height * .055)
    # On a large stage the staff grows with resolution. Preserve enough
    # room above and below the *entire* grand staff for ledger lines.
    var desired: float = clampf(viewport_height * .085, 26.0, 54.0)
    return minf(desired, viewport_height * .86 * gap_fraction / extent_fraction)


static func png_width(layout: Dictionary, viewport_height: float) -> int:
    var systems: Array = layout.get("systems", [])
    var widths: Array = layout.get("widths", [])
    var heights: Array = layout.get("heights", [])
    if systems.is_empty() or widths.is_empty() or heights.is_empty():
        return MIN_PNG_WIDTH
    var lines: Array = systems[0].get("staff_lines", [])
    if lines.size() < 2:
        return MIN_PNG_WIDTH
    var gap_fraction: float = absf(float(lines[1]) - float(lines[0]))
    var first_page: int = int(systems[0].get("page", 0))
    if first_page < 0 or first_page >= widths.size() or first_page >= heights.size():
        return MIN_PNG_WIDTH
    var aspect: float = float(heights[first_page]) / maxf(1.0, float(widths[first_page]))
    if gap_fraction <= .000001 or aspect <= .000001:
        return MIN_PNG_WIDTH
    # Rasterize ABOVE the actual requested staff pixel size, then let Godot
    # downsample instead of enlarging a fixed 2000px image into blurry ink.
    var requested: float = staff_gap(viewport_height, lines) * 1.18 / (
        gap_fraction * aspect)
    var tallest_aspect: float = aspect
    for i in range(mini(widths.size(), heights.size())):
        tallest_aspect = maxf(tallest_aspect,
            float(heights[i]) / maxf(1.0, float(widths[i])))
    # Keep the whole PNG bounded for long multi-page piano lessons.
    var safe_width: int = mini(MAX_PNG_WIDTH,
        maxi(MIN_PNG_WIDTH, int(floor(sqrt(float(MAX_PAGE_PIXELS) /
            maxf(.01, tallest_aspect))))))
    # Changing window size only changes the raster resolution in coarse
    # 200px steps. A normal camera frame never triggers a score reload.
    return clampi(int(ceil(requested / 200.0)) * 200,
        MIN_PNG_WIDTH, safe_width)
