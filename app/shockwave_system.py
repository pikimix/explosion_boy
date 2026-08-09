"""Full-screen radial shockwave effect triggered when a super bomb explodes.

The scene is captured into an offscreen framebuffer and warped by a
GLSL shader that refracts pixels within an expanding ring and fades the
effect out once the ring reaches the blast's horizontal radius. If the
driver does not support GLSL 3.30 (OpenGL 3.3) the effect disables itself
silently so the rest of the game is unaffected.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import arcade
from arcade.gl import Framebuffer
from arcade.gl.geometry import quad_2d_fs

from app.gfx_base import try_init_shader_effect
from core.state import GameState
from engine.config import (
    SHOCKWAVE_DISTORTION_STRENGTH, SHOCKWAVE_LIFETIME_SECONDS,
    SHOCKWAVE_RING_WIDTH, SHOCKWAVE_TRAIL_LENGTH, SHOCKWAVE_TRAVEL_FRACTION,
    TILE_SIZE,
)

_log = logging.getLogger(__name__)

_SHADER_DIR = Path(__file__).parent.parent / 'resources' / 'shaders'

# Set to True by disable() before any GameView is created to skip all GL work.
_force_disabled: bool = False


def disable() -> None:
    """Permanently disable the shockwave effect (call before the first draw)."""
    global _force_disabled
    _force_disabled = True


class _ActiveShockwave:
    """One in-flight shockwave: its origin, target radius, and remaining life.

    The wave travels out to max_radius at full strength across the first
    SHOCKWAVE_TRAVEL_FRACTION of its lifetime, then holds at max_radius and
    fades to nothing over the remainder — it stays strong until it reaches
    the blast radius, then dissipates, rather than fading the whole time
    it's travelling out.
    """

    __slots__ = ('cx', 'cy', 'max_radius', 'start_time', 'lifetime')

    def __init__(self, cx: float, cy: float, max_radius: float, lifetime: float) -> None:
        self.cx = cx
        self.cy = cy
        self.max_radius = max_radius
        self.start_time = time.monotonic()
        self.lifetime = lifetime

    def _age_ratio(self) -> float:
        """Fraction of the shockwave's lifetime elapsed, clamped to [0, 1]."""
        if self.lifetime <= 0.0:
            return 1.0
        return min(1.0, (time.monotonic() - self.start_time) / self.lifetime)

    def radius_ratio(self) -> float:
        """Fraction of max_radius the wavefront has reached, clamped to [0, 1]."""
        age = self._age_ratio()
        if age >= SHOCKWAVE_TRAVEL_FRACTION:
            return 1.0
        return age / SHOCKWAVE_TRAVEL_FRACTION

    def strength_ratio(self) -> float:
        """Distortion strength: 1.0 throughout the travel phase, fading to 0.0 after."""
        age = self._age_ratio()
        if age <= SHOCKWAVE_TRAVEL_FRACTION:
            return 1.0
        dissipate_span = 1.0 - SHOCKWAVE_TRAVEL_FRACTION
        if dissipate_span <= 0.0:
            return 0.0
        return 1.0 - (age - SHOCKWAVE_TRAVEL_FRACTION) / dissipate_span

    def is_dead(self) -> bool:
        return self._age_ratio() >= 1.0


class ShockwaveSystem:
    """Detects super-bomb detonations and renders the resulting screen warp."""

    def __init__(self, lifetime: float = SHOCKWAVE_LIFETIME_SECONDS) -> None:
        self.lifetime = lifetime
        self._active: list[_ActiveShockwave] = []
        # Super bombs present on the *previous* update, keyed by cell — the
        # server removes a detonating bomb the same tick its explosion
        # appears, so this must be captured before that tick's bombs list
        # overwrites it.
        self._known_super_bombs: dict[tuple[int, int], int] = {}
        self._seen_centers: set[tuple[int, int]] = set()

        # GL resources — created lazily on first draw()
        self._program = None
        self._quad = None
        self._scene_fbo: Framebuffer | None = None
        self._ping_fbo: Framebuffer | None = None
        self._fbo_size: tuple[int, int] = (0, 0)
        # None = not yet attempted; True = ready; False = permanently disabled
        self._enabled: bool | None = None

    # ── Public interface ──────────────────────────────────────────────────────

    def update(self, state: GameState) -> None:
        """Detect newly-appeared super-bomb explosions and advance active ones."""
        current_centers = {(exp.col, exp.row) for exp in state.explosions}

        for exp in state.explosions:
            cell = (exp.col, exp.row)
            if cell in self._seen_centers:
                continue
            self._seen_centers.add(cell)

            blast_radius = self._known_super_bombs.get(cell)
            if blast_radius is None:
                continue

            half = max(2, blast_radius // 2)
            radius_px = (half + 0.5) * TILE_SIZE
            cx = exp.col * TILE_SIZE + TILE_SIZE / 2
            cy = exp.row * TILE_SIZE + TILE_SIZE / 2
            self._active.append(_ActiveShockwave(cx, cy, radius_px, self.lifetime))

        self._seen_centers &= current_centers
        self._known_super_bombs = {
            (bomb.col, bomb.row): bomb.blast_radius for bomb in state.bombs if bomb.is_super
        }
        self._active = [sw for sw in self._active if not sw.is_dead()]

    def has_active(self) -> bool:
        return bool(self._active)

    def begin_scene_capture(self, width: int, height: int) -> Framebuffer | None:
        """Return a framebuffer to render the scene into, or None to skip post-processing.

        Call this before drawing the scene each frame. When it returns a
        framebuffer, draw the scene into it (it is not cleared for you)
        and then call composite() to warp it back onto the screen.
        """
        if not self._active:
            return None
        if self._enabled is None:
            self._enabled = self._try_init()
        if not self._enabled:
            return None
        return self._ensure_fbo(width, height)

    def composite(self, camera) -> None:
        """Warp the captured scene by every active shockwave and draw it to the screen."""
        ctx = arcade.get_window().ctx
        width, height = self._fbo_size
        aspect = width / height

        saved_blend = ctx.blend_func
        ctx.disable(ctx.BLEND)

        count = len(self._active)
        # Fixed pair of buffers ping-ponged between by index — needed only
        # when more than one shockwave is active at once (e.g. two super
        # bombs detonating together); the common single-shockwave case
        # never touches the second buffer.
        buffers = (self._scene_fbo, self._ensure_ping_fbo(width, height) if count > 1 else None)
        src_idx = 0
        for i, sw in enumerate(self._active):
            is_last = i == count - 1
            src = buffers[src_idx]
            dst = ctx.screen if is_last else buffers[1 - src_idx]

            dst.use()
            src.color_attachments[0].use(0)
            self._program['scene'] = 0
            self._program['aspect'] = aspect

            screen_x, screen_y = camera.project((sw.cx, sw.cy))
            self._program['centre'] = (screen_x / width, screen_y / height)
            self._program['radius'] = (sw.radius_ratio() * sw.max_radius * camera.zoom) / height
            self._program['ring_width'] = SHOCKWAVE_RING_WIDTH
            self._program['trail_length'] = SHOCKWAVE_TRAIL_LENGTH
            self._program['strength'] = SHOCKWAVE_DISTORTION_STRENGTH
            self._program['life_ratio'] = sw.strength_ratio()

            self._quad.render(self._program)

            if not is_last:
                src_idx = 1 - src_idx

        ctx.blend_func = saved_blend

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_fbo(self, width: int, height: int) -> Framebuffer:
        if self._scene_fbo is None or self._fbo_size != (width, height):
            ctx = arcade.get_window().ctx
            if self._scene_fbo is not None:
                self._scene_fbo.delete()
            if self._ping_fbo is not None:
                self._ping_fbo.delete()
                self._ping_fbo = None
            self._scene_fbo = ctx.framebuffer(color_attachments=[self._make_texture(width, height)])
            self._fbo_size = (width, height)
        return self._scene_fbo

    def _ensure_ping_fbo(self, width: int, height: int) -> Framebuffer:
        if self._ping_fbo is None:
            ctx = arcade.get_window().ctx
            self._ping_fbo = ctx.framebuffer(color_attachments=[self._make_texture(width, height)])
        return self._ping_fbo

    @staticmethod
    def _make_texture(width: int, height: int):
        ctx = arcade.get_window().ctx
        return ctx.texture(
            (width, height),
            components=4,
            filter=(ctx.LINEAR, ctx.LINEAR),
            wrap_x=ctx.CLAMP_TO_EDGE,
            wrap_y=ctx.CLAMP_TO_EDGE,
        )

    def _try_init(self) -> bool:
        """Load the shockwave shader and allocate GPU resources.

        Returns False on any failure so the effect degrades gracefully.
        """
        def build(ctx) -> None:
            vert_src = (_SHADER_DIR / 'shockwave.vert').read_text()
            frag_src = (_SHADER_DIR / 'shockwave.frag').read_text()
            self._program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
            self._quad = quad_2d_fs()

        return try_init_shader_effect(_log, 'Shockwave effect', _force_disabled, build)
