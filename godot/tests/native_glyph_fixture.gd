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
