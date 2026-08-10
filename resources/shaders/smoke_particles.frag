#version 330

in float v_alpha;
out vec4 out_colour;

void main() {
    // gl_PointCoord maps [0,1]^2 across the point sprite
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    float d = dot(uv, uv);
    if (d > 1.0) discard;   // clip to a circle

    // Soft radial falloff with a slightly darker core — hundreds of these
    // overlapping is what gives the cloud its volume, not any single one.
    float falloff = 1.0 - d;
    vec3 colour = mix(vec3(0.42, 0.42, 0.46), vec3(0.12, 0.12, 0.14), falloff);
    out_colour = vec4(colour, v_alpha * falloff * 0.65);
}
