extends RefCounted

# Geometry-only elliptical notehead outlines. All positions originate in
# Verovio's real engraved noteheads, never guessed staff columns.
static func ellipse(center: Vector2, radius_x: float, radius_y: float,
        tilt: float = -0.27) -> PackedVector2Array:
    var points := PackedVector2Array()
    var xx: float = maxf(1.0, radius_x)
    var yy: float = maxf(1.0, radius_y)
    var c: float = cos(tilt)
    var s: float = sin(tilt)
    for index in range(33):
        var angle: float = TAU * float(index) / 32.0
        var x: float = cos(angle) * xx
        var y: float = sin(angle) * yy
        points.append(center + Vector2(c * x - s * y, s * x + c * y))
    return points

static func radii(staff_gap: float) -> Vector2:
    # A notehead is wider than it is tall. Never let huge fullscreen score
    # zoom turn a cue into a large circle painted across adjacent pitches.
    var gap: float = maxf(5.0, staff_gap)
    return Vector2(gap * 0.78, gap * 0.48)
