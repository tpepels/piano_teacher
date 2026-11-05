extends RefCounted
## Approximate traditional tempo names for the CURRENT exercise BPM.
## These labels are descriptive, not changes to the score's own tempo text.
## Historical markings do not have universal numerical boundaries.
const BANDS: Array = [
    [40, "Grave"],
    [60, "Largo"],
    [66, "Larghetto"],
    [76, "Adagio"],
    [108, "Andante"],
    [120, "Moderato"],
    [168, "Allegro"],
    [200, "Presto"],
]

static func name_for_bpm(bpm: float) -> String:
    if not is_finite(bpm) or bpm <= 0.0:
        return "Tempo"
    for band in BANDS:
        if bpm < float(band[0]):
            return str(band[1])
    return "Prestissimo"

static func display(bpm: float) -> String:
    if not is_finite(bpm) or bpm <= 0.0:
        return "-- BPM"
    return "%s · %d BPM" % [name_for_bpm(bpm),roundi(bpm)]
