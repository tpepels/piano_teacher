extends RefCounted

# C1-continuous, monotone camera projection between real engraved onsets.
# Verovio preserves the actual noteheads; this only smooths the velocity
# between timestamps. All MIDI onsets remain EXACTLY on the fixed playhead.
# Used for native one-system lessons, never to alter evaluation or timing.

static func _interval(points: Array, i: int) -> float:
    return float(points[i + 1].get("beat", 0.0)) - float(points[i].get("beat", 0.0))


static func _secant(points: Array, i: int) -> float:
    var duration: float = _interval(points, i)
    if duration <= .000001:
        return 0.0
    return maxf(0.0, (float(points[i + 1].get("x", 0.0))
        - float(points[i].get("x", 0.0))) / duration)


static func _slope(points: Array, at: int) -> float:
    if points.size() < 2:
        return 0.0
    var last: int = points.size() - 1
    if at <= 0:
        return _secant(points, 0)
    if at >= last:
        return _secant(points, last - 1)
    var before: float = _secant(points, at - 1)
    var after: float = _secant(points, at)
    if before <= .0 or after <= .0:
        return 0.0
    var h0: float = _interval(points, at - 1)
    var h1: float = _interval(points, at)
    if h0 <= .000001 or h1 <= .000001:
        return minf(before, after)
    # Weighted harmonic-mean derivative of a monotone cubic Hermite curve.
    # Unlike abrupt linear joins, both sides share exactly the same slope.
    var w0: float = 2.0 * h1 + h0
    var w1: float = h1 + 2.0 * h0
    return (w0 + w1) / (w0 / before + w1 / after)


static func position(points: Array, interval: int, beat: float) -> float:
    if points.is_empty():
        return 0.0
    if points.size() == 1:
        return float(points[0].get("x", 0.0))
    var at: int = clampi(interval, 0, points.size() - 2)
    var a: Dictionary = points[at]
    var b: Dictionary = points[at + 1]
    var h: float = _interval(points, at)
    if h <= .000001:
        return float(a.get("x", 0.0))
    var t: float = clampf((beat - float(a.get("beat", 0.0))) / h, 0.0, 1.0)
    var x0: float = float(a.get("x", 0.0))
    var x1: float = float(b.get("x", 0.0))
    var m0: float = _slope(points, at)
    var m1: float = _slope(points, at + 1)
    # Hermite basis exactly interpolates both onsets. The PCHIP slopes keep
    # it monotone, without moving noteheads or overshooting into next bar.
    return (2.0 * t * t * t - 3.0 * t * t + 1.0) * x0 + (
        t * t * t - 2.0 * t * t + t) * h * m0 + (
        -2.0 * t * t * t + 3.0 * t * t) * x1 + (
        t * t * t - t * t) * h * m1


static func velocity(points: Array, interval: int, beat: float) -> float:
    if points.size() < 2:
        return 0.0
    var at: int = clampi(interval, 0, points.size() - 2)
    var h: float = _interval(points, at)
    if h <= .000001:
        return 0.0
    var a: Dictionary = points[at]
    var b: Dictionary = points[at + 1]
    var t: float = clampf((beat - float(a.get("beat", 0.0))) / h, 0.0, 1.0)
    return maxf(0.0, (6.0 * t * t - 6.0 * t) * (
        float(a.get("x", 0.0)) - float(b.get("x", 0.0))) / h
        + (3.0 * t * t - 4.0 * t + 1.0) * _slope(points, at)
        + (3.0 * t * t - 2.0 * t) * _slope(points, at + 1))
