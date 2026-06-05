#version 330

in float v_life;
out vec4 out_colour;

void main() {
    // gl_PointCoord maps [0,1]^2 across the point sprite
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    float d = dot(uv, uv);
    if (d > 1.0) discard;   // clip to a circle

    float r = sqrt(d);

    // White-hot core that shifts to deep orange-red as the particle ages.
    // The inner 30 % of the disc is held near white for a bright spark look.
    vec3 core  = vec3(1.0, 0.95, 0.7);           // near-white hot core
    vec3 fresh = vec3(1.0, 0.55, 0.05);           // orange when alive
    vec3 old   = vec3(0.75, 0.08, 0.0);           // dark red when fading
    vec3 col   = mix(mix(old, fresh, v_life), core, max(0.0, 1.0 - r * 3.3));

    // Smooth, fairly opaque disc that fades with age
    float alpha = (1.0 - r * r) * min(1.0, v_life * 2.5);
    out_colour = vec4(col, alpha);
}
