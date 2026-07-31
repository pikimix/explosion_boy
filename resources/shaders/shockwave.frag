#version 330

// Supersonic-style shock ring: a sharp, near-instantaneous kick right at the
// leading edge, trailing off gradually behind it (nothing disturbed ahead of
// the front). Refracts the previously-rendered scene and fades out as the
// wave reaches the blast's horizontal radius.
uniform sampler2D scene;
uniform vec2 centre;       // blast origin, in UV space [0, 1]
uniform float aspect;      // scene width / height, corrects the ring to a circle
uniform float radius;      // current wavefront radius, in screen-height-normalised units
uniform float ring_width;  // width of the sharp leading edge, same units as radius
uniform float trail_length;  // how far the distortion trails behind the front, same units
uniform float strength;    // peak UV displacement at the leading edge
uniform float life_ratio;  // 1.0 when spawned -> 0.0 at end of life, drives the fade-out

in vec2 v_uv;
out vec4 out_colour;

void main() {
    vec2 diff = v_uv - centre;
    diff.x *= aspect;
    float dist = length(diff);

    // Signed distance behind the wavefront: >0 just inside/behind it (already
    // passed), <0 ahead of it (not yet reached, must stay undisturbed).
    float behind = radius - dist;

    // Thin, sharp spike exactly at the front — the rapid "crack" of the wave.
    float edge = 1.0 - smoothstep(0.0, ring_width, abs(behind));
    // Long, gradually-decaying tail following behind the front only.
    float tail = exp(-max(behind, 0.0) / trail_length) * step(0.0, behind);

    float band = max(edge, tail);

    vec2 dir = dist > 0.0001 ? diff / dist : vec2(0.0);
    vec2 dir_uv = vec2(dir.x / aspect, dir.y);

    // Sample from *behind* (towards the centre) rather than ahead: this pixel
    // then shows content that used to sit closer in, i.e. the scene reads as
    // matter shoved outward by the blast, not sucked in towards it.
    vec2 offset = dir_uv * band * strength * life_ratio;
    out_colour = texture(scene, v_uv - offset);
}
