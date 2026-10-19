extends RefCounted
# Test-only synthetic 2x2 vector square. NEVER referenced by application
# or production glyph catalogue. Verifies glyph loading/placement; the real
# MIDI integration test checks authentic Verovio outlines independently.

static func catalogue() -> Dictionary:
    var asset = load("res://score_verovio_glyphs.gd")
    var result: Dictionary = {}
    for name in asset.REQUIRED:
        result[name] = {
            "source": "verovio", "font": "UnitTestOnly", "units_per_space": 250,
            "bounds": [0.0, 0.0, 2.0, 2.0],
            "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" width="2" height="2"><path d="M0 0L2 0L2 2L0 2Z" fill="white"/></svg>'
        }
    return result


# Synthetic PNG fixtures used only by geometry tests. The actual desktop
# tests validate Verovio's engraved heads, stems and flags end-to-end.
static func note_catalogue() -> Dictionary:
    var atlas = load("res://score_verovio_glyphs.gd")
    var image := Image.create(3,3,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    var encoded: String = Marshalls.raw_to_base64(image.save_png_to_buffer())
    var entries: Dictionary = {}
    for name in atlas.NOTE_TEMPLATES:
        entries[name] = {
            "source": "verovio-engraved-note",
            "units_per_space": 250, "bounds":[-1.5,-1.5,3.0,3.0],
            "png_base64":encoded
        }
        if name != "whole":
            entries[name]["stem_only"] = {
                "source":"verovio-engraved-note-stem",
                "units_per_space":250,"bounds":[0.0,-300.0,2.0,300.0],
                "png_base64":encoded}
    return entries


static func tie_catalogue() -> Dictionary:
    var image := Image.create(4,2,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    var encoded: String = Marshalls.raw_to_base64(image.save_png_to_buffer())
    var output: Dictionary = {}
    for side in ["up","down"]:
        output[side] = {"source":"verovio-engraved-tie",
            "units_per_space":250, "bounds":[0.0,-10.0,80.0,12.0],
            "span":80.0, "png_base64":encoded}
    return output


static func chord_catalogue() -> Dictionary:
    var image := Image.create(4,8,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    var encoded: String = Marshalls.raw_to_base64(image.save_png_to_buffer())
    var atlas: Dictionary = {}
    for pattern in ["quarter|up|0,2","eighth|up|0,2"]:
        atlas[pattern] = {
            "source":"verovio-engraved-chord","units_per_space":250,
            "bounds":[-20.0,-200.0,120.0,250.0],
            "head_positions":[[0.0,0.0],[0.0,-250.0]],
            "png_base64":encoded,
            "heads_only":{"source":"verovio-engraved-chord-heads",
                "bounds":[-20.0,-190.0,120.0,160.0],
                "png_base64":encoded},
            "stem_only":{"source":"verovio-engraved-chord-stem",
                "bounds":[90.0,-800.0,6.0,790.0],
                "png_base64":encoded}}
    return atlas


# Test-only beam mask: production beams are extracted from the actual
# score SVG with their two original note identities and stem-tip offsets.
static func beam_catalogue() -> Dictionary:
    var image := Image.create(8,3,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    return {"d|e":{
        "source":"verovio-engraved-beam","units_per_space":250,
        "bounds":[100.0,-860.0,600.0,85.0],
        "span":650.0,"stem_up":true,
        "note_ids":["d","e"],"tip_offsets":[-860.0,-860.0],
        "head_offsets":[0.0,650.0],
        "png_base64":Marshalls.raw_to_base64(image.save_png_to_buffer())}}


static func tuplet_catalogue() -> Dictionary:
    var digits := Image.create(5,6,false,Image.FORMAT_RGBA8)
    digits.fill(Color.WHITE)
    var bars := Image.create(20,2,false,Image.FORMAT_RGBA8)
    bars.fill(Color.WHITE)
    return {"three0|three1|three2":{
        "source":"verovio-engraved-tuplet",
        "note_ids":["three0","three1","three2"],"span":500.0,
        "number":{"source":"verovio-tuplet-number",
            "units_per_space":250,"bounds":[220.0,-940.0,60.0,70.0],
            "png_base64":Marshalls.raw_to_base64(digits.save_png_to_buffer())},
        "bracket":{"source":"verovio-tuplet-bracket",
            "units_per_space":250,
            "bounds":[-5.0,-890.0,510.0,15.0],
            "png_base64":Marshalls.raw_to_base64(bars.save_png_to_buffer())}}}


static func slur_catalogue() -> Dictionary:
    var image := Image.create(30,6,false,Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    return {"n1|n3":{
        "source":"verovio-engraved-slur","units_per_space":250,
        "note_ids":["n1","n3"],"bounds":[12.0,-430.0,600.0,100.0],
        "span":625.0,"original_end_y":-180.0,
        "png_base64":Marshalls.raw_to_base64(image.save_png_to_buffer())}}
