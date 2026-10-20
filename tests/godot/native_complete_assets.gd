extends SceneTree

var failures: Array[String] = []
var calls := 0
const C_CLEFS := ["clef_c_8va","clef_c_15ma","clef_c_15mb"]
const C_ANCHORS := [120,340,560]
const C_Y := 680
const C_GAP := 36.0
const C_REFERENCE_X := 790
const C_OCTAVE_REFERENCE_X := 1010
var octave_reference_texture: Texture2D
var octave_reference_data: Dictionary = {}

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("NATIVE_COMPLETE_ASSET_FAIL: ",label)

class Artwork extends Node2D:
    var atlas
    var suite
    func _draw() -> void:
        var ink := Color.WHITE
        for direction in [false,true]:
            var x: float = 70.0 if direction else 160.0
            suite.check(atlas.paint_note(self,"128th",direction,x,145.0,20.0,ink),
                "Draw complete original 128th note")
            suite.calls += 1
        var names := ["rest_128th","flag_up_5","flag_down_5",
            "clef_g_15mb","clef_g_15ma","clef_f_15mb","clef_f_15ma"]
        for i in range(names.size()):
            suite.check(atlas.paint(self,names[i],250.0+i*90.0,145.0,20.0,ink),
                "Draw authentic "+names[i])
            suite.calls += 1
        for direction in ["up","down"]:
            suite.check(atlas.paint_chord(self,"128th|"+direction+"|0,2",
                70.0 if direction == "up" else 180.0,320.0,20.0,ink),
                "Draw original 128th chord")
            suite.calls += 1
        for i in range(2):
            var key: String = "outer" if i == 0 else "inner"
            suite.check(atlas.has_tuplet(key,true),"Separate stable tuplet group ID")
            suite.check(atlas.paint_tuplet(self,key,300.0,680.0,
                350.0+i*90.0,20.0,ink),"Draw real tuplet bracket and numeral")
            suite.calls += 1
        suite.check(atlas.paint_tuplet(self,"hidden",720.0,900.0,400.0,20.0,ink),
            "Source-hidden numeral keeps its real bracket")
        suite.calls += 1
        var reference: Dictionary = suite.octave_reference_data
        var source_box: Array = reference["bounds"]
        var source_ink: Array = reference["ink_bounds"]
        var unit: float = suite.C_GAP/250.0
        var scale: float = float(reference["height_units"])/float(source_ink[3])
        var base: Array = atlas.bounds["clef_c"]
        var center: float = suite.C_OCTAVE_REFERENCE_X+float(reference["center_x_units"])*unit
        var number_left: float = center-float(source_ink[2])*scale*unit*.5
        var number_top: float = suite.C_Y+(float(base[1])+12.0-
            float(reference["clearance_units"])-float(reference["height_units"]))*unit
        self.draw_texture_rect(suite.octave_reference_texture,Rect2(
            number_left+(float(source_box[0])-float(source_ink[0]))*scale*unit,
            number_top+(float(source_box[1])-float(source_ink[1]))*scale*unit,
            float(source_box[2])*scale*unit,float(source_box[3])*scale*unit),false,ink)
        suite.calls += 1
        for i in range(suite.C_CLEFS.size()):
            suite.check(atlas.paint(self,suite.C_CLEFS[i],suite.C_ANCHORS[i],
                suite.C_Y,suite.C_GAP,ink),"Draw original "+suite.C_CLEFS[i])
            suite.calls += 1
        suite.check(atlas.paint(self,"clef_c",suite.C_REFERENCE_X,suite.C_Y,
            suite.C_GAP,ink),"Draw independent base C-clef reference")
        suite.calls += 1


func ink_count(raster: Image, region: Rect2i) -> int:
    var clipped := region.intersection(Rect2i(Vector2i.ZERO,raster.get_size()))
    var count := 0
    for y in range(clipped.position.y,clipped.end.y):
        for x in range(clipped.position.x,clipped.end.x):
            if raster.get_pixel(x,y).a > .2:
                count += 1
    return count


func ink_bounds(raster: Image, region: Rect2i) -> Rect2i:
    var clipped := region.intersection(Rect2i(Vector2i.ZERO,raster.get_size()))
    var left: int = clipped.end.x
    var top: int = clipped.end.y
    var right: int = clipped.position.x
    var bottom: int = clipped.position.y
    for y in range(clipped.position.y,clipped.end.y):
        for x in range(clipped.position.x,clipped.end.x):
            if raster.get_pixel(x,y).a > .2:
                left = mini(left,x)
                top = mini(top,y)
                right = maxi(right,x+1)
                bottom = maxi(bottom,y+1)
    return Rect2i(left,top,maxi(0,right-left),maxi(0,bottom-top))


func matching_ink(raster: Image, actual: Rect2i, reference: Rect2i) -> float:
    if actual.size.x <= 0 or actual.size.y <= 0 or reference.size.x <= 0 or reference.size.y <= 0:
        return 0.0
    var total := 0
    var matched := 0
    for y in range(actual.size.y):
        for x in range(actual.size.x):
            if raster.get_pixel(actual.position.x+x,actual.position.y+y).a <= .2:
                continue
            total += 1
            var rx: int = reference.position.x+int(float(x)*reference.size.x/actual.size.x)
            var ry: int = reference.position.y+int(float(y)*reference.size.y/actual.size.y)
            var nearby := false
            # Allow one raster pixel of antialiasing/rounding variation.
            for dy in range(-1,2):
                for dx in range(-1,2):
                    if raster.get_pixel(rx+dx,ry+dy).a > .2:
                        nearby = true
            if nearby:
                matched += 1
    return float(matched)/maxf(1.0,float(total))


func check_c_clef_pixels(raster: Image,atlas) -> void:
    # Regions come from the independently rendered BASE clef, never the
    # compound's bounds or its numeral placement implementation.
    var base: Array = atlas.bounds["clef_c"]
    var unit: float = C_GAP/250.0
    var left: int = int(floor(float(base[0])*unit))
    var right: int = int(ceil((float(base[0])+float(base[2]))*unit))
    var top: int = C_Y+int(floor(float(base[1])*unit))
    var bottom: int = C_Y+int(ceil((float(base[1])+float(base[3]))*unit))
    var reference := Rect2i(C_REFERENCE_X+left,top,right-left,bottom-top)
    var reference_ink: int = ink_count(raster,reference)
    check(reference_ink > 100,"Independent base C clef has visible Godot pixels")
    check(ink_count(raster,Rect2i(C_REFERENCE_X-15,540,130,top-540)) == 0 and
        ink_count(raster,Rect2i(C_REFERENCE_X-15,bottom,130,860-bottom)) == 0,
        "Base C clef has no octave numeral outside its body")
    for i in range(C_CLEFS.size()):
        var x: int = C_ANCHORS[i]
        var body := Rect2i(x+left,top,right-left,bottom-top)
        var overlap := 0
        var union := 0
        for dy in range(body.size.y):
            for dx in range(body.size.x):
                var actual: bool = raster.get_pixel(body.position.x+dx,top+dy).a > .2
                var expected: bool = raster.get_pixel(reference.position.x+dx,top+dy).a > .2
                if actual or expected:
                    union += 1
                if actual and expected:
                    overlap += 1
        check(union > 0 and float(overlap)/maxf(1.0,float(union)) > .85,
            "Original base-clef silhouette remains visible for "+C_CLEFS[i])
        var above: int = ink_count(raster,Rect2i(x-15,540,130,top-540))
        var below: int = ink_count(raster,Rect2i(x-15,bottom,130,860-bottom))
        var expects_above: bool = i < 2
        var side: String = "above" if expects_above else "below"
        check((above if expects_above else below) > 20,
            "Expected octave numeral "+side+" for "+C_CLEFS[i])
        check((below if expects_above else above) <= 1,
            "No octave numeral on the wrong side for "+C_CLEFS[i])
    # An '8' must not substitute for the '15' even when both are above.
    var different := 0
    for y in range(540,top):
        for dx in range(-15,115):
            var eight: bool = raster.get_pixel(C_ANCHORS[0]+dx,y).a > .2
            var fifteen: bool = raster.get_pixel(C_ANCHORS[1]+dx,y).a > .2
            if eight != fifteen:
                different += 1
    check(different > 20,"Octave 8 and octave 15 retain distinct original numeral silhouettes")
    var above_eight: Rect2i = ink_bounds(raster,Rect2i(C_ANCHORS[0]-15,540,130,top-540))
    var original_eight: Rect2i = ink_bounds(raster,Rect2i(C_OCTAVE_REFERENCE_X-15,540,130,top-540))
    check(original_eight.size.x > 5 and original_eight.size.y > 10,
        "Independent E510 reference has a visible octave-eight numeral")
    check(absi(above_eight.size.x-original_eight.size.x) <= 2 and
        absi(above_eight.size.y-original_eight.size.y) <= 2,
        "Original octave-eight silhouette dimensions retained above the base C clef")
    var eight_ink: int = ink_count(raster,above_eight)
    var reference_eight_ink: int = ink_count(raster,original_eight)
    check(absf(float(eight_ink-reference_eight_ink)) <= maxf(5.0,float(reference_eight_ink)*.2),
        "Original octave-eight silhouette ink retained above the base C clef")
    check(matching_ink(raster,above_eight,original_eight) > .9 and
        matching_ink(raster,original_eight,above_eight) > .9,
        "Original octave-eight contour retained above the base C clef")
    print("NATIVE_C_CLEF_PIXEL_CHECKS:3")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    check(OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1",
        "Explicit native notation selection")
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_ASSET_FIXTURE")))
    var atlas = load("res://notation/native/glyphs.gd").new()
    octave_reference_data = data["octave_eight_reference"]
    check(str(octave_reference_data.get("code","")) == "E510" and
        str(octave_reference_data.get("source","")) == "verovio",
        "Reference is the original standalone Verovio E510 contour")
    var reference_image := Image.new()
    check(reference_image.load_svg_from_buffer(str(octave_reference_data["svg"]).to_utf8_buffer(),
        atlas.RASTER_SCALE) == OK and not reference_image.is_empty(),
        "Godot rasterizes the independent original E510 reference")
    octave_reference_texture = ImageTexture.create_from_image(reference_image)
    check(atlas.load_font(data["glyphs"]),"Load extended authentic font: "+atlas.error)
    check(atlas.load_note_templates(data["notes"]),"Load 128th templates: "+atlas.error)
    check(atlas.load_chord_templates(data["chords"]),"Load 128th chords: "+atlas.error)
    check(atlas.load_tuplet_fragments(data["tuplets"]),"Load same-endpoint nested tuplets: "+atlas.error)
    if not failures.is_empty():
        quit(1)
        return
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1200,900)
    viewport.transparent_bg = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var canvas := Artwork.new()
    canvas.atlas = atlas
    canvas.suite = self
    viewport.add_child(canvas)
    await process_frame
    await process_frame
    if OS.get_environment("PIANO_TEACHER_ASSET_PIXELS") == "1":
        await RenderingServer.frame_post_draw
        var raster := viewport.get_texture().get_image()
        var count := 0
        for y in range(raster.get_height()):
            for x in range(raster.get_width()):
                if raster.get_pixel(x,y).a > .1:
                    count += 1
        check(count > 1500,"Native compositor produces real visible glyph pixels")
        var names := ["rest_128th","flag_up_5","flag_down_5",
            "clef_g_15mb","clef_g_15ma","clef_f_15mb","clef_f_15ma"]
        for i in range(names.size()):
            var box: Array = atlas.bounds[names[i]]
            var left: int = maxi(0,int(floor(250.0+i*90.0+float(box[0])*.08)))
            var top: int = maxi(0,int(floor(145.0+float(box[1])*.08)))
            var right: int = mini(raster.get_width(),int(ceil(250.0+i*90.0+(float(box[0])+float(box[2]))*.08)))
            var bottom: int = mini(raster.get_height(),int(ceil(145.0+(float(box[1])+float(box[3]))*.08)))
            var symbol_pixels := 0
            for y in range(top,bottom):
                for x in range(left,right):
                    if raster.get_pixel(x,y).a > .1:
                        symbol_pixels += 1
            check(symbol_pixels > 10,"Visible original ink for "+names[i])
        check_c_clef_pixels(raster,atlas)
        var path := OS.get_environment("PIANO_TEACHER_ASSET_PNG")
        if not path.is_empty():
            raster.save_png(path)
    check(calls == 19,"Every requested extended asset passes through its actual draw method")
    print("NATIVE_COMPLETE_ASSET_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
