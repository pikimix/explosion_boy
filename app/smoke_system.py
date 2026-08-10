"""GLSL point-sprite particle system for smoke-bomb clouds.

Each active SmokeCloud gets a fixed pool of particles spawned once, with
random motion parameters (orbit anchor/radius/speed, or wind wander phase)
baked into a static per-vertex buffer. From then on nothing about a
particle is touched from Python — every frame this module only updates a
handful of small uniforms (elapsed time, every player's current
position/velocity, and each cloud's hold/fade value); the vertex shader
(smoke_particles.vert) does the entire simulation: orbiting, the wind
"push" from nearby players, per-particle turnover fade, and the local
player's hole cutout. If the driver does not support GLSL 3.30
(OpenGL 3.3) the system disables itself silently so the rest of the game
is unaffected.
"""
from __future__ import annotations

import array
import logging
import math
import random
import time as time_module
from pathlib import Path

import arcade
from arcade.gl import BufferDescription

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

_DENSITY_PER_TILE = 260         # particles per grid cell of a cloud's area
_MAX_PARTICLES_PER_CLOUD = 48_000
_ORBIT_FRACTION = 0.55

_SIZE_MIN, _SIZE_MAX = 11.0, 20.0
_LIFE_MIN, _LIFE_MAX = 1.4, 2.8    # seconds per turnover cycle

_ORBIT_RADIUS_MIN, _ORBIT_RADIUS_MAX = 6.0, 20.0
_ORBIT_SPEED_MIN, _ORBIT_SPEED_MAX = 0.5, 2.0    # rad/s

_WIND_AMP_MIN, _WIND_AMP_MAX = 8.0, 22.0
_WIND_FREQ_MIN, _WIND_FREQ_MAX = 0.15, 0.5       # rad/s, slow ambient wander

_HOLD_OPACITY = 0.99


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

        self._program = None
        self._vbo = None
        self._geometry = None
        self._enabled: bool | None = None
        self._render_count = 0

        self._local_player_pos = (-1.0e6, -1.0e6)
        self._other_pos: tuple[float, ...] = tuple([0.0] * (_MAX_PLAYERS * 2))
        self._other_vel: tuple[float, ...] = tuple([0.0] * (_MAX_PLAYERS * 2))
        self._other_count = 0

    # ── Public interface ────────────────────────────────────────────────────

    def update(
        self,
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
                _HOLD_OPACITY if fade_ratio < 0.5
                else _HOLD_OPACITY * (1.0 - (fade_ratio - 0.5) * 2.0)
            )
        self._cloud_fade = tuple(fade_array)

        other_pos = [0.0] * (_MAX_PLAYERS * 2)
        other_vel = [0.0] * (_MAX_PLAYERS * 2)
        count = 0
        for phys in state.player_physics.values():
            if count >= _MAX_PLAYERS:
                break
            other_pos[count * 2] = phys.x
            other_pos[count * 2 + 1] = phys.y
            other_vel[count * 2] = phys.vx
            other_vel[count * 2 + 1] = phys.vy
            count += 1
        self._other_pos = tuple(other_pos)
        self._other_vel = tuple(other_vel)
        self._other_count = count
        self._local_player_pos = (player_x, player_y)

    def draw(self) -> None:
        """Upload the particle buffer (only if clouds spawned/despawned) and render."""
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

        elapsed = time_module.monotonic() - self._start_time
        self._program['time'] = elapsed
        self._program['player_pos'] = self._local_player_pos
        self._program['hole_radius'] = _HOLE_RADIUS
        self._program['other_pos'] = self._other_pos
        self._program['other_vel'] = self._other_vel
        self._program['other_count'] = self._other_count
        self._program['cloud_fade'] = self._cloud_fade

        ctx = arcade.get_window().ctx
        ctx.enable(_GL_PROGRAM_POINT_SIZE)
        saved_blend = ctx.blend_func
        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.BLEND_DEFAULT
        self._geometry.render(self._program, mode=ctx.POINTS, vertices=self._render_count)
        ctx.blend_func = saved_blend

    # ── Internal helpers ────────────────────────────────────────────────────

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
        """Load the smoke shader and allocate GPU resources.

        Returns False on any failure so the effect degrades gracefully.
        """
        def build(ctx) -> None:
            vert_src = (_SHADER_DIR / 'smoke_particles.vert').read_text()
            vert_src = vert_src.replace('__MAX_PLAYERS__', str(_MAX_PLAYERS))
            vert_src = vert_src.replace('__MAX_CLOUDS__', str(_MAX_CLOUDS))
            frag_src = (_SHADER_DIR / 'smoke_particles.frag').read_text()
            self._program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
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
            ctx.enable(_GL_PROGRAM_POINT_SIZE)

        return try_init_shader_effect(
            _log, 'Smoke cloud effect', _force_disabled, build,
            success_label='Smoke particle system',
        )
