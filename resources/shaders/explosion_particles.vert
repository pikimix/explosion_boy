#version 330

uniform WindowBlock {
    mat4 projection;
    mat4 view;
} window;

in vec2 in_pos;
in float in_life;   // normalised lifetime: 1.0 = freshly spawned, 0.0 = dead
in float in_size;   // base point size in screen pixels

out float v_life;

void main() {
    v_life = in_life;
    gl_Position = window.projection * window.view * vec4(in_pos, 0.0, 1.0);
    // Shrink the point as the particle ages
    gl_PointSize = in_size * (0.3 + 0.7 * in_life);
}
