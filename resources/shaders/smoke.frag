#version 330

// Every client independently cuts its own hole around its own player when
// drawing every cloud (including other players' smoke) — there is no
// server-side per-player visibility state.
uniform vec2 player_pos;
uniform float hole_radius;    // 1 grid cell, world units
uniform float life_ratio;     // 0 = fresh/opaque -> 1 = expired/transparent
uniform float edge_softness;  // fraction of half-extent softened at the boundary
uniform float time;           // seconds since the smoke system started, for billow drift

// Other players' positions/velocities push the noise field around as they
// walk through the cloud — a visual tell without revealing them, since
// only the local player's hole (below) is an actual reveal.
const int MAX_FLOW_SOURCES = 8;
uniform vec2 flow_pos[MAX_FLOW_SOURCES];
uniform vec2 flow_vel[MAX_FLOW_SOURCES];
uniform int flow_count;

in vec2 v_local;
in vec2 v_world;
out vec4 out_colour;

const float HOLD_OPACITY = 0.99;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float value_noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
    float sum = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        sum += amp * value_noise(p);
        p *= 2.03;
        amp *= 0.5;
    }
    return sum;
}

void main() {
    // Radial distance from the cloud centre: 0 at the centre, 1 at the
    // edge of the AOE radius. Rendered as a circle (unlike the square
    // box-fill AOE used server-side for rubble/super bombs) so the
    // corners of the bounding quad stay transparent.
    float box_dist = length(v_local);
    float edge_alpha = 1.0 - smoothstep(1.0 - edge_softness, 1.0, box_dist);

    // Base billow: the noise field itself scrolls steadily so the cloud
    // reads as alive/moving even with nobody walking through it.
    vec2 drift = vec2(sin(time * 0.2) * 8.0, time * 14.0);
    vec2 sample_pos = v_world * 0.028 - drift * 0.05;

    // Each other player nearby drags the noise field along with their
    // velocity, so the smoke visibly parts/flows around them without any
    // change to alpha — they stay exactly as hidden as before.
    for (int i = 0; i < flow_count; i++) {
        vec2 to_src = v_world - flow_pos[i];
        float d = length(to_src);
        float speed = length(flow_vel[i]);
        float influence = exp(-d / (hole_radius * 2.0)) * min(speed, 200.0) * 0.002;
        sample_pos += normalize(to_src + vec2(0.001)) * influence;
    }

    float density = fbm(sample_pos);
    density = smoothstep(0.15, 0.9, density);

    // The local player's own hole is a plain circle — the only reveal
    // this shader performs.
    float hole_dist = length(v_world - player_pos);
    float hole_alpha = smoothstep(hole_radius * 0.85, hole_radius, hole_dist);

    // First half of the cloud's life: held at HOLD_OPACITY. Second half:
    // faded linearly down to 0. The two phases are equal length — see
    // _spawn_smoke_cloud, which sizes ticks_total to exactly double the
    // hold duration for this purpose.
    float fade = life_ratio < 0.5
        ? HOLD_OPACITY
        : HOLD_OPACITY * (1.0 - (life_ratio - 0.5) * 2.0);

    // Density only shades the cloud — it never drags alpha low enough to
    // see through it, so the effect reads as texture, not transparency.
    float alpha = fade * edge_alpha * hole_alpha * mix(0.95, 1.0, density);
    if (alpha <= 0.01) {
        discard;
    }

    // Kept dark even at its lightest so the cloud reads as solid against
    // light tile backgrounds — the old flat black had this for free by
    // being pure black; a lighter grey here blends into the background
    // and reads as see-through even at the same alpha.
    vec3 colour = mix(vec3(0.34, 0.34, 0.37), vec3(0.08, 0.08, 0.1), density);
    out_colour = vec4(colour, alpha);
}
