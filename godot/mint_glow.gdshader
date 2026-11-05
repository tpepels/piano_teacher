shader_type canvas_item;
render_mode blend_add, unshaded;

// Local bloom approximation for the OpenGL Compatibility renderer.
// Does not require global HDR, a WorldEnvironment or screen sampling.
uniform vec4 tint : source_color = vec4(0.23, 0.99, 0.72, 1.0);
uniform int shape = 0; // 0 = playhead, 1 = transport, 2 = progress light
uniform float intensity : hint_range(0.0, 2.0) = 1.0;

void fragment() {
    vec2 p = UV * 2.0 - 1.0;
    float light = 0.0;
    if (shape == 0) {
        // Vertical profile: fine luminous core + middle halo + diffuse spill.
        // The first and last 8% taper, avoiding a rectangular light column.
        float x = abs(p.x);
        float core = exp(-pow(x / 0.037, 2.0));
        float close_halo = exp(-pow(x / 0.14, 2.0));
        float spill = exp(-pow(x / 0.49, 2.0));
        float vertical = smoothstep(0.0, 0.09, UV.y)
            * (1.0 - smoothstep(0.91, 1.0, UV.y));
        float midpoint = 0.78 + 0.22 * exp(-pow(p.y / 0.50, 2.0));
        light = (0.76 * core + 0.41 * close_halo + 0.21 * spill)
            * vertical * midpoint;
    } else if (shape == 1) {
        // Rounded rectangle signed-distance bloom. The previous clamp()
        // made EVERY pixel inside the oversized quad equally bright,
        // exposing a hard rectangular patch behind the button.
        vec2 half_box = vec2(0.69, 0.41);
        float radius = 0.115;
        vec2 q = abs(p) - half_box + vec2(radius);
        float sdf = length(max(q, vec2(0.0))) +
            min(max(q.x, q.y), 0.0) - radius;
        float outside = max(sdf, 0.0);
        float outer = exp(-pow(outside / 0.17, 2.0));
        float haze = exp(-pow(outside / 0.41, 2.0));
        float near_edge = exp(-pow(sdf / 0.18, 2.0));
        light = 0.40 * outer + 0.16 * haze + 0.09 * near_edge;
    } else {
        // Small circular flare for the actual progress position.
        float d2 = dot(p / vec2(0.78, 0.62), p / vec2(0.78, 0.62));
        light = 0.38 * exp(-3.0 * d2) + 0.35 * exp(-16.0 * d2);
    }
    // Exact zero at all quad edges. Avoids visible GPU shader rectangles,
    // also for the narrow progress lights and the vertical playhead.
    vec2 edge = 1.0 - abs(p);
    float feather = smoothstep(0.0, 0.10, min(edge.x, edge.y));
    float breathe = 0.95 + 0.05 * sin(TIME * 0.85);
    COLOR = vec4(tint.rgb,
        clamp(light * feather * intensity * breathe, 0.0, 1.0) * tint.a);
}
