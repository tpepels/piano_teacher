extends RefCounted
## Screen routing only. Leaving Practice requests an idempotent backend
## suspension; phase, pending action and musical pause eligibility belong
## exclusively to Python's locked control projection.

static func plan(target: String, previous: String) -> Dictionary:
    if target == "home":
        target = "practice"
    return {
        "target": target,
        "previous": previous,
        "remember_settings": target == "settings" and previous != "settings",
        "suspend": previous == "practice" and target != "practice",
    }
