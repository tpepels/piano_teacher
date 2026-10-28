extends RefCounted
# Pure polyphonic rest collision placement. The renderer supplies the real
# source-symbol ink at zero staff-lane shift; shifting that rectangle changes
# visual layout only, never source beats, MIDI attacks or note identities.

static func candidate_offsets(voice: String, voices: Array,
        note_type: String) -> Array:
    var preferred := 0.0
    var direction := -1.0
    if voices.size() > 1:
        var index: int = voices.find(voice)
        direction = -1.0 if index % 2 == 0 else 1.0
        preferred = direction*(1.0+floorf(float(index)/2.0))
    var offsets: Array = [preferred]
    # Moving half/whole rests by half a staff space changes their meaning.
    var step_size := 1.0 if note_type in ["whole","half"] else .5
    for step in range(1,15):
        offsets.append(preferred+direction*float(step)*step_size)
        offsets.append(preferred-direction*float(step)*step_size)
    return offsets


static func place_rest(base_rect: Rect2, voice: String, voices: Array,
        note_type: String, gap: float, obstacles: Array) -> Dictionary:
    var offsets: Array = candidate_offsets(voice,voices,note_type)
    var preferred: float = float(offsets[0])
    var best_score := INF
    var best_shift := preferred
    var best_rect := Rect2()
    for candidate in offsets:
        var shift: float = float(candidate)
        var rect := Rect2(base_rect.position+Vector2(0.0,gap*shift),
            base_rect.size)
        var overlap_area := 0.0
        for blocker in obstacles:
            if str(blocker["voice"]) == voice:
                continue
            var other: Rect2 = blocker["ink"]
            if rect.intersects(other.grow(gap*.06)):
                var overlap: Rect2 = rect.intersection(other.grow(gap*.06))
                overlap_area += overlap.size.x*overlap.size.y
        var score: float = overlap_area+absf(shift-preferred)*gap*gap*.02
        if score < best_score:
            best_score = score
            best_shift = shift
            best_rect = rect
        if overlap_area <= .00001:
            return {"shift":shift,"ink":rect,"placed":true}
    # When crowded voices force a collision, preserve minimum overlap rather
    # than hiding source notation or falling back to incorrect raster ink.
    return {"shift":best_shift,"ink":best_rect,"placed":false}
