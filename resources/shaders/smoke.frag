#version 330

// Every client independently cuts its own hole around its own player when
// drawing every cloud (including other players' smoke) — there is no
// server-side per-player visibility state.
uniform vec2 player_pos;
uniform float hole_radius;    // 1 grid cell, world units
uniform float life_ratio;     // 0 = fresh/opaque -> 1 = expired/transparent
uniform float edge_softness;  // fraction of half-extent softened at the boundary

in vec2 v_local;
in vec2 v_world;
out vec4 out_colour;

const float HOLD_OPACITY = 0.98;

void main() {
    // Radial distance from the cloud centre: 0 at the centre, 1 at the
    // edge of the AOE radius. Rendered as a circle (unlike the square
    // box-fill AOE used server-side for rubble/super bombs) so the
    // corners of the bounding quad stay transparent.
    float box_dist = length(v_local);
    float edge_alpha = 1.0 - smoothstep(1.0 - edge_softness, 1.0, box_dist);

    float hole_dist = length(v_world - player_pos);
    float hole_alpha = smoothstep(hole_radius * 0.85, hole_radius, hole_dist);

    // First half of the cloud's life: held at HOLD_OPACITY. Second half:
    // faded linearly down to 0. The two phases are equal length — see
    // _spawn_smoke_cloud, which sizes ticks_total to exactly double the
    // hold duration for this purpose.
    float fade = life_ratio < 0.5
        ? HOLD_OPACITY
        : HOLD_OPACITY * (1.0 - (life_ratio - 0.5) * 2.0);

    float alpha = fade * edge_alpha * hole_alpha;
    if (alpha <= 0.0) {
        discard;
    }
    out_colour = vec4(0.0, 0.0, 0.0, alpha);
}
