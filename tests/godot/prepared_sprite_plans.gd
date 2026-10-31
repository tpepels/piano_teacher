extends SceneTree
const Beams := preload("res://notation/native/beam_sprite_plan.gd")
const Slurs := preload("res://notation/native/slur_sprite_plan.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")
const SourceSpans := preload("res://notation/native/source_spans.gd")
const Layout := preload("res://notation/native/score_layout.gd")
const Axis := preload("res://notation/shared/timeline.gd")

func _initialize() -> void:
    var failures := 0
    var atlas := Glyphs.new()
    var pixels := Image.create(100,10,false,Image.FORMAT_RGBA8)
    pixels.fill(Color.WHITE)
    var texture := ImageTexture.create_from_image(pixels)
    atlas.beam_textures["fixture"] = texture
    atlas.beam_metadata["fixture"] = {
        "head_offsets":[10.0,50.0],"bounds":[0.0,0.0,100.0,10.0]}
    var regions: Array = Beams.build(atlas,"fixture",[50.0,150.0],
        200.0,20.0,[10.0,50.0])
    if regions.size()!=3:
        failures += 1
    else:
        # Authentic source interpolator, both end caps, no frame origin.
        if regions[0]["dest"] != Rect2(50,200,100,.8) or \
                regions[0]["source"] != Rect2(10,0,40,10):
            failures += 1
        if regions[1]["source"] != Rect2(0,0,10,10) or \
                absf(float(regions[1]["dest"].size.x)-.8)>.00001:
            failures += 1
        if regions[2]["source"] != Rect2(50,0,50,10) or \
                absf(float(regions[2]["dest"].size.x)-4.0)>.00001:
            failures += 1
    if not Beams.build(atlas,"missing",[0,10],0.0,20.0,[]).is_empty():
        failures += 1
    if not Beams.build(atlas,"fixture",[50,40],0.0,20.0,[10,50]).is_empty():
        failures += 1
    atlas.slur_textures["arc"] = texture
    atlas.slur_metadata["arc"] = {
        "span":100.0,"bounds":[10.0,-20.0,80.0,12.0],
        "original_end_y":0.0}
    var quad: PackedVector2Array = Slurs.build(
        atlas,"arc",100.0,200.0,300.0,220.0,20.0)
    if quad.size()!=4:
        failures += 1
    else:
        # Source mask is stretched horizontally and sheared to pitch y,
        # once. The same quad is translated for every animation frame.
        if (quad[0]-Vector2(120,200.4)).length()>.00001 or \
                (quad[1]-Vector2(280,216.4)).length()>.00001 or \
                (quad[2]-Vector2(280,217.36)).length()>.00001:
            failures += 1
    if not Slurs.build(atlas,"missing",0,0,200,0,20).is_empty():
        failures += 1
    var layout := Layout.new(Axis.new(),atlas)
    var directions: Array = [
        {"kind":"hairpin","value":"crescendo","number":"1",
            "hand":"left","beat":1.0},
        {"kind":"hairpin","value":"stop","number":"1",
            "hand":"left","beat":4.0},
        {"kind":"hairpin","value":"diminuendo","number":"2",
            "hand":"right","beat":5.0},
        {"kind":"hairpin","value":"stop","number":"2",
            "hand":"right","beat":7.0}
    ]
    var spans: Array = SourceSpans.hairpins(directions,layout)
    if spans.size()!=2 or spans[0]["begin"]!=1.0 or \
            spans[0]["end"]!=4.0 or spans[0]["hand"]!="left" or \
            spans[1]["begin"]!=5.0 or spans[1]["end"]!=7.0:
        failures += 1
    var measures: Array = [
        {"start_beat":0.0,"end_beat":4.0,
            "left_barline":{"ending":{"number":"1","type":"start"}}},
        {"start_beat":4.0,"end_beat":8.0,
            "right_barline":{"ending":{"number":"1","type":"stop"}}},
        {"start_beat":8.0,"end_beat":12.0,
            "left_barline":{"ending":{"number":"2","type":"start"}}}
    ]
    var endings: Array = SourceSpans.voltas(measures,12.0)
    if endings.size()!=2 or endings[0]["start"]!=0.0 or \
            endings[0]["end"]!=8.0 or not endings[0]["closed"] or \
            endings[1]["start"]!=8.0 or endings[1]["end"]!=12.0 or \
            endings[1]["closed"]:
        failures += 1
    print("PREPARED_SPRITE_PLAN_FAILURES:",failures)
    quit(0 if failures==0 else 1)
