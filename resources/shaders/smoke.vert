#version 330

uniform WindowBlock {
    mat4 projection;
    mat4 view;
} window;

uniform vec2 center;   // cloud centre, world space (px)
uniform vec2 size;     // cloud bounding-box width/height, world space (px)

in vec2 in_vert;   // unit quad corner, [-0.5, 0.5] per axis

out vec2 v_local;   // box-local coords in [-1, 1]
out vec2 v_world;

void main() {
    vec2 world_pos = center + in_vert * size;
    v_local = in_vert * 2.0;
    v_world = world_pos;
    gl_Position = window.projection * window.view * vec4(world_pos, 0.0, 1.0);
}
