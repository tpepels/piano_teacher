extends Control

# Purely decorative, non-interactive musical stage behind the genuine
# Verovio raster. Nothing here represents assessed notes or timing.
const AURA := Color("#69E2BF")
const ERROR := Color("#EF7776")
const AMBER := Color("#F0BC76")

var phase := "ready"
var progress := 0.0
var accent := AURA

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func present(state: Dictionary) -> void:
    var next_phase: String = str(state.get("phase", "ready"))
    var next_progress: float = clampf(float(state.get("progress", 0.0)), 0.0, 1.0)
    var next_accent: Color = (
        ERROR if next_phase == "feedback" and not bool(state.get("take_result", {}).get("clean", false))
        else AMBER if next_phase in ["paused", "recovering"]
        else AURA)
    if phase != next_phase or absf(next_progress-progress) > 0.003 or accent != next_accent:
        phase = next_phase
        progress = next_progress
        accent = next_accent
        queue_redraw()

func _draw() -> void:
    var w: float = size.x
    var h: float = size.y
    if w < 1 or h < 1:
        return
    # Nearly-black velvet piano-finish surface, with a soft center lift
    # so the score ink stays readable. No full-screen image or noise.
    for i in range(32):
        var y := h * float(i) / 32.0
        var lift := 1.0 - absf(float(i) - 14.0) / 25.0
        draw_rect(Rect2(0, y, w, h / 32.0 + 1),
            Color("#101B1D").lerp(Color("#1A2929"), clampf(lift * .75, 0.0, 1.0)))
    # A faint acoustic-console grid. It is behind the sheet, not painted
    # onto its noteheads or collision targets.
    var step := 96.0
    for x_index in range(1, int(ceil(w / step))):
        var x := float(x_index) * step
        draw_line(Vector2(x, 0), Vector2(x, h),
            Color("#759D94", .055), 1.0)
    for row in range(1, 5):
        var y := h * float(row) / 5.0
        draw_line(Vector2(0, y), Vector2(w, y),
            Color("#759D94", .035), 1.0)
    # Hairline border and eight short, instrument-like corner brackets.
    var border := Color(accent, .2)
    draw_rect(Rect2(1, 1, w - 2, h - 2), border, false, 1.0)
    var trim := Color(accent, .62)
    var length := minf(42.0, w * .14)
    for x in [2.0, w - 2.0]:
        for y in [2.0, h - 2.0]:
            var horizontal := 1.0 if x < w / 2.0 else -1.0
            var vertical := 1.0 if y < h / 2.0 else -1.0
            draw_line(Vector2(x, y), Vector2(x + horizontal * length, y), trim, 2.0)
            draw_line(Vector2(x, y), Vector2(x, y + vertical * minf(length, h * .18)), trim, 2.0)
    # Tiny in-stage transport rail, not a competing website progress bar.
    draw_rect(Rect2(1, h - 4, maxf(0, w - 2), 2), Color("#789B90", .18))
    if progress > 0:
        draw_rect(Rect2(1, h - 4, maxf(0, (w - 2) * progress), 2),
            Color(accent, .92))
