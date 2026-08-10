#version 330

// All particle motion is computed here from a static per-particle seed
// (baked once at spawn) plus a handful of small uniforms updated every
// frame. Nothing about a particle's position is touched from Python after
// it spawns — this shader is the entire simulation.
uniform WindowBlock {
    mat4 projection;
    mat4 view;
} window;

uniform float time;         // seconds since the smoke system started
uniform vec2 player_pos;    // local player — the only actual reveal (hole cutout)
uniform float hole_radius;

// Every player's current position/velocity is fed in raw; "wind" particles
// react to whichever is live right now. This is a stateless approximation
// of wind, not an integrated physics simulation — there is no memory of
// past frames, so it can never drift or accumulate error.
// MAX_PLAYERS/MAX_CLOUDS are substituted by smoke_system.py at load time
// from its own constants, so the array sizes here can never drift out of
// sync with the flat uniform data Python actually uploads.
const int MAX_PLAYERS = __MAX_PLAYERS__;
uniform vec2 other_pos[MAX_PLAYERS];
uniform vec2 other_vel[MAX_PLAYERS];
uniform int other_count;

// Each active SmokeCloud gets one slot; its hold/fade curve (driven by the
// server's ticks_remaining/ticks_total) lives here so per-particle data
// never needs touching as the cloud ages.
const int MAX_CLOUDS = __MAX_CLOUDS__;
uniform float cloud_fade[MAX_CLOUDS];

in vec2 in_spawn;        // orbit anchor, or wind particle's base wander point
in float in_kind;        // 0 = bounded orbit, 1 = wind-blown
in float in_amp;         // orbit radius, or wind wander amplitude
in float in_freq;        // orbit angular speed, or wind wander frequency
in float in_phase;
in float in_phase2;      // second phase axis, wind particles only
in float in_size;
in float in_life_total;  // seconds per turnover cycle (fade in -> hold -> fade out -> repeat)
in float in_life_phase;  // 0..1, staggers turnover across the population
in float in_slot;        // index into cloud_fade for this particle's owning cloud

out float v_alpha;

void main() {
    vec2 pos;
    if (in_kind < 0.5) {
        float angle = in_phase + in_freq * time;
        pos = in_spawn + in_amp * vec2(cos(angle), sin(angle));
    } else {
        vec2 wander = in_amp * vec2(
            cos(in_freq * time + in_phase),
            sin(in_freq * 1.3 * time + in_phase2)
        );
        pos = in_spawn + wander;
        for (int i = 0; i < other_count; i++) {
            vec2 to_p = pos - other_pos[i];
            float d2 = dot(to_p, to_p);
            float speed = length(other_vel[i]);
            float push = exp(-d2 / 5000.0) * speed * 0.03;
            pos += normalize(to_p + vec2(0.001)) * push;
        }
    }

    // Repeating fade-in/hold/fade-out cycle per particle, staggered by
    // in_life_phase so the whole cloud doesn't pulse in sync.
    float cycle = fract(time / in_life_total + in_life_phase);
    float edge = 0.15;
    float turnover = clamp(min(cycle / edge, (1.0 - cycle) / edge), 0.0, 1.0);

    float dist = length(pos - player_pos);
    float hole = smoothstep(hole_radius * 0.85, hole_radius, dist);

    float fade = cloud_fade[int(in_slot + 0.5)];

    v_alpha = turnover * hole * fade;

    gl_Position = window.projection * window.view * vec4(pos, 0.0, 1.0);
    gl_PointSize = in_size;
}
