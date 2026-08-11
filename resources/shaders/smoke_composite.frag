#version 330

// Pass 2 of the metaball-style smoke render: read back the density field
// every particle wrote into in pass 1 (smoke_density.frag) and shade it
// as one joined shape. A central-difference gradient of that field
// approximates its outward 2D normal — near-zero deep inside an
// overlapping mass (density has saturated and gone flat), large right at
// the true boundary of the joined blob — so only real edges get the
// cel-shaded banding/outline, regardless of any one particle's own
// position or silhouette.
uniform sampler2D density_tex;
uniform vec2 texel_size;   // 1/width, 1/height of density_tex

in vec2 v_uv;
out vec4 out_colour;

const int SHADE_BANDS = 3;
const vec3 SHADOW_COLOUR    = vec3(0.10, 0.10, 0.12);
const vec3 MID_COLOUR       = vec3(0.30, 0.30, 0.34);
const vec3 HIGHLIGHT_COLOUR = vec3(0.62, 0.62, 0.68);
const vec3 OUTLINE_COLOUR   = vec3(0.04, 0.04, 0.05);

void main() {
    float density = texture(density_tex, v_uv).r;

    // Below this, there is no smoke at all; the transition band above it
    // is where the blob's true silhouette lives.
    float inside = smoothstep(0.12, 0.30, density);
    if (inside <= 0.001) discard;

    float dx = texture(density_tex, v_uv + vec2(texel_size.x, 0.0)).r
             - texture(density_tex, v_uv - vec2(texel_size.x, 0.0)).r;
    float dy = texture(density_tex, v_uv + vec2(0.0, texel_size.y)).r
             - texture(density_tex, v_uv - vec2(0.0, texel_size.y)).r;
    vec2 grad = vec2(dx, dy);
    float grad_mag = length(grad);

    // Light from the game view's upper-left corner. Texture UV space has
    // (0,0) at the bottom-left, so "up" is +y and "left" is -x here.
    vec2 light_dir2d = normalize(vec2(-0.7, 0.7));
    vec2 normal2d = grad_mag > 0.0001 ? -grad / grad_mag : vec2(0.0);
    float lit = clamp(dot(normal2d, light_dir2d) * 0.5 + 0.5, 0.0, 0.999);

    float band = floor(lit * float(SHADE_BANDS)) / float(SHADE_BANDS - 1);
    vec3 shaded = band < 0.5
        ? mix(SHADOW_COLOUR, MID_COLOUR, band * 2.0)
        : mix(MID_COLOUR, HIGHLIGHT_COLOUR, (band - 0.5) * 2.0);

    // Only pixels where the field is actually changing fast — the real
    // overlap boundary — get lit/shadowed and outlined. A flat interior
    // (saturated, near-zero gradient) collapses to one joined colour.
    float edge_strength = smoothstep(0.0, 0.35, grad_mag * 12.0);
    vec3 colour = mix(MID_COLOUR, shaded, edge_strength);

    // The outline is a *shadow-side* rim, not a ring around the whole
    // silhouette — it only shows where the edge also faces away from the
    // light (low lit), so the top-left rim stays a clean highlight and
    // only the bottom-right rim darkens.
    float shadow_side = 1.0 - smoothstep(0.35, 0.65, lit);
    float outline_amount = smoothstep(0.55, 0.75, edge_strength) * shadow_side;
    colour = mix(colour, OUTLINE_COLOUR, outline_amount);

    out_colour = vec4(colour, inside);
}
