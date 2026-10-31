extends RefCounted
## Resolve authored expression/barline pairs once per loaded source.
## No viewport, canvas, transport, or playback state is stored here.

static func hairpins(expressions: Array, score_layout) -> Array:
    var pending: Dictionary = {}
    var result: Array = []
    for mark in expressions:
        if str(mark.get("kind","")) != "hairpin":
            continue
        var staff: String = score_layout.display_staff(mark)
        var key: String = staff+"|"+str(mark.get("number","1"))
        var direction: String = str(mark.get("value",""))
        if direction in ["crescendo","diminuendo"]:
            pending[key] = mark
        elif direction == "stop" and pending.has(key):
            var first: Dictionary = pending[key]
            pending.erase(key)
            var begin: float = float(first.get("beat",0.0))
            var end: float = float(mark.get("beat",0.0))
            if end > begin:
                result.append({"first":first,"last":mark,
                    "begin":begin,"end":end,"hand":staff})
    return result

static func voltas(measures: Array, duration: float) -> Array:
    var pending: Dictionary = {}
    var result: Array = []
    for measure in measures:
        for location in ["left","right"]:
            var mark: Variant = measure.get(location+"_barline")
            if not mark is Dictionary:
                continue
            var ending: Variant = mark.get("ending")
            if not ending is Dictionary:
                continue
            var number: String = str(ending.get("number",""))
            var kind: String = str(ending.get("type",""))
            var beat: float = float(measure.get(
                "start_beat" if location == "left" else "end_beat",0.0))
            if kind == "start":
                pending[number] = beat
            elif kind in ["stop","discontinue"] and pending.has(number):
                result.append({"start":float(pending[number]),
                    "end":beat,"number":number,"closed":kind == "stop"})
                pending.erase(number)
    for number in pending:
        result.append({"start":float(pending[number]),"end":duration,
            "number":str(number),"closed":false})
    return result
