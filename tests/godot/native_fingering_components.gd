extends SceneTree
# These assertions catch changed source coordinates, copy visibility,
# assignment validation, physical-note deduplication and edit identity.
const Layout := preload("res://notation/native/score_layout.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")
const Connectors := preload("res://notation/native/connector_geometry.gd")
const Design := preload("res://practice_theme.gd")

class Canvas:
    extends RefCounted
    var host: Node
    var strings: Array = []
    func _init(parent: Node) -> void:
        host = parent
    func draw_string(_font, position, text, _alignment, _width, font_size, ink) -> void:
        strings.append({"position":position,"text":text,"font_size":font_size,"ink":ink})
    func add_child(child: Node) -> void:
        host.add_child(child)
    func get_screen_transform() -> Transform2D:
        return Transform2D(0.0,Vector2(10,20))

var failures := 0

func check(condition: bool, label: String) -> void:
    if not condition:
        failures += 1
        print("FAIL: ",label)

func _initialize() -> void:
    for path in ["fingering_annotations.gd","fingering_obstacles.gd","source_visibility.gd"]:
        if not FileAccess.file_exists("res://notation/native/"+path):
            check(false,"missing independent component "+path)
    if failures:
        finish()
        return
    call_deferred("run_contract")

func finish() -> void:
    print("FINGERING_COMPONENT_FAILURES:",failures)
    quit(0 if failures == 0 else 1)

func note(id: String, beat: float, finger: Variant = 2) -> Dictionary:
    return {"id":id,"kind":"note","staff":"right","hand":"right",
        "measure":1,"beat":beat,"duration_beats":1.0,"note_type":"quarter",
        "voice":"1","is_attack":true,"source_id":"source-"+id,"midi_pitch":64,
        "spelling":{"step":"E","octave":4,"alter":0},
        "fingering":{"finger":finger,"hand":"right","source_id":"source-"+id,"origin":"manual"}}

func fixture(events: Array):
    var axis := Axis.new()
    axis.pixels_per_beat = 100.0
    axis.duration_beats = 4.0
    var measure := {"number":1,"start_beat":0.0,"end_beat":4.0,
        "left_barline":{"style":"none","repeat":""},
        "right_barline":{"style":"none","repeat":""}}
    axis.measures = [measure]
    axis.model = {"measures":[measure],"notation_events":events}
    var atlas := Glyphs.new()
    atlas.bounds = {"head_black":[-50,-50,100,100],"head_half":[-50,-50,100,100],
        "augmentation_dot":[-10,-10,20,20],"repeat_dot":[-10,-10,20,20],
        "rest_quarter":[-40,-80,80,160]}
    var score := Layout.new(axis,atlas)
    score.set_viewport(Vector2(1000,500))
    score.rebuild_index()
    return score

func run_contract() -> void:
    var Placement = load("res://notation/native/fingering_placement.gd")
    var Visibility = load("res://notation/native/source_visibility.gd")
    var Annotations = load("res://notation/native/fingering_annotations.gd")
    var Obstacles = load("res://notation/native/fingering_obstacles.gd")
    var first := note("a",1.0)
    check(Placement.assignment(first) == first["fingering"],"valid manual assignment")
    for invalid in [null,0,6,2.5,NAN,INF,"2",true]:
        var event := note("invalid",0.0,invalid)
        check(Placement.assignment(event).is_empty(),"invalid finger rejected: "+str(invalid))
    for invalid in [{"hand":"both"},{"source_id":""},{"source_id":2},{"origin":"unknown"}]:
        var event := first.duplicate(true)
        event["fingering"].merge(invalid,true)
        check(Placement.assignment(event).is_empty(),"invalid assignment metadata")
    var continued := first.duplicate(true)
    continued["is_attack"] = false
    check(Placement.assignment(continued).is_empty(),"continuations have no annotation")
    var unknown := note("unknown",3.0,null)
    check(Placement.source(unknown) == "source-unknown","manual unknown remains editable")
    check(Placement.source({"source_id":"fallback"}) == "fallback","event source fallback")
    check(Placement.source({"source_id":123}).is_empty(),"non-string source rejected")

    var history := {8.0:{"measure":{"start_beat":10.0,"end_beat":12.0}}}
    for sample in [[1.99998,true],[2.0,false],[3.99998,false],[4.0,true]]:
        check(Visibility.event_visible({"beat":sample[0]},8.0,true,history) == sample[1],"event boundary "+str(sample[0]))
    check(Visibility.event_visible({"start_beat":2.0},8.0,false,history),"disabled loop ignores recovery")
    check(not Visibility.event_visible({"start_beat":2.0},8.0,true,history),"measure start fallback")
    check(not Visibility.span_visible({"beat":1.0},{"beat":2.0},8.0,true,history),"span touching silence start hidden")
    check(Visibility.span_visible({"beat":4.0},{"beat":5.0},8.0,true,history),"span at silence end visible")
    check(not Visibility.intervals_overlap({"start_beat":0.0,"end_beat":2.0},{"start_beat":2.0,"end_beat":4.0}),"touching intervals do not overlap")
    check(Visibility.intervals_overlap({"start_beat":0.0,"end_beat":2.1},{"start_beat":2.0,"end_beat":4.0}),"crossing intervals overlap")

    var twin := note("twin",1.0)
    var left := note("left",2.0,4)
    left["staff"] = "left"
    left["hand"] = "left"
    left["fingering"]["hand"] = "left"
    var score = fixture([first,twin,left,unknown])
    var original: Dictionary = score.timeline.model.duplicate(true)
    var connector := Connectors.new(score)
    var obstacles = Obstacles.new(score,connector)
    var bins := {}
    obstacles.build(20.0,bins,100.0,0.0)
    check(obstacles.staff_lines.size() == 10,"both staves reserved independently")
    check(not obstacles.is_clear(Rect2(99,219,2,2),bins,100.0),"source head blocks its own location")
    check(obstacles.is_clear(Rect2(600,100,2,2),bins,100.0),"empty space remains free")
    check(obstacles.staff_lines[0] == Rect2(-240,139.5,1240,1),"staff-line envelope stays on source axis")
    # Repeat punctuation must cancel the explicit barline play-from translation.
    score.timeline.measures[0]["left_barline"] = {"style":"regular","repeat":"forward"}
    score.timeline.measures[0]["right_barline"] = {"style":"light-heavy","repeat":"backward"}
    bins.clear()
    obstacles.build(20.0,bins,100.0,0.0)
    var zero_bins: Dictionary = bins.duplicate(true)
    bins.clear()
    obstacles.build(20.0,bins,100.0,2.0)
    check(bins == zero_bins,"play-from does not translate source barlines or repeat dots")
    check(not obstacles.is_clear(Rect2(372,250,2,2),bins,100.0),"terminal barline uses score-axis position 373")
    check(not obstacles.is_clear(Rect2(353.8,169.8,.4,.4),bins,100.0),"backward repeat dot stays beside terminal barline")
    score.timeline.measures[0]["left_barline"] = {"style":"none","repeat":""}
    score.timeline.measures[0]["right_barline"] = {"style":"none","repeat":""}
    obstacles.block(Rect2(700,100,10,10),bins,100.0)
    check(not obstacles.is_clear(Rect2(705,105,2,2),bins,100.0),"explicit packed cells block later labels")

    var annotations = Annotations.new(score,connector)
    annotations.layout_fingerings(20.0)
    check(annotations.fingering_layout.size() == 2,"one physical note across voices, plus left hand")
    check(annotations.fingering_placement_issues.is_empty(),"simple source admits local placement")
    check(annotations.fingering_layout[0]["event_ids"] == ["a","twin"],"dedup preserves both edit identities")
    var cell_metrics: Dictionary = annotations.metrics(15)
    check(cell_metrics["ink_size"].x > 0 and cell_metrics["cell"].y >= cell_metrics["ink_size"].y,"real font ink metrics")
    var source_layout: Array = annotations.fingering_layout.duplicate(true)
    var canvas := Canvas.new(root)
    annotations.begin_frame()
    annotations.paint(canvas,0.5,400.0,20.0,2,8.0,{"active_hand":"right","play_from_beat":1.0})
    check(annotations.drawn_fingerings.size() == 2,"visible annotations recorded")
    for i in range(2):
        check(annotations.drawn_fingerings[i]["head"] == source_layout[i]["head"]+Vector2(250,0),"single explicit source-axis translation")
        check(annotations.drawn_fingerings[i]["pass_index"] == 2,"pass identity preserved")
    check(canvas.strings[0]["ink"] == Design.SCORE_INK,"selected right-hand ink")
    check(canvas.strings[1]["ink"] == Color(Design.STAFF_MUTED,.46).lerp(Design.BLUE,.32),"inactive left-hand tint")
    check(annotations.fingering_layout == source_layout,"painting does not move cached annotation cells")
    annotations.begin_frame()
    annotations.paint(canvas,0.0,400.0,20.0,0,8.0,{"score_loop_enabled":true,"preparation_history":{8.0:{"measure":{"start_beat":9.0,"end_beat":10.0}}}})
    check(annotations.drawn_fingerings.size() == 1 and annotations.drawn_fingerings[0]["hand"] == "left","recovery visibility comes from explicit frame data")
    annotations.begin_frame()
    annotations.paint(canvas,0.0,-100.0,20.0)
    check(annotations.drawn_fingerings.size() == 1,"partly clipped numeral omitted as a whole")

    var edits: Array = []
    annotations.fingering_change_requested.connect(func(source_id: String, finger: Variant): edits.append([source_id,finger]))
    check(annotations.open_editor(canvas,Vector2(900,100),20.0,[{"event_id":"unknown","position":Vector2(900,100)}]),"manual unknown selected via explicit drawn notes")
    check(annotations.fingering_popup.get_item_text(0) == "Right hand · fingering","menu performer header")
    for i in range(1,6):
        check(not annotations.fingering_popup.is_item_checked(i),"manual unknown checks no finger")
    annotations.fingering_popup.id_pressed.emit(3)
    annotations.fingering_popup.id_pressed.emit(0)
    check(edits == [["source-unknown",3],["source-unknown",null]],"edit and reset emit original source identity")
    check(annotations.open_editor(canvas,Vector2(900,100),20.0,[{"event_id":"a","position":Vector2(900,100)},{"event_id":"twin","position":Vector2(900,100)}]),"coincident voices remain independently editable")
    check(annotations.fingering_popup.item_count == 2,"coincident sources become submenus")
    check(annotations.fingering_popup.get_child(0).get_item_text(0) == "Right hand · fingering","submenu retains assignment menu")
    annotations.begin_frame()
    annotations.paint(canvas,0.0,400.0,20.0)
    var label_point: Vector2 = annotations.drawn_fingerings[0]["rect"].get_center()
    check(annotations.open_editor(canvas,label_point,20.0,[]),"label hit selects its merged event identities")
    check(annotations.fingering_popup.item_count == 2,"merged label exposes each source voice")
    annotations.set_enabled(false)
    check(annotations.drawn_fingerings.is_empty() and not annotations.fingering_popup.visible,"disable clears labels and hides menu")
    check(not annotations.open_editor(canvas,label_point,20.0,[]),"disabled annotations cannot edit")
    annotations.set_enabled(true)
    annotations.clear()
    check(annotations.fingering_layout.is_empty() and annotations.fingering_layout_gap < 0,"score reset invalidates placement")
    check(score.timeline.model == original,"source score remains immutable")
    # Exact alpha-aware envelopes exclude each authentic head rectangle.
    var picture := Image.create(6,6,false,Image.FORMAT_RGBA8)
    picture.fill(Color.TRANSPARENT)
    picture.set_pixel(0,2,Color.WHITE)  # first head, reserved separately
    picture.set_pixel(5,2,Color.WHITE)  # second chord head, outside a single head
    picture.set_pixel(5,0,Color.WHITE)
    picture.set_pixel(4,1,Color(1,1,1,.004))  # faint edge ink must survive
    score.glyphs.note_bounds["eighth_up"] = [-50,-100,150,150]
    score.glyphs.note_textures["eighth_up"] = ImageTexture.create_from_image(picture)
    score.glyphs.chord_metadata["two-heads"] = {"bounds":[-50,-100,150,150],"head_positions":[[0,0],[100,0]]}
    score.glyphs.chord_textures["two-heads"] = ImageTexture.create_from_image(picture)
    check(obstacles.nonhead_envelope("eighth",true).is_equal_approx(Rect2(50,-100,50,75)),"single-head mask retains faint flag ink")
    check(obstacles.nonhead_envelope("eighth",true,"two-heads").is_equal_approx(Rect2(50,-100,50,50)),"chord envelope excludes both heads")
    picture.fill(Color.TRANSPARENT)
    score.glyphs.note_textures["eighth_up"] = ImageTexture.create_from_image(picture)
    check(obstacles.nonhead_envelope("eighth",true).is_equal_approx(Rect2(50,-100,50,75)),"texture envelope cached for atlas lifetime")
    obstacles.clear()
    check(obstacles.staff_lines.is_empty() and obstacles.sprite_envelopes.is_empty(),"obstacle reset owns its caches")
    check(obstacles.nonhead_envelope("eighth",true) == Rect2(),"cache clear observes replacement glyph atlas")
    check_obstacle_geometry(Obstacles)
    finish()

func contains_rect(bins: Dictionary, wanted: Rect2) -> bool:
    for column in bins.values():
        for rect in column:
            if rect.is_equal_approx(wanted):
                return true
    return false

func check_obstacle_geometry(Obstacles) -> void:
    var a := note("a",0.0)
    a["accidental"] = "sharp"
    var b := note("b",2.0)
    var rest := {"id":"rest","kind":"rest","staff":"left","measure":1,
        "beat":1.0,"note_type":"quarter","dots":2,"voice":"1"}
    var score = fixture([a,rest,b])
    score.cached_head_offsets = {"a":5.0,"b":9.0}
    score.cached_accidental_offsets = {"a":-18.0}
    score.beam_groups = [[a,b]]
    score.beamed_note_ids = {"a":true,"b":true}
    score.beam_stem_up_by_note = {"a":true,"b":true}
    score.glyphs.note_stem_bounds["quarter_up"] = [40,-500,10,500]
    score.glyphs.beam_metadata["a|b"] = {"bounds":[0,-500,250,40],
        "head_offsets":[10,200],"tip_offsets":[-500,-450],"stem_up":true}
    score.tie_pairs = [{"first":a,"last":b}]
    score.glyphs.tie_metadata["up"] = {"bounds":[50,30,400,40],"span":500,
        "head_centers":[0,0],"head_widths":[100,100]}
    score.slur_pairs = [{"first":a,"last":b,"key":"a|b"}]
    score.glyphs.slur_metadata["a|b"] = {"bounds":[-10,-700,300,30],"span":250,"original_end_y":0}
    score.notation_tuplets = [{"events":[a,b]}]
    score.glyphs.tuplet_metadata["a|b"] = {"span":250,
        "number":{"bounds":[0,-800,30,40]},"bracket":{"bounds":[-10,-750,300,20]}}
    score.glyphs.bounds["acc_sharp"] = [-20,-60,40,120]
    score.glyphs.bounds["dynamic_p"] = [-20,-30,40,60]
    score.glyphs.bounds["artic_staccato_below"] = [-10,-20,20,40]
    score.source_expressions = [{"kind":"dynamic","value":"p","staff":"left","beat":1.0},
        {"kind":"articulation","value":"staccato","note_id":"a"},
        {"kind":"hairpin","value":"crescendo","staff":"right","beat":.5},
        {"kind":"hairpin","value":"stop","staff":"right","beat":1.5}]
    score.glyphs.note_bounds["eighth_up"] = [-50,-100,150,150]
    score.attached_grace_notes = [{"before_note_id":"b","measure":1,"staff":"right",
        "note_type":"eighth","spelling":{"step":"E","octave":4}}]
    var obstacle = Obstacles.new(score,Connectors.new(score))
    var bins := {}
    obstacle.build(20.0,bins,100.0,2.0)
    for sample in [
        [Rect2(1,216,8,8),"displaced source head"],
        [Rect2(-14.6,215.2,3.2,9.6),"source accidental offset"],
        [Rect2(96.8,338.6,6.4,12.8),"rest source rectangle"],
        [Rect2(120.2,339.4,1.6,1.6),"first rest dot"],
        [Rect2(132.8,339.4,1.6,1.6),"second rest dot"],
        [Rect2(4.2,180,208.8,3.2),"source beam mask"],
        [Rect2(8.2,180,.8,40),"first stretched beam stem"],
        [Rect2(212.2,184,.8,36),"second stretched beam stem"],
        [Rect2(9,222.4,196,3.2),"connector-owned tie contour"],
        [Rect2(-3.16,164,244.8,2.4),"source slur contour"],
        [Rect2(105.8,156,2.4,3.2),"source tuplet number"],
        [Rect2(4.2,160,208,1.6),"source tuplet bracket"],
        [Rect2(98.56,402.84,2.88,4.32),"dynamic display staff"],
        [Rect2(4.28,239.56,1.44,2.88),"linked articulation"],
        [Rect2(59.6,245,85.4,12),"paired source hairpin"],
        [Rect2(178.36,214.72,7.92,7.92),"linked grace note"]]:
        check(contains_rect(bins,sample[0]),sample[1])
    score.notation_tuplets[0]["show_number"] = "none"
    score.notation_tuplets[0]["bracket"] = "no"
    bins.clear()
    obstacle.build(20.0,bins,100.0)
    check(not contains_rect(bins,Rect2(105.8,156,2.4,3.2)),"hidden tuplets reserve no ink")

    var lower := note("lower",0.0)
    lower["dots"] = 1
    var upper := note("upper",0.0)
    upper["chord"] = true
    upper["dots"] = 1
    upper["spelling"]["step"] = "F"
    var chord_score = fixture([lower,upper])
    chord_score.cached_head_offsets = {"lower":-4.0,"upper":4.0}
    var chord_obstacles = Obstacles.new(chord_score,Connectors.new(chord_score))
    bins.clear()
    chord_obstacles.build(20.0,bins,100.0)
    check(contains_rect(bins,Rect2(24.2,229.2,1.6,1.6)),"lower chord dot clears adjacent occupied staff space")
    check(contains_rect(bins,Rect2(24.2,209.2,1.6,1.6)),"upper chord dot shares rightmost head anchor")
