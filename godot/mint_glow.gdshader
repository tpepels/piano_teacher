shader_type canvas_item;
render_mode blend_add, unshaded;

// Local bloom approximation for the OpenGL Compatibility renderer.
// Does not require global HDR, a WorldEnvironment or screen sampling.
// Every shape fades smoothly to exactly zero well inside its quad, so no
// glow ever shows the quad's rectangle (owner report 2026-11-25).
uniform vec4 tint : source_color = vec4(0.23, 0.99, 0.72, 1.0);
uniform int shape = 0; // 0 = playhead, 1 = transport, 2 = progress light
uniform float intensity : hint_range(0.0, 2.0) = 1.0;
// Playhead and transport: the quad size; transport also uses button size.
uniform vec2 quad_px = vec2(300.0, 100.0);
uniform vec2 box_half_px = vec2(140.0, 30.0);

void fragment() {
    vec2 p = UV * 2.0 - 1.0;
    float light = 0.0;
    if (shape == 0) {
        // Continuous elongated capsule. Measure the distance beyond
        // the ends of the actual reading line in pixels, so changing
        // the staff height does not stretch or flatten its soft caps.
        vec2 at = abs((UV - 0.5) * quad_px);
        vec2 half_quad = quad_px * 0.5;
        float end_padding = min(38.0, half_quad.y);
        float beyond = max(0.0, at.y - (half_quad.y - end_padding));
        vec2 core_delta = vec2(at.x / 5.0, beyond / 11.0);
        vec2 halo_delta = vec2(at.x / 26.0, beyond / 23.0);
        float core = exp(-dot(core_delta, core_delta));
        float halo = exp(-dot(halo_delta, halo_delta));
        vec2 edge = at / max(half_quad, vec2(1.0));
        float window = (1.0 - smoothstep(0.70, 1.0, edge.x))
            * (1.0 - smoothstep(0.72, 1.0, beyond / max(end_padding, 1.0)));
        light = (0.40 * core + 0.19 * halo) * window;
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
    // Keep the reading axis steady. Other existing accent blooms retain
    // their subtle breathing animation.
    float breathe = shape == 0 ? 1.0 : 0.96 + 0.04 * sin(TIME * 0.85);
    float alpha = clamp(light * intensity * breathe, 0.0, 1.0) * tint.a;
    if (shape == 0) {
        // Stochastic rounding with a stationary pixel pattern. Exact
        // zero remains zero: dithering cannot reveal the bloom quad.
        float noise = fract(52.9829189 * fract(dot(floor(FRAGCOORD.xy),
            vec2(0.06711056, 0.00583715))));
        alpha = floor(alpha * 255.0 + noise) / 255.0;
    }
    COLOR = vec4(tint.rgb, alpha);
}
