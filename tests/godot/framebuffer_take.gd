extends RefCounted
## Put a loaded score on screen for a framebuffer harness through the
## production stream queue. A freshly loaded score has no visible ink: READY
## and unreserved transports hold their take offscreen until Play arms it.
## The harness therefore admits one take, queued while the world axis is still
## far behind it, exactly as a framebuffer audit of the moving score needs (see
## native_verovio_overlay.gd), then presents frames until every retained strip
## has compiled and been attached. The take's world origin is beat 0, or, for
## a repeated pass shown at a later visual clock, the world position at which
## that pass begins.

static func show(tree: SceneTree, renderer: Control, state: Dictionary,
        clock: float, visual_clock: float = NAN) -> void:
    var world: float = visual_clock if is_finite(visual_clock) else clock
    if renderer._stream_queue.online.is_empty():
        var origin: float = world - clock
        renderer.stream_world_beat = origin - maxf(100.0, renderer.timeline.duration_beats + 30.0)
        renderer._stream_add_take(0.0, origin, 0.0, "framebuffer-audit")
    for settle in range(40):
        renderer.present(state, clock, visual_clock)
        renderer.present_flow(world, state, clock)
        await tree.process_frame
        if settle >= 1 and renderer.retained_ready():
            break

## Re-record every retained strip after a harness changed the score's events or
## geometry in place. Redrawing the parent only moves already compiled ink.
static func recompile(tree: SceneTree, renderer: Control, state: Dictionary,
        clock: float, visual_clock: float = NAN) -> void:
    renderer._invalidate_retained_segments()
    await show(tree, renderer, state, clock, visual_clock)
