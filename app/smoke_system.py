"""GLSL point-sprite particle system for smoke-bomb clouds.

Each active SmokeCloud gets a fixed pool of particles spawned once, with
random motion parameters (orbit anchor/radius/speed, or wind wander phase)
baked into a static per-vertex buffer. From then on nothing about a
particle is touched from Python — every frame this module only updates a
handful of small uniforms (elapsed time, every player's current
position/velocity, and each cloud's hold/fade value); the vertex shader
(smoke_particles.vert) does the entire simulation: orbiting, the wind
"push" from nearby players, per-particle turnover fade, and the local
player's hole cutout.

Rendering is two-pass, metaball-style, so the cloud reads as one joined,
rim-shaded shape rather than hundreds of individually-lit balls:

1. Density pass — every particle is rasterised as a soft circle into an
   offscreen buffer with additive blending (smoke_density.frag), so
   overlapping particles' discs sum into a single continuous field.
2. Composite pass — one full-screen shader (smoke_composite.frag)
   thresholds that field into the blob's silhouette and takes its
   gradient to find the true edge of the *joined* shape (near-zero deep
   inside an overlapping mass, large right at the boundary), driving the
   cel-shaded banding/outline only there.

If the driver does not support GLSL 3.30 (OpenGL 3.3) the system disables
itself silently so the rest of the game is unaffected.
"""
from __future__ import annotations

import array
import logging
import math
import random
import time as time_module
from pathlib import Path

import arcade
from arcade.gl import BufferDescription, Framebuffer
from arcade.gl.geometry import quad_2d_fs

from app.gfx_base import try_init_shader_effect
from core.state import GameState
from engine.config import TILE_SIZE

_log = logging.getLogger(__name__)

_SHADER_DIR = Path(__file__).parent.parent / 'resources' / 'shaders'

# Set to True by disable() before any GameView is created to skip all GL work.
_force_disabled: bool = False


def disable() -> None:
    """Permanently disable the smoke cloud effect (call before the first draw)."""
    global _force_disabled
    _force_disabled = True


_GL_PROGRAM_POINT_SIZE = 0x8642   # required on macOS core profile for gl_PointSize

_HOLE_RADIUS = TILE_SIZE          # 1 grid cell around the local player

# Matches MAX_PLAYERS(engine.config)/cloud-slot caps declared in the shader.
_MAX_PLAYERS = 16
_MAX_CLOUDS = 16
_MAX_PARTICLES = 1_000_000
_FLOATS_PER_PARTICLE = 11          # in_spawn(2), kind, amp, freq, phase, phase2, size, life_total, life_phase, slot
_BYTES_PER_PARTICLE = _FLOATS_PER_PARTICLE * 4

_DENSITY_PER_TILE = 64         # particles per grid cell of a cloud's area
_MAX_PARTICLES_PER_CLOUD = 48000
_ORBIT_FRACTION = 0.55

_SIZE_MIN, _SIZE_MAX = 11.0, 32.0
_LIFE_MIN, _LIFE_MAX = 1.4, 2.8    # seconds per turnover cycle

_ORBIT_RADIUS_MIN, _ORBIT_RADIUS_MAX = 6.0, 20.0
_ORBIT_SPEED_MIN, _ORBIT_SPEED_MAX = 0.5, 2.0    # rad/s

_WIND_AMP_MIN, _WIND_AMP_MAX = 8.0, 22.0
_WIND_FREQ_MIN, _WIND_FREQ_MAX = 0.15, 0.5       # rad/s, slow ambient wander

# Exponential smoothing rate (1/s) for player positions/velocities fed to
# the shader — state.player_physics only changes at server-tick rate, so
# this fills the gaps between ticks with continuous motion instead of the
# raw dict's discrete jumps. Higher = snappier but jumpier, lower = smoother
# but laggier.
_PLAYER_SMOOTH_RATE = 12.0

_PEAK_OPACITY = 0.97


def _random_point_in_disc(cx: float, cy: float, radius: float) -> tuple[float, float]:
    r = radius * math.sqrt(random.random())
    theta = random.uniform(0.0, 2.0 * math.pi)
    return cx + r * math.cos(theta), cy + r * math.sin(theta)


def _append_particle(
    buf: array.array, cx: float, cy: float, disc_radius: float, slot: int, is_orbit: bool,
) -> None:
    """Append one particle's seed directly into a flat float buffer.

    Building the upload buffer straight from these appends (rather than
    collecting per-particle lists and flattening them afterwards) matters
    once cloud populations run into the hundreds of thousands.
    """
    life_total = random.uniform(_LIFE_MIN, _LIFE_MAX)
    size = random.uniform(_SIZE_MIN, _SIZE_MAX)
    life_phase = random.random()
    if is_orbit:
        anchor_x, anchor_y = _random_point_in_disc(cx, cy, disc_radius * 0.85)
        amp = random.uniform(_ORBIT_RADIUS_MIN, _ORBIT_RADIUS_MAX)
        freq = random.uniform(_ORBIT_SPEED_MIN, _ORBIT_SPEED_MAX) * random.choice((-1.0, 1.0))
        kind = 0.0
        phase = random.uniform(0.0, 2.0 * math.pi)
        phase2 = 0.0
        spawn_x, spawn_y = anchor_x, anchor_y
    else:
        spawn_x, spawn_y = _random_point_in_disc(cx, cy, disc_radius)
        amp = random.uniform(_WIND_AMP_MIN, _WIND_AMP_MAX)
        freq = random.uniform(_WIND_FREQ_MIN, _WIND_FREQ_MAX)
        kind = 1.0
        phase = random.uniform(0.0, 2.0 * math.pi)
        phase2 = random.uniform(0.0, 2.0 * math.pi)

    buf.extend((
        spawn_x, spawn_y, kind, amp, freq, phase, phase2,
        size, life_total, life_phase, float(slot),
    ))


class SmokeCloudSystem:
    """Simulates and renders hundreds of point-sprite particles per active SmokeCloud."""

    def __init__(self) -> None:
        self._blocks: dict[tuple[int, int], array.array] = {}
        self._slot_of: dict[tuple[int, int], int] = {}
        self._free_slots: list[int] = list(range(_MAX_CLOUDS))
        self._fade: dict[tuple[int, int], float] = {}
        self._cloud_fade: tuple[float, ...] = tuple([0.0] * _MAX_CLOUDS)
        self._dirty = False
        self._start_time = time_module.monotonic()

        self._density_program = None
        self._composite_program = None
        self._composite_quad = None
        self._vbo = None
        self._geometry = None
        self._enabled: bool | None = None
        self._render_count = 0

        self._density_fbo: Framebuffer | None = None
        self._fbo_size: tuple[int, int] = (0, 0)

        self._local_player_pos = (-1.0e6, -1.0e6)
        self._other_pos: tuple[float, ...] = tuple([0.0] * (_MAX_PLAYERS * 2))
        self._other_vel: tuple[float, ...] = tuple([0.0] * (_MAX_PLAYERS * 2))
        self._other_count = 0
        # Smoothed towards state.player_physics each frame — that dict only
        # changes at server-tick rate, so feeding it to the shader straight
        # makes wind-pushed particles visibly snap between ticks instead of
        # flowing continuously.
        self._smoothed_players: dict[int, list[float]] = {}

    # ── Public interface ────────────────────────────────────────────────────

    def update(
        self,
        dt: float,
        state: GameState,
        local_id: int | None,
        player_x: float,
        player_y: float,
    ) -> None:
        """Track cloud spawn/despawn and refresh the small per-frame uniforms.

        No per-particle work happens here — that's entirely the vertex
        shader's job, driven by the values this stores.
        """
        active: dict[tuple[int, int], tuple[float, float, float, float]] = {}
        for cloud in state.smoke_clouds:
            key = (cloud.col, cloud.row)
            cx = cloud.col * TILE_SIZE + TILE_SIZE / 2
            cy = cloud.row * TILE_SIZE + TILE_SIZE / 2
            disc_radius = (cloud.radius * 2 + 1) * TILE_SIZE / 2
            life_ratio = 1.0 - (
                cloud.ticks_remaining / cloud.ticks_total if cloud.ticks_total else 0.0
            )
            active[key] = (cx, cy, disc_radius, life_ratio)

        for key in list(self._blocks):
            if key not in active:
                self._free_slots.append(self._slot_of.pop(key))
                del self._blocks[key]
                del self._fade[key]
                self._dirty = True

        for key, (cx, cy, disc_radius, life_ratio) in active.items():
            self._fade[key] = life_ratio
            if key not in self._blocks:
                if not self._free_slots:
                    continue  # more concurrent clouds than slots — drop, rare edge case
                slot = self._free_slots.pop()
                self._slot_of[key] = slot
                self._blocks[key] = self._spawn_particles(cx, cy, disc_radius, slot)
                self._dirty = True

        fade_array = [0.0] * _MAX_CLOUDS
        for key, slot in self._slot_of.items():
            fade_ratio = self._fade[key]
            fade_array[slot] = (
                _PEAK_OPACITY if fade_ratio < 0.5
                else _PEAK_OPACITY * (1.0 - (fade_ratio - 0.5) * 2.0)
            )
        self._cloud_fade = tuple(fade_array)

        lerp_t = min(1.0, dt * _PLAYER_SMOOTH_RATE) if dt > 0.0 else 1.0
        seen_pids: set[int] = set()
        other_pos = [0.0] * (_MAX_PLAYERS * 2)
        other_vel = [0.0] * (_MAX_PLAYERS * 2)
        count = 0
        for pid, phys in state.player_physics.items():
            seen_pids.add(pid)
            smoothed = self._smoothed_players.get(pid)
            if smoothed is None:
                smoothed = [phys.x, phys.y, phys.vx, phys.vy]
                self._smoothed_players[pid] = smoothed
            else:
                smoothed[0] += (phys.x - smoothed[0]) * lerp_t
                smoothed[1] += (phys.y - smoothed[1]) * lerp_t
                smoothed[2] += (phys.vx - smoothed[2]) * lerp_t
                smoothed[3] += (phys.vy - smoothed[3]) * lerp_t

            if count >= _MAX_PLAYERS:
                continue
            other_pos[count * 2], other_pos[count * 2 + 1] = smoothed[0], smoothed[1]
            other_vel[count * 2], other_vel[count * 2 + 1] = smoothed[2], smoothed[3]
            count += 1

        for pid in list(self._smoothed_players):
            if pid not in seen_pids:
                del self._smoothed_players[pid]

        self._other_pos = tuple(other_pos)
        self._other_vel = tuple(other_vel)
        self._other_count = count
        self._local_player_pos = (player_x, player_y)

    def draw(self) -> None:
        """Render every cloud in two passes: density-field, then cel-shaded composite."""
        if self._enabled is None:
            self._enabled = self._try_init()
        if not self._enabled or not self._blocks:
            return

        if self._dirty:
            buf: array.array = array.array('f')
            count = 0
            remaining = _MAX_PARTICLES
            for block in self._blocks.values():
                block_count = len(block) // _FLOATS_PER_PARTICLE
                take = min(block_count, remaining)
                if take <= 0:
                    break
                buf.extend(block[: take * _FLOATS_PER_PARTICLE])
                count += take
                remaining -= take
            self._vbo.write(buf.tobytes())
            self._render_count = count
            self._dirty = False

        if self._render_count == 0:
            return

        win = arcade.get_window()
        ctx = win.ctx
        width, height = win.width, win.height
        fbo = self._ensure_density_fbo(width, height)

        elapsed = time_module.monotonic() - self._start_time
        self._density_program['time'] = elapsed
        self._density_program['player_pos'] = self._local_player_pos
        self._density_program['hole_radius'] = _HOLE_RADIUS
        self._density_program['other_pos'] = self._other_pos
        self._density_program['other_vel'] = self._other_vel
        self._density_program['other_count'] = self._other_count
        self._density_program['cloud_fade'] = self._cloud_fade

        ctx.enable(_GL_PROGRAM_POINT_SIZE)
        saved_blend = ctx.blend_func

        with fbo.activate():
            fbo.clear(color=(0, 0, 0, 0))
            ctx.enable(ctx.BLEND)
            ctx.blend_func = ctx.ONE, ctx.ONE   # additive — overlapping particles sum
            self._geometry.render(self._density_program, mode=ctx.POINTS, vertices=self._render_count)
        # fbo.activate() restores whichever framebuffer was bound before this call.

        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.BLEND_DEFAULT
        fbo.color_attachments[0].use(0)
        self._composite_program['density_tex'] = 0
        self._composite_program['texel_size'] = (1.0 / width, 1.0 / height)
        self._composite_program['peak_opacity'] = _PEAK_OPACITY
        self._composite_quad.render(self._composite_program)
        ctx.blend_func = saved_blend

    # ── Internal helpers ────────────────────────────────────────────────────

    def _ensure_density_fbo(self, width: int, height: int) -> Framebuffer:
        if self._density_fbo is None or self._fbo_size != (width, height):
            ctx = arcade.get_window().ctx
            if self._density_fbo is not None:
                self._density_fbo.delete()
            texture = ctx.texture(
                (width, height),
                components=4,
                filter=(ctx.LINEAR, ctx.LINEAR),
                wrap_x=ctx.CLAMP_TO_EDGE,
                wrap_y=ctx.CLAMP_TO_EDGE,
            )
            self._density_fbo = ctx.framebuffer(color_attachments=[texture])
            self._fbo_size = (width, height)
        return self._density_fbo

    def _spawn_particles(
        self, cx: float, cy: float, disc_radius: float, slot: int,
    ) -> array.array:
        tiles = max(1, round((disc_radius * 2 / TILE_SIZE) ** 2))
        total = min(_MAX_PARTICLES_PER_CLOUD, max(40, round(_DENSITY_PER_TILE * tiles)))
        orbit_count = round(total * _ORBIT_FRACTION)

        buf: array.array = array.array('f')
        for _ in range(orbit_count):
            _append_particle(buf, cx, cy, disc_radius, slot, is_orbit=True)
        for _ in range(total - orbit_count):
            _append_particle(buf, cx, cy, disc_radius, slot, is_orbit=False)
        return buf

    def _try_init(self) -> bool:
        """Load the smoke shaders and allocate GPU resources.

        Returns False on any failure so the effect degrades gracefully.
        """
        def build(ctx) -> None:
            vert_src = (_SHADER_DIR / 'smoke_particles.vert').read_text()
            vert_src = vert_src.replace('__MAX_PLAYERS__', str(_MAX_PLAYERS))
            vert_src = vert_src.replace('__MAX_CLOUDS__', str(_MAX_CLOUDS))
            density_frag_src = (_SHADER_DIR / 'smoke_density.frag').read_text()
            self._density_program = ctx.program(
                vertex_shader=vert_src, fragment_shader=density_frag_src,
            )
            self._vbo = ctx.buffer(reserve=_MAX_PARTICLES * _BYTES_PER_PARTICLE, usage='dynamic')
            self._geometry = ctx.geometry([
                BufferDescription(
                    self._vbo,
                    '2f 1f 1f 1f 1f 1f 1f 1f 1f 1f',
                    [
                        'in_spawn', 'in_kind', 'in_amp', 'in_freq', 'in_phase',
                        'in_phase2', 'in_size', 'in_life_total', 'in_life_phase', 'in_slot',
                    ],
                )
            ])

            composite_vert_src = (_SHADER_DIR / 'smoke_composite.vert').read_text()
            composite_frag_src = (_SHADER_DIR / 'smoke_composite.frag').read_text()
            self._composite_program = ctx.program(
                vertex_shader=composite_vert_src, fragment_shader=composite_frag_src,
            )
            self._composite_quad = quad_2d_fs()

            ctx.enable(_GL_PROGRAM_POINT_SIZE)

        return try_init_shader_effect(
            _log, 'Smoke cloud effect', _force_disabled, build,
            success_label='Smoke particle system',
        )
