"""GLSL point-sprite particle system for explosion visual effects.

Particles are CPU-simulated and rendered via a custom GLSL shader loaded
from resources/shaders/. If the driver does not support GLSL 3.30
(OpenGL 3.3) the system disables itself silently so the rest of the game
is unaffected.
"""
from __future__ import annotations

import array
import logging
import math
import random
from pathlib import Path

import arcade
from arcade.gl import BufferDescription

from core.state import GameState
from engine.config import TILE_SIZE

_log = logging.getLogger(__name__)

_SHADER_DIR = Path(__file__).parent.parent / 'resources' / 'shaders'

# Set to True by disable() before any GameView is created to skip all GL work.
_force_disabled: bool = False


def disable() -> None:
    """Permanently disable the particle system (call before the first draw)."""
    global _force_disabled
    _force_disabled = True

# GL_PROGRAM_POINT_SIZE — required on macOS OpenGL core profile so that
# the vertex shader's gl_PointSize assignment actually takes effect.
_GL_PROGRAM_POINT_SIZE = 0x8642

_MAX_PARTICLES = 5_000
_BYTES_PER_PARTICLE = 4 * 4        # x, y, life_ratio, size — four floats

_COUNT_CENTER = 35
_COUNT_RAY_CELL = 12

_LIFETIME_MIN = 0.30
_LIFETIME_MAX = 0.75
_SPEED_MIN = 80.0
_SPEED_MAX = 360.0
_SIZE_MIN = 14.0
_SIZE_MAX = 32.0
_DRAG = 2.5                        # velocity multiplied by (1 - DRAG * dt) each frame


class ExplosionParticleSystem:
    """Manages point-sprite particles emitted when explosion cells first appear."""

    def __init__(self) -> None:
        # Each entry: [x, y, vx, vy, life_remaining, max_life, size]
        self._particles: list[list[float]] = []
        # Tracks cells that have already had particles emitted this explosion
        self._seen_cells: set[tuple[int, int]] = set()

        # GL resources — created lazily on first draw()
        self._program = None
        self._vbo = None
        self._geometry = None
        # None = not yet attempted; True = ready; False = permanently disabled
        self._enabled: bool | None = None

    # ── Public interface ──────────────────────────────────────────────────────

    def update(self, dt: float, state: GameState) -> None:
        """Emit particles for newly-seen explosion cells and advance all particles."""
        current_cells: set[tuple[int, int]] = set()

        for exp in state.explosions:
            cell = (exp.col, exp.row)
            current_cells.add(cell)
            if cell not in self._seen_cells:
                self._seen_cells.add(cell)
                self._emit(
                    exp.col * TILE_SIZE + TILE_SIZE / 2,
                    exp.row * TILE_SIZE + TILE_SIZE / 2,
                    _COUNT_CENTER,
                )

        for ray in state.explosion_rays:
            dc, dr = ray.direction
            for i in range(1, ray.length + 1):
                col = ray.origin_col + dc * i
                row = ray.origin_row + dr * i
                cell = (col, row)
                current_cells.add(cell)
                if cell not in self._seen_cells:
                    self._seen_cells.add(cell)
                    self._emit(
                        col * TILE_SIZE + TILE_SIZE / 2,
                        row * TILE_SIZE + TILE_SIZE / 2,
                        _COUNT_RAY_CELL,
                    )

        # Remove cells that have left all explosions so re-explosions re-emit
        self._seen_cells &= current_cells

        # Integrate physics and cull dead particles
        drag = max(0.0, 1.0 - _DRAG * dt)
        surviving = []
        for p in self._particles:
            p[4] -= dt
            if p[4] > 0.0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[2] *= drag
                p[3] *= drag
                surviving.append(p)
        self._particles = surviving

    def draw(self) -> None:
        """Upload particle positions to the GPU and render them."""
        if self._enabled is None:
            self._enabled = self._try_init()
        if not self._enabled or not self._particles:
            return

        # Pack interleaved float data: x, y, life_ratio, size
        buf: array.array = array.array('f')
        for p in self._particles:
            x, y, _vx, _vy, life, max_life, size = p
            buf.extend((x, y, life / max_life, size))

        n = len(self._particles)
        self._vbo.write(buf.tobytes())

        ctx = arcade.get_window().ctx
        # Re-enable each frame: Arcade's enable_only() calls can clear it.
        ctx.enable(_GL_PROGRAM_POINT_SIZE)
        saved_blend = ctx.blend_func
        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.BLEND_DEFAULT
        self._geometry.render(self._program, mode=ctx.POINTS, vertices=n)
        ctx.blend_func = saved_blend

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _emit(self, cx: float, cy: float, count: int) -> None:
        for _ in range(count):
            if len(self._particles) >= _MAX_PARTICLES:
                break
            angle = random.uniform(0.0, 2.0 * math.pi)
            speed = random.uniform(_SPEED_MIN, _SPEED_MAX)
            life = random.uniform(_LIFETIME_MIN, _LIFETIME_MAX)
            size = random.uniform(_SIZE_MIN, _SIZE_MAX)
            # Scatter spawn positions across the tile
            ox = random.uniform(-TILE_SIZE * 0.3, TILE_SIZE * 0.3)
            oy = random.uniform(-TILE_SIZE * 0.3, TILE_SIZE * 0.3)
            self._particles.append([
                cx + ox, cy + oy,
                math.cos(angle) * speed, math.sin(angle) * speed,
                life, life, size,
            ])

    def _try_init(self) -> bool:
        """Load shaders, compile them, and allocate GPU resources.

        Returns False on any failure so the system degrades gracefully.
        """
        if _force_disabled:
            _log.info('Particle system disabled via --no-shader flag.')
            return False

        ctx = arcade.get_window().ctx
        gl_ver: tuple[int, int] | None = getattr(ctx, 'gl_version', None)
        if gl_ver is not None and gl_ver < (3, 3):
            _log.warning(
                'Particle system disabled — OpenGL %d.%d detected, 3.3 required.',
                *gl_ver,
            )
            return False
        try:
            vert_src = (_SHADER_DIR / 'explosion_particles.vert').read_text()
            frag_src = (_SHADER_DIR / 'explosion_particles.frag').read_text()
            self._program = ctx.program(
                vertex_shader=vert_src,
                fragment_shader=frag_src,
            )
            self._vbo = ctx.buffer(
                reserve=_MAX_PARTICLES * _BYTES_PER_PARTICLE,
                usage='dynamic',
            )
            self._geometry = ctx.geometry(
                [BufferDescription(self._vbo, '2f 1f 1f', ['in_pos', 'in_life', 'in_size'])]
            )
            ctx.enable(_GL_PROGRAM_POINT_SIZE)
            if gl_ver is not None:
                _log.info('Explosion particle system initialised (OpenGL %d.%d).', *gl_ver)
            else:
                _log.info('Explosion particle system initialised.')
            return True
        except Exception:
            _log.warning(
                'Particle system disabled — shader load or compilation failed.',
                exc_info=True,
            )
            return False
