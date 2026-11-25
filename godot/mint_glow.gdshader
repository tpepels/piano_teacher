shader_type canvas_item;
render_mode blend_add, unshaded;

// Local bloom approximation for the OpenGL Compatibility renderer.
// Does not require global HDR, a WorldEnvironment or screen sampling.
// Every shape fades smoothly to exactly zero well inside its quad, so no
// glow ever shows the quad's rectangle (owner report 2026-11-25).
uniform vec4 tint : source_color = vec4(0.23, 0.99, 0.72, 1.0);
uniform int shape = 0; // 0 = playhead, 1 = transport, 2 = progress light
uniform float intensity : hint_range(0.0, 2.0) = 1.0;
// Transport only: the quad and the button's half size, in pixels.
uniform vec2 quad_px = vec2(300.0, 100.0);
uniform vec2 box_half_px = vec2(140.0, 30.0);

void fragment() {
    vec2 p = UV * 2.0 - 1.0;
    float light = 0.0;
    if (shape == 0) {
        // Vertical line: a fine core and a close halo, tapered at both ends;
        // the halo has gone before the sides of the quad.
        float x = abs(p.x);
        float core = exp(-pow(x / 0.04, 2.0));
        float halo = exp(-pow(x / 0.16, 2.0));
        float sides = 1.0 - smoothstep(0.35, 0.9, x);
        float vertical = smoothstep(0.0, 0.12, UV.y)
            * (1.0 - smoothstep(0.88, 1.0, UV.y));
        light = (0.62 * core + 0.22 * halo) * sides * vertical;
    } else if (shape == 1) {
        // A soft rim just outside a rounded button, measured in pixels.
        vec2 at = (UV - 0.5) * quad_px;
        float radius = 8.0;
        vec2 q = abs(at) - box_half_px + vec2(radius);
        float outside = max(length(max(q, vec2(0.0))) + min(max(q.x, q.y), 0.0) - radius, 0.0);
        vec2 room = quad_px * 0.5 - box_half_px;
        float reach = max(1.0, min(room.x, room.y));
        float rim = exp(-pow(outside / (reach * 0.45), 2.0));
        vec2 to_edge = quad_px * 0.5 - abs(at);
        float window = smoothstep(0.0, reach * 0.8, min(to_edge.x, to_edge.y));
        light = 0.30 * rim * window;
    } else {
        // Small round flare for the actual progress position.
        float d = length(p);
        light = (0.30 * exp(-pow(d / 0.30, 2.0)) + 0.20 * exp(-pow(d / 0.12, 2.0)))
            * (1.0 - smoothstep(0.6, 1.0, d));
    }
    float breathe = 0.96 + 0.04 * sin(TIME * 0.85);
    COLOR = vec4(tint.rgb, clamp(light * intensity * breathe, 0.0, 1.0) * tint.a);
}
