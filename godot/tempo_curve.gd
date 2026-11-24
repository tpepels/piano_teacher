extends RefCounted
## Exact beat <-> time for one tempo span, constant or eased (half-cosine
## speed change). The same closed forms as piano_teacher/application/
## tempo_curve.py, so the scrolling bar, clicks and grading agree:
##   t(u) = 120 L / (pi sqrt(v0 v1)) * atan(sqrt(v1/v0) * tan(pi u / 2))
##   u(t) = (2/pi) * atan(tan(theta) / sqrt(v1/v0)),
##          theta = pi t sqrt(v0 v1) / (120 L)

static func is_constant(v0: float, v1: float) -> bool:
	return absf(v1-v0) < 1e-9

static func bpm_at(beat: float, length: float, v0: float, v1: float) -> float:
	if is_constant(v0, v1) or length <= 0.0:
		return v0
	var u := clampf(beat/length, 0.0, 1.0)
	return v0 + (v1-v0)*(1.0-cos(PI*u))/2.0

static func seconds_at(beat: float, length: float, v0: float, v1: float) -> float:
	beat = clampf(beat, 0.0, maxf(0.0, length))
	if is_constant(v0, v1) or length <= 0.0:
		return 60.0*beat/v0
	var u := beat/length
	if u >= 1.0:
		return 60.0*length/sqrt(v0*v1)
	return 120.0*length/(PI*sqrt(v0*v1))*atan(sqrt(v1/v0)*tan(PI*u/2.0))

static func beat_at(seconds: float, length: float, v0: float, v1: float) -> float:
	if seconds <= 0.0:
		return 0.0
	if seconds >= seconds_at(length, length, v0, v1):
		return length
	if is_constant(v0, v1):
		return seconds*v0/60.0
	var theta := PI*seconds*sqrt(v0*v1)/(120.0*length)
	return (2.0/PI)*atan(tan(theta)/sqrt(v1/v0))*length
