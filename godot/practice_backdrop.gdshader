shader_type canvas_item;
render_mode unshaded;

// Screen-space interleaved gradient noise, stationary over time. A one
// 8-bit code-value peak-to-peak dither hides contour bands in dark teal.
float pixel_noise(vec2 pixel) {
    return fract(52.9829189 * fract(dot(floor(pixel), vec2(0.06711056, 0.00583715))));
}

void fragment() {
    vec2 offset = (UV - vec2(0.46, 0.47)) * vec2(1.14, 0.98);
    float distance_from_center = length(offset);
    // Broad continuous falloff without the old flat central region.
    float vignette = smoothstep(0.0, 0.96, distance_from_center);
    vec3 center = vec3(0.004, 0.120, 0.111);
    vec3 edge = vec3(0.002, 0.062, 0.059);
    vec3 base = mix(center, edge, vignette);
    float dither = (pixel_noise(FRAGCOORD.xy) - 0.5) / 255.0;
    COLOR = vec4(clamp(base + vec3(dither), vec3(0.0), vec3(1.0)), 1.0);
}
