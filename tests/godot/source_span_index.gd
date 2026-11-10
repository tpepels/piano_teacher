extends SceneTree
## Interval seek cannot lose an old long slur that overlaps a local window.
## It must return the exact exhaustive set in the original authoring order,
## never a generated or repositioned symbol.
const SourceSpanIndex := preload("res://notation/native/source_span_index.gd")
var failures := 0

func check(ok: bool,why: String) -> void:
    if not ok:
        failures += 1
        print("SOURCE_SPAN_INDEX_FAILED:",why)

func exhaustive(rows: Array, left: float, right: float) -> Array:
    var expected: Array = []
    for row in rows:
        if float(row["end"]) >= left and float(row["start"]) <= right:
            expected.append(row["object"])
    return expected

func _initialize() -> void:
    var data: Array = [
        {"start":0.0,"end":40.0,"object":"long_slur"},
        {"start":1.0,"end":1.5,"object":"short_note"},
        {"start":3.0,"end":6.0,"object":"beam"},
        {"start":6.0,"end":6.0,"object":"singleton_tuplet"},
        {"start":25.0,"end":26.0,"object":"late_fingering"},
        {"start":4.0,"end":8.0,"object":"nested_expression"}]
    var index = SourceSpanIndex.new()
    for position in range(data.size()):
        var item: Dictionary = data[position]
        index.add(item["start"],item["end"],item["object"],position)
    index.finish()
    for pair in [[-1.0,0.0],[1.0,2.0],[4.0,4.5],[6.0,6.0],
            [7.0,9.0],[19.0,20.0],[25.0,25.1],[41.0,50.0]]:
        check(index.query(pair[0],pair[1]) ==
            exhaustive(data,pair[0],pair[1]),
            "nested / straddling spans agree with exhaustive original paint order")
    var large = SourceSpanIndex.new()
    for i in range(10000):
        large.add(float(i),float(i)+.25,i,i)
    large.add(0.0,9999.0,"original_whole_page_slur",10000)
    large.finish()
    var visible: Array = large.query(5000.0,5000.5)
    check(visible == [5000,"original_whole_page_slur"],
        "long score seeks just the local source glyph and crossing original slur")
    check(large.query(11000.0,12000.0).is_empty(),
        "out-of-source windows never create phantom symbols")
    print("SOURCE_SPAN_INDEX_FAILURES:",failures)
    quit(0 if failures==0 else 1)
