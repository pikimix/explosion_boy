#version 330

// Pass 1 of the metaball-style smoke render: write each particle as a
// soft circle, weighted by v_alpha (turnover/hole/fade combined). Drawn
// with additive blending, so overlapping particles' discs sum into one
// continuous field — smoke_composite.frag reads that field back in pass 2
// to find the true edge of the joined shape.
in float v_alpha;
out vec4 out_colour;

void main() {
    vec2 uv = gl_PointCoord * 2.0 - 1.0;
    float d2 = dot(uv, uv);
    if (d2 > 1.0) discard;

    float density = v_alpha * (1.0 - d2);
    out_colour = vec4(density, density, density, density);
}
