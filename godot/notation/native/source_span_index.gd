extends RefCounted
## Source-bound span interval index shared by every retained measure painter.
## Indexing changes WHICH original objects are examined, never their
## authentic geometry, source IDs, paint order or world positions.
var entries: Array = []
var prefix_end: Array[float] = []
var prepared := false

func add(begin: float, end: float, source, source_index: int) -> void:
    assert(not prepared)
    if is_finite(begin) and is_finite(end) and end >= begin:
        entries.append({"start":begin,"end":end,
            "item":source,"order":source_index})

func finish() -> void:
    entries.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        if absf(float(a["start"])-float(b["start"])) > .0000001:
            return float(a["start"]) < float(b["start"])
        return int(a["order"]) < int(b["order"]))
    prefix_end.clear()
    var max_end := -INF
    for entry in entries:
        max_end = maxf(max_end,float(entry["end"]))
        prefix_end.append(max_end)
    prepared = true

func query(left: float, right: float) -> Array:
    assert(prepared)
    if right < left:
        return []
    # Prefix maxima are monotonically increasing even with nested slurs.
    # A group that begins far before this measure but ends inside it MUST
    # survive the seek; binary-searching starts alone would lose that ink.
    var lo := 0
    var hi: int = entries.size()
    while lo < hi:
        var mid: int = (lo+hi)>>1
        if prefix_end[mid] < left:
            lo = mid+1
        else:
            hi = mid
    var chosen: Array = []
    for i in range(lo,entries.size()):
        var entry: Dictionary = entries[i]
        if float(entry["start"]) > right:
            break
        if float(entry["end"]) >= left:
            chosen.append(entry)
    chosen.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return int(a["order"]) < int(b["order"]))
    var result: Array = []
    for entry in chosen:
        result.append(entry["item"])
    return result
