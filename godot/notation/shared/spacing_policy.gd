extends RefCounted
## Shared, score-wide horizontal-spacing defaults. No tempo, grading or
## transport ownership. Physical ink collision checks may raise the selected
## density for a specific score; neither note beats nor measure beats move.
##
## Change DEFAULT_PIXELS_PER_BEAT to widen/narrow ordinary measures on the
## NEXT loaded score. A running score's selected density is immutable.
const DEFAULT_PIXELS_PER_BEAT := 96.0
const MAX_STAFF_GAP := 22.0
const MIN_READABLE_STAFF_GAP := 14.0
# Reserve the same minimum visible reading horizon during viewport fitting
# and new-source admission. These must not silently diverge.
const MIN_LOOKAHEAD_BEATS := 3.0
