#version 330

// Screen-aligned full-screen quad (see arcade.gl.geometry.quad_2d_fs).
in vec2 in_vert;
in vec2 in_uv;

out vec2 v_uv;

void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
