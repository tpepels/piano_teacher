extends SceneTree

# Phase 8I: exercise bounded GPU residency without fake scoring or a
# pre-rendered preview. Uses real Godot ImageTexture resources, and the
# production app's exact residency path.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        set_process(false)

var failures: Array[String] = []

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("TILE_RESIDENCY_FAIL:", description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var app := FixtureApp.new()
    root.add_child(app)
    await process_frame

    var tile_image := Image.create(48, 32, false, Image.FORMAT_LA8)
    tile_image.fill(Color(1, 1, 1, 0))
    tile_image.set_pixel(2, 2, Color(0, 0, 0, 1))
    var raw: PackedByteArray = tile_image.get_data()
    var packed: PackedByteArray = raw.compress(FileAccess.COMPRESSION_FASTLZ)
    check(not packed.is_empty(), "Lossless packing must be available")
    var tile_count := 80
    for i in range(tile_count):
        app.strip_tiles.append({
            "rect": Rect2(i * 48, 0, 48, 32),
            "image_size": Vector2i(48, 32),
            "upload_bytes": raw.size(),
            "packed_ink": packed,
        })
        var tile := TextureRect.new()
        app.score_tiles.append(tile)
        app.add_child(tile)
    app.deferred_tile_mode = true

    var seeks: Array[int] = [0, 1, 10, 73, 20, 79, 42, 0, 30, 78]
    for target in seeks:
        check(app._set_tile_residency(Vector2i(target, target + 1)),
            "Every legitimate seek must restore its source ink")
        var start: int = maxi(0, target - 2)
        var end: int = mini(tile_count, target + 3)
        check(app.resident_tile_begin == start and
            app.resident_tile_end == end, "Keep only two systems around playhead")
        check(app.resident_tile_bytes == (end - start) * raw.size(),
            "Actual resident bytes equal exactly the uploaded LA8 tiles")
        for i in range(tile_count):
            var active: bool = app.score_tiles[i].texture != null
            check(active == (i >= start and i < end),
                "A seek cannot leave offscreen GPU textures behind")
        check(app.score_tiles[target].texture != null and
            app.score_tiles[target].texture.get_image().get_pixel(2, 2).a > .98,
            "Restored real image must have the exact source note ink")

    var restores_before: int = app.restored_tile_count
    check(app._set_tile_residency(Vector2i(78, 79)),
        "Repeated camera window remains valid")
    check(app.restored_tile_count == restores_before,
        "Stable view must not re-decode or re-upload any image")

    check(app._set_tile_residency(Vector2i(20, 21)),
        "Prepare a known valid score for the corruption test")
    var stored_begin: int = app.resident_tile_begin
    var stored_end: int = app.resident_tile_end
    var stored_bytes: int = app.resident_tile_bytes
    var kept_texture: Texture2D = app.score_tiles[20].texture
    var safe_tile: Dictionary = app.strip_tiles[50]
    var damaged: Dictionary = safe_tile.duplicate()
    damaged["packed_ink"] = PackedByteArray()
    app.strip_tiles[50] = damaged
    check(not app._set_tile_residency(Vector2i(50, 51)),
        "Corrupted note ink must fail instead of displaying an empty staff")
    check(app.resident_tile_begin == stored_begin and
        app.resident_tile_end == stored_end and app.resident_tile_bytes == stored_bytes,
        "Failed seek cannot evict the existing visible score")
    check(app.score_tiles[20].texture == kept_texture,
        "Failed seek must keep the previously displayed GPU notation")
    app.strip_tiles[50] = safe_tile
    check(app._set_tile_residency(Vector2i(50, 51)),
        "Retry with original ink must recover a complete rendered score")
    check(app.score_tiles[50].texture != null,
        "Recovered tile must be drawable immediately")

    print("TILE_RESIDENCY_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
