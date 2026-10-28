extends SceneTree
# Hand-computed coordinates catch drift in the source axis, glyph offsets,
# clipping, performer tint, recovery visibility and actual head edit metadata.
const Layout := preload("res://notation/native/score_layout.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Connectors := preload("res://notation/native/connector_geometry.gd")
const Design := preload("res://practice_theme.gd")

# A recording drawing boundary deliberately has no view/transport/query API.
class Canvas:
    extends RefCounted
    var lines: Array = []
    var textures: Array = []
    var strings: Array = []
    func draw_line(a, b, ink, width, aa = false) -> void:
        lines.append([a,b,ink,width,aa])
    func draw_texture_rect(texture, rect, tiled, ink) -> void:
        textures.append([texture,rect,tiled,ink])
    func draw_string(font, at, text, alignment, width, font_size, ink) -> void:
        strings.append([at,text,font_size,ink])

# Only the rendering boundary is replaced: real score/connector policies run.
# Capture musical anchors at the glyph API, before the existing atlas projects
# them into texture rectangles (whose implementation is not changed here).
class Atlas:
    extends RefCounted
    var bounds := {"head_black":[-50,-50,100,100],"head_half":[-50,-50,100,100],
        "repeat_dot":[-10,-10,20,20]}
    var textures := {"clef_g_8va":true}
    var chord_metadata: Dictionary = {}
    var chord_stem_bounds: Dictionary = {}
    var note_stem_bounds := {"quarter_up":[40,-500,10,500]}
    var beam_metadata: Dictionary = {}
    var tie_metadata := {"up":{"bounds":[50,30,400,40],"span":500,"head_centers":[0,0],"head_widths":[100,100]},
        "down":{"bounds":[50,30,400,40],"span":500,"head_centers":[0,0],"head_widths":[100,100]}}
    var tie_textures: Dictionary = {}
    var calls: Array = []
    func paint(_canvas, name, x, y, gap, ink, centered = false) -> bool:
        calls.append([name,Vector2(x,y),gap,ink,centered])
        return true
    func paint_note(_canvas, kind, up, x, y, gap, ink) -> bool:
        calls.append(["note:"+kind,Vector2(x,y),gap,ink,up])
        return true
    func has_chord(key) -> bool:
        return chord_metadata.has(key)
    func has_chord_heads(key) -> bool:
        return chord_metadata.has(key)
    func has_chord_stem(key) -> bool:
        return chord_metadata.has(key)
    func chord_heads(key) -> Array:
        return chord_metadata.get(key,{}).get("head_positions",[])
    func paint_chord(_canvas, key, x, y, gap, ink) -> bool:
        calls.append(["chord:"+key,Vector2(x,y),gap,ink])
        return true
    func paint_chord_heads(_canvas, key, x, y, gap, ink) -> bool:
        calls.append(["heads:"+key,Vector2(x,y),gap,ink])
        return true
    func paint_chord_stem(_canvas, key, x, y, tip, gap, ink) -> bool:
        calls.append(["chord_stem:"+key,Vector2(x,y),gap,ink,tip])
        return true
    func paint_note_stem(_canvas, kind, up, x, y, tip, gap, ink) -> bool:
        calls.append(["stem:"+kind,Vector2(x,y),gap,ink,tip,up])
        return true
    func beam_tips(key) -> Array:
        return beam_metadata.get(key,{}).get("tip_offsets",[])
    func paint_beam(_canvas, key, anchors, y, gap, ink, offsets = []) -> bool:
        calls.append(["beam:"+key,anchors,y,gap,ink,offsets])
        return true
    func paint_tuplet(_canvas, key, x0, x1, y, gap, ink) -> bool:
        calls.append(["tuplet:"+key,Vector2(x0,y),x1,gap,ink])
        return true
    func paint_slur(_canvas, key, x0, y0, x1, y1, gap, ink) -> bool:
        calls.append(["slur:"+key,Vector2(x0,y0),Vector2(x1,y1),gap,ink])
        return true

class ActualCanvas:
    extends Node2D
    var symbols
    var context
    var frame
    var event: Dictionary
    var painted := false
    func _draw() -> void:
        symbols.paint_note(self,frame,event,100.0,20.0,Design.SCORE_INK)
        symbols.paint_rest(self,frame,300.0,345.0,"quarter",1,Design.SCORE_INK,20.0)
        context.paint_barline(self,frame,{"x":350.0,"style":"regular","repeat":"forward"},20.0)
        context.paint_clef(self,frame,50.0,180.0,{"sign":"G","line":2},20.0,Design.SCORE_INK)
        context.paint_meter_number(self,frame,4,70.0,180.0,Design.SCORE_INK,20.0)
        painted = true

var failures := 0
var Pass
var Symbols
var Context

func check(condition: bool, label: String) -> void:
    if not condition:
        failures += 1
        print("FAIL: ",label)

func _initialize() -> void:
    for name in ["render_pass","symbol_painter","context_painter"]:
        check(FileAccess.file_exists("res://notation/native/"+name+".gd"),"missing component "+name)
    if failures:
        finish()
        return
    Pass = load("res://notation/native/render_pass.gd")
    Symbols = load("res://notation/native/symbol_painter.gd")
    Context = load("res://notation/native/context_painter.gd")
    call_deferred("run_contract")

func finish() -> void:
    print("PAINT_COMPONENT_FAILURES:",failures)
    quit(0 if failures == 0 else 1)

func note(id: String, beat: float = 0.0) -> Dictionary:
    return {"id":id,"kind":"note","staff":"right","hand":"right","measure":1,
        "beat":beat,"duration_beats":1.0,"note_type":"quarter","voice":"1",
        "is_attack":true,"source_id":"source-"+id,"stem":"up",
        "spelling":{"step":"E","octave":4,"alter":0}}

func fixture(events: Array):
    var axis := Axis.new()
    axis.pixels_per_beat = 100.0
    axis.duration_beats = 4.0
    var measure := {"number":1,"start_beat":0.0,"end_beat":4.0,"meter":[4,4]}
    axis.measures = [measure]
    axis.model = {"measures":[measure],"notation_events":events}
    var score := Layout.new(axis,Atlas.new())
    score.set_viewport(Vector2(1000,500))
    score.measure_by_number = {1:measure}
    score.ordered_events = events
    for event in events:
        score.expression_note_index[str(event["id"])] = event
    for digit in range(10):
        score.glyphs.bounds["time_"+str(digit)] = [-50,-50,100,100]
    return score

func run_contract() -> void:
    var contract: String = OS.get_cmdline_user_args()[0]
    if contract == "frame":
        check_frame()
    elif contract == "symbols":
        check_symbols()
    elif contract == "context":
        check_context()
    elif contract == "atlas":
        await check_real_atlas()
    finish()

func check_frame() -> void:
    var history := {8.0:{"measure":{"start_beat":10.0,"end_beat":12.0}}}
    var frame = Pass.new({"clock":1.0,"playhead_x":400.0,"gap":20.0,
        "play_from_beat":2.0,"active_hand":"left","score_loop_enabled":true,
        "pass_index":3,"pass_start":8.0,"preparation_history":history,"visual_scroll_beat":17.0})
    var axis := Axis.new()
    axis.pixels_per_beat = 100.0
    check(frame.screen_x(axis,3.0) == 400.0,"one linear source-axis projection")
    check(not frame.event_visible({"beat":2.0}) and frame.event_visible({"beat":4.0}),"half-open recovery event bounds")
    check(not frame.span_visible({"beat":1.0},{"beat":2.0}),"spans touching silence start hidden")
    check(not frame.intervals_overlap({"start_beat":0.0,"end_beat":2.0},{"start_beat":2.0,"end_beat":4.0}),"touching recovery intervals stay distinct")
    check(frame.current_preparation == history[8.0],"per-pass preparation selection")
    check(frame.ink("left") == Design.SCORE_INK and frame.ink("right") == Color(Design.STAFF_MUTED,.46),"performer hand fade")
    var event := note("a")
    frame.record_notehead(event,Vector2(600,220),1000.0)
    frame.record_notehead(event,Vector2(410,220),1000.0)
    frame.record_notehead(event,Vector2(700,220),1000.0)
    check(frame.drawn_noteheads["a"] == Vector2(410,220),"nearest actual head to fixed playhead wins")
    check(frame.pass_noteheads["a"] == Vector2(700,220),"current pass head records latest authentic position")
    check(frame.drawn_note_instances[0] == {"event_id":"a","source_id":"source-a","pass_index":3,"instance_id":"3:a","position":Vector2(600,220)},"edit identity metadata unchanged")
    var other = Pass.new({})
    check(other.drawn_noteheads.is_empty() and other.drawn_note_instances.is_empty() and other.visible_symbols == 0 and other.scanned_events == 0 and other.visible_beam_groups == 0,"per-pass mutable outputs isolated")
    check(frame.visual_scroll_beat == 17.0 and frame.gap == 20.0,"explicit presentation values")

func check_symbols() -> void:
    var a := note("a")
    a["dots"] = 1
    a["accidental"] = "sharp"
    var b := note("b",2.0)
    var score = fixture([a,b])
    score.cached_head_offsets = {"a":5.0,"b":9.0}
    score.cached_accidental_offsets = {"a":-18.0}
    var original: Dictionary = score.timeline.model.duplicate(true)
    var painter = Symbols.new(score,Connectors.new(score))
    var frame = Pass.new({"clock":0.0,"playhead_x":100.0,"gap":20.0,"pass_index":2})
    var canvas := Canvas.new()
    painter.paint_note(canvas,frame,a,100.0,20.0,frame.ink("right"),{},5.0)
    check(frame.pass_noteheads["a"] == Vector2(105,220),"isolated head uses displaced actual glyph anchor")
    check(score.glyphs.calls[0] == ["note:quarter",Vector2(105,220),20.0,Design.SCORE_INK,true],"authentic complete note remains one sprite")
    check(score.glyphs.calls[1][0] == "augmentation_dot" and score.glyphs.calls[1][1].is_equal_approx(Vector2(126,215.2)),"dot remains tied to displaced head")
    check(score.glyphs.calls[2][0] == "acc_sharp" and score.glyphs.calls[2][1] == Vector2(87,220),"source accidental offset retained")
    check(frame.drawn_note_instances[0]["instance_id"] == "2:a","painted heads carry source-copy identity")
    painter.paint_ledger(canvas,frame,100.0,100.0,12,220.0,20.0,Design.SCORE_INK)
    check(canvas.lines.size() == 2 and canvas.lines[0][0] == Vector2(81,120) and canvas.lines[1][1] == Vector2(119,100),"ledger rules retain staff-space extents")
    check(is_equal_approx(canvas.lines[0][3],1.6),"ledger rules retain stroke weight")
    painter.paint_rest(canvas,frame,300.0,345.0,"quarter",2,Design.SCORE_INK,20.0)
    check(score.glyphs.calls[-1][1].is_equal_approx(Vector2(333.6,340.2)),"rest dots retain distinct rest anchor")
    painter.paint_note(canvas,frame,b,300.0,20.0,Design.SCORE_INK,{"up":true,"tip_y":140.0},9.0)
    check(frame.pass_noteheads["b"] == Vector2(309,220),"beamed heads retain real displacement")
    check(score.glyphs.calls[-1][0] == "stem:quarter","beamed notes use authentic stem mask")
    score.tie_pairs = [{"first":a,"last":b}]
    var image := Image.create(2,2,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    score.glyphs.tie_textures = {"up":ImageTexture.create_from_image(image),"down":ImageTexture.create_from_image(image)}
    painter.paint_ties(canvas,frame,100.0,0.0,20.0)
    check(canvas.textures.size() == 1 and canvas.textures[0][1].is_equal_approx(Rect2(109,222.4,196,3.2)),"ties use connector-owned fixed endpoint contours")
    score.slur_pairs = [{"first":a,"last":b,"key":"a|b"}]
    painter.paint_slurs(canvas,frame,100.0,0.0,20.0)
    check(score.glyphs.calls[-1][0] == "slur:a|b" and score.glyphs.calls[-1][1] == Vector2(105,220) and score.glyphs.calls[-1][2] == Vector2(309,220),"slurs project authentic displaced endpoints")
    score.notation_tuplets = [{"events":[a,b]},{"events":[a,b],"show_number":"none","bracket":"no"}]
    painter.paint_tuplet_brackets(canvas,frame,0.0,100.0,20.0)
    check(score.glyphs.calls[-1][0] == "tuplet:a|b","visible source tuplet painted")
    var count: int = score.glyphs.calls.size()
    var hidden = Pass.new({"score_loop_enabled":true,"pass_start":8.0,"preparation_history":{8.0:{"measure":{"start_beat":8.0,"end_beat":11.0}}}})
    painter.paint_tuplet_brackets(canvas,hidden,0.0,100.0,20.0)
    painter.paint_ties(canvas,hidden,100.0,0.0,20.0)
    painter.paint_slurs(canvas,hidden,100.0,0.0,20.0)
    check(score.glyphs.calls.size() == count and canvas.textures.size() == 1,"recovery hides connectors and tuplets consistently")
    score.attached_grace_notes = [{"before_note_id":"b","measure":1,"staff":"right","note_type":"eighth","spelling":{"step":"E","octave":4}}]
    painter.paint_grace_notes(canvas,frame,20.0)
    check(score.glyphs.calls[-1][1] == Vector2(281,220) and is_equal_approx(score.glyphs.calls[-1][2],13.2),"grace uses recorded actual target head and uniform scale")
    check_chord(painter,canvas,frame,score)
    check_beams(painter,canvas,frame,score,a,b)
    check(score.timeline.model == original,"painting preserves source model")

func check_chord(painter, canvas, frame, score) -> void:
    var lower := note("lower")
    var upper := note("upper")
    upper["chord"] = true
    upper["spelling"]["step"] = "F"
    score.chord_members = {"lower":[lower,upper]}
    score.cached_head_offsets.merge({"lower":-4.0,"upper":4.0})
    score.glyphs.chord_metadata["quarter|up|0,1"] = {"head_positions":[[-50,0],[50,-125]]}
    var ids: Array = painter.paint_engraved_chord(canvas,frame,lower,500.0,20.0,Design.SCORE_INK)
    check(ids == ["lower","upper"],"compound sprite reports every physical source identity")
    check(frame.pass_noteheads["lower"] == Vector2(496,220) and frame.pass_noteheads["upper"] == Vector2(504,210),"compound heads use measured original sprite offsets")
    score.beamed_note_ids = {"lower":true}
    check(painter.paint_engraved_chord(canvas,frame,lower,500.0,20.0,Design.SCORE_INK).is_empty(),"missing beam plan never invents compound stem")
    var before: int = score.glyphs.calls.size()
    painter.paint_engraved_chord(canvas,frame,lower,500.0,20.0,Design.SCORE_INK,{"up":true,"tip_y":140.0})
    check(score.glyphs.calls[before][0] == "chord_stem:quarter|up|0,1" and score.glyphs.calls[before+1][0] == "heads:quarter|up|0,1","beamed compound uses separated authentic masks")
    score.chord_members = {}
    score.beamed_note_ids = {}

func check_beams(painter, canvas, frame, score, a, b) -> void:
    score.beam_stem_up_by_note = {"a":true,"b":true}
    score.glyphs.beam_metadata["a|b"] = {"head_offsets":[0,250],"tip_offsets":[-500,-450]}
    var plan: Dictionary = painter.beam_layout(frame,score.cached_head_offsets,[[a,b]])
    check(frame.visible_beam_groups == 1 and not plan.has("visible_count"),"explicit beam plans keep original counter contract")
    check(plan["stems"]["a"]["tip_y"] == 180.0 and plan["stems"]["b"]["tip_y"] == 184.0,"source beam tips retain measured offsets")
    painter.paint_beams(canvas,frame,plan,20.0)
    check(score.glyphs.calls[-1][0] == "beam:a|b","source beam mask painted")
    check(score.glyphs.calls[-1][1] == [108.6,312.6],"beam mask attaches at actual shaft centers")
    painter.beam_layout(frame,score.cached_head_offsets,[])
    check(frame.visible_beam_groups == 0,"empty explicit group list cannot resurrect source beams")

func check_context() -> void:
    var a := note("a",1.0)
    a["staff"] = "left"
    var score = fixture([a])
    var symbols = Symbols.new(score,Connectors.new(score))
    var painter = Context.new(score,symbols)
    var frame = Pass.new({"active_hand":"right","clock":.5,"playhead_x":200.0,"gap":20.0,"play_from_beat":1.0,"visual_scroll_beat":5.0})
    var canvas := Canvas.new()
    painter.paint_barline(canvas,frame,{"x":300.0,"style":"light-heavy","repeat":"both","segments":[{"top":100.0,"bottom":300.0}]},20.0)
    check(canvas.lines.size() == 2 and is_equal_approx(canvas.lines[0][0].x,291.2) and canvas.lines[1][3] == 7.0,"authored barline uses full authentic stroke style")
    check(score.glyphs.calls.size() == 8 and score.glyphs.calls[0][1].is_equal_approx(Vector2(281.6,170)),"both repeat-dot pairs share original staff positions")
    check(is_equal_approx(painter.barline_left_limit(300.0,{"style":"light-heavy","repeat":"backward"},20.0),280.8),"backward repeat ink limits header lane")
    painter.paint_clef(canvas,frame,100.0,180.0,{"sign":"G","line":2,"octave_change":1},20.0,Design.SCORE_INK)
    check(score.glyphs.calls[-1][0] == "clef_g_8va" and score.glyphs.calls[-1][1] == Vector2(100,200),"combined authentic octave clef retains staff origin")
    painter.paint_meter_number(canvas,frame,12,100.0,80.0,Design.SCORE_INK,20.0)
    check(score.glyphs.calls[-2][1] == Vector2(89,80) and score.glyphs.calls[-1][1] == Vector2(111,80),"multi-digit meter stays centered")
    check(is_equal_approx(painter.context_meter_x({"meter":[12,8]},100.0,20.0,false,60.0),42.0),"meter clears exact rightmost boundary ink")
    var previous := {"number":1,"start_beat":0.0,"end_beat":.5,"meter":[1,8],"keys":{"right":2,"left":2}}
    var incoming := {"number":2,"start_beat":.5,"end_beat":4.5,"meter":[4,4],"keys":{"right":0,"left":0}}
    check(painter.meter_is_crowded(incoming,previous,20.0),"short pickup puts meter above staff")
    var start: int = score.glyphs.calls.size()
    check(painter.paint_context(canvas,frame,incoming,previous,300.0,20.0,false),"crowded context reports raised meter")
    var names: Array = []
    for call in score.glyphs.calls.slice(start):
        names.append(call[0])
    check(names.count("acc_natural") == 4,"key cancellation survives zero destination signature")
    check(score.glyphs.calls[-1][3] == Design.SCORE_INK and is_equal_approx(score.glyphs.calls[-1][2],14.4),"shared upper meter remains readable with one hand muted")
    score.source_expressions = [{"kind":"dynamic","value":"p","staff":"left","hand":"left","beat":1.0},
        {"kind":"articulation","value":"staccato","note_id":"a","beat":1.0}]
    frame.record_notehead(a,Vector2(155,280),1000.0)
    painter.paint_expressions(canvas,frame,-2.0,4.0,.5,200.0,20.0)
    check(score.glyphs.calls[-2][1] == Vector2(150,405) and score.glyphs.calls[-2][3] == Color(Design.STAFF_MUTED,.46),"dynamic inherits performer tint on display staff")
    check(score.glyphs.calls[-1][0] == "artic_staccato_above" and score.glyphs.calls[-1][1] == Vector2(155,259),"linked articulation uses painted actual head")
    score.source_expressions = [{"kind":"hairpin","value":"crescendo","staff":"right","beat":0.0},{"kind":"hairpin","value":"stop","staff":"right","beat":2.0}]
    var line_start := canvas.lines.size()
    painter.paint_hairpins(canvas,frame,-2.0,4.0,.5,200.0,20.0)
    check(canvas.lines.size() == line_start+2 and canvas.lines[-2][0].is_equal_approx(Vector2(59.6,250.4)) and canvas.lines[-2][1].is_equal_approx(Vector2(245,246.3)),"hairpin endpoints preserve source axis and wedge slope")
    var silence := {"start_beat":4.0,"end_beat":8.0,"meter":[4,4],"events":[{"staff":"right"},{"staff":"left"}],"left_barline":{"style":"regular"},"right_barline":{"style":"regular"}}
    painter.paint_preparation_measure(canvas,frame,silence,{},20.0,200.0)
    check(score.glyphs.calls[-2][0] == "rest_whole" and score.glyphs.calls[-2][1].is_equal_approx(Vector2(273,160)),"preparation rest shares exact projected boundary midpoint")
    check(score.glyphs.calls[-1][3] == Color(Design.STAFF_MUTED,.46),"preparation rest observes explicit hand selection")
    score.timeline.measures[0]["left_barline"] = {"ending":{"type":"start","number":"1"}}
    score.timeline.measures[0]["right_barline"] = {"ending":{"type":"stop","number":"1"}}
    painter.paint_volta_endings(canvas,frame,-2.0,5.0,.5,200.0,20.0)
    check(canvas.strings[-1][1] == "1.","source volta text retains closed endpoint label")


func check_real_atlas() -> void:
    # Run the unchanged, CanvasItem-typed production atlas on a real canvas.
    # Synthetic masks isolate projection/lifecycle from asset generation/HTTP.
    var a := note("real")
    var score = fixture([a])
    var atlas = load("res://notation/native/glyphs.gd").new()
    var image := Image.create(2,2,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    var texture := ImageTexture.create_from_image(image)
    atlas.bounds = {"head_black":[-50,-50,100,100],"augmentation_dot":[-10,-10,20,20],
        "rest_quarter":[-40,-80,80,160],"repeat_dot":[-10,-10,20,20],
        "clef_g":[-40,-100,80,200],"time_4":[-40,-80,80,160]}
    for key in atlas.bounds:
        atlas.textures[key] = texture
    atlas.note_textures["quarter_up"] = texture
    atlas.note_bounds["quarter_up"] = [-50,-500,100,550]
    score.glyphs = atlas
    var symbols = Symbols.new(score,Connectors.new(score))
    var canvas := ActualCanvas.new()
    canvas.symbols = symbols
    canvas.context = Context.new(score,symbols)
    canvas.frame = Pass.new({"gap":20.0})
    canvas.event = a
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1000,500)
    root.add_child(viewport)
    viewport.add_child(canvas)
    await process_frame
    await process_frame
    check(canvas.painted,"real atlas runs inside actual CanvasItem draw lifecycle")
    check(canvas.frame.pass_noteheads.get("real") == Vector2(100,220),"real production atlas keeps actual head metadata")
    check(canvas.frame.drawn_note_instances.size() == 1,"rests/context cannot become playable note instances")
    viewport.free()
