"""
Stateless renderer. Accepts a GameState and draws it each frame.
Not an arcade.View — it's a plain class owned by GameScene.

Predicted position for the local player comes from PredictionEngine and
overrides the server-state position for rendering only.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

import arcade
import arcade.camera
from arcade.sprite.animated import TextureKeyframe

from app.particle_system import ExplosionParticleSystem
from app.shockwave_system import ShockwaveSystem
from app.smoke_system import SmokeCloudSystem
from app.ui import hud, speed_widget
from app.ui.hud import HUD_WIDTH
from core.components import PowerupKind, TileKind
from core.state import GameState
from engine.config import (
    BOMB_FUSE_TICKS, BOMB_PULSE_COLOUR, EMPTY_TILE_COLOUR,
    EXPLOSION_COLOUR, GRID_COLS, GRID_ROWS, POWERUP_COLOURS,
    POWERUP_SYMBOLS, SHRINK_WARN_TICKS, SOFT_BLOCK_COLOUR, SOLID_WALL_COLOUR,
    TILE_SIZE, WINDOW_H, WINDOW_W,
)
from systems.world import ring_cells

_PLAYER_SPRITE_PATH = Path(__file__).parent.parent / 'resources' / 'sprites' / 'player.png'
_PLAYER_ANIM_FRAME_SIZE = 32   # each frame is 32×32 in the sheet
_PLAYER_ANIM_FRAMES = 4
_PLAYER_ANIM_DURATION_MS = 100  # 10 fps
_PLAYER_DRAW_SIZE = TILE_SIZE * 0.76

_TILE_COLOURS = {
    TileKind.SOLID_WALL: SOLID_WALL_COLOUR,
    TileKind.SOFT_BLOCK: SOFT_BLOCK_COLOUR,
    TileKind.EMPTY:      EMPTY_TILE_COLOUR,
}


class GameView:
    """Stateless renderer that draws a ``GameState`` each frame."""

    def __init__(self) -> None:
        self._tile_list: arcade.shape_list.ShapeElementList | None = None
        self._last_tiles_version: int = -1
        self._bomb_start_times: dict[tuple[int, int], float] = {}
        self._window_w = WINDOW_W
        self._window_h = WINDOW_H
        self._map_w = GRID_COLS * TILE_SIZE
        self._map_h = GRID_ROWS * TILE_SIZE
        self._camera = self._make_camera(WINDOW_W, WINDOW_H)
        self._shrink_warn_ring: int = 0
        self._shrink_flash_start: float = 0.0
        self._walk_animation: arcade.TextureAnimation | None = None
        self._player_sprites: dict[int, arcade.TextureAnimationSprite] = {}
        self._anim_last_time: float = 0.0
        self._last_frame_time: float = 0.0
        self._particles = ExplosionParticleSystem()
        self._shockwaves = ShockwaveSystem()
        self._smoke = SmokeCloudSystem()
        self._bomb_text = arcade.Text(
            self._BOMB_EMOJI, 0, 0,
            color=arcade.color.WHITE,
            font_size=self._BOMB_FONT_SIZE,
            anchor_x='center', anchor_y='center',
        )
        self._powerup_texts: dict[int, arcade.Text] = {
            kind: arcade.Text(
                symbol, 0, 0,
                color=POWERUP_COLOURS.get(kind, (255, 255, 255, 255)),
                font_size=28,
                bold=True,
                anchor_x='center', anchor_y='center',
            )
            for kind, symbol in POWERUP_SYMBOLS.items()
        }
        self._bomb_badge_texts: dict[int, arcade.Text] = {
            kind: arcade.Text(
                POWERUP_SYMBOLS[kind], 0, 0,
                color=POWERUP_COLOURS.get(kind, (255, 255, 255, 255)),
                font_size=self._BOMB_BADGE_FONT_SIZE,
                bold=True,
                anchor_x='center', anchor_y='center',
            )
            for kind in (PowerupKind.SUPER_BOMB, PowerupKind.CLUSTER_BOMB, PowerupKind.RUBBLE_BOMB,
                         PowerupKind.SMOKE_BOMB)
        }
        self._dizzy_text = arcade.Text(
            '\U0001f635', 0, 0,
            font_size=14,
            anchor_x='center', anchor_y='bottom',
        )
        self._bomb_count_fill_text = arcade.Text(
            '', 0, 0,
            color=arcade.color.WHITE,
            font_size=14,
            bold=True,
            anchor_x='center', anchor_y='bottom',
        )
        self._bomb_count_outline_text = arcade.Text(
            '', 0, 0,
            color=arcade.color.BLACK,
            font_size=14,
            bold=True,
            anchor_x='center', anchor_y='bottom',
        )

    def _make_camera(self, width: float, height: float) -> arcade.camera.Camera2D:
        play_w = width - HUD_WIDTH
        return arcade.camera.Camera2D(
            viewport=arcade.LBWH(HUD_WIDTH, 0, play_w, height),
            position=(self._map_w / 2, self._map_h / 2),
            zoom=min(play_w / self._map_w, height / self._map_h),
        )

    def on_resize(self, width: int, height: int) -> None:
        """Rebuild the camera to match the new window dimensions.

        Parameters
        ----------
        width : int
            New window width in pixels.
        height : int
            New window height in pixels.
        """
        self._window_w, self._window_h = width, height
        self._camera = self._make_camera(width, height)

    def set_map_size(self, cols: int, rows: int) -> None:
        """Resize the camera framing to match the round's actual grid dimensions."""
        self._map_w = cols * TILE_SIZE
        self._map_h = rows * TILE_SIZE
        self._camera = self._make_camera(self._window_w, self._window_h)

    def draw(
        self,
        state: GameState,
        local_player_id: int | None = None,
        predicted_x: float | None = None,
        predicted_y: float | None = None,
        predicted_vx: float | None = None,
        predicted_vy: float | None = None,
        speed: float | None = None,
    ) -> None:
        """Draw the full frame: tiles, entities, particles and the HUD.

        Parameters
        ----------
        state : GameState
            The game state to render.
        local_player_id : int, optional
            ID of the locally-controlled player, used to apply predicted
            position/velocity instead of the server-reported ones.
        predicted_x : float, optional
            Client-predicted x position for the local player.
        predicted_y : float, optional
            Client-predicted y position for the local player.
        predicted_vx : float, optional
            Client-predicted x velocity for the local player.
        predicted_vy : float, optional
            Client-predicted y velocity for the local player.
        speed : float, optional
            Current speed value to display in the speed widget, if any.
        """
        now = time.monotonic()
        dt = now - self._last_frame_time if self._last_frame_time else 0.0
        self._last_frame_time = now

        self._shockwaves.update(state)
        fbo = self._shockwaves.begin_scene_capture(self._window_w, self._window_h)
        if fbo is not None:
            with fbo.activate():
                fbo.clear()
                with self._camera.activate():
                    self._draw_scene(state, dt, local_player_id, predicted_x, predicted_y, predicted_vx, predicted_vy)
            self._shockwaves.composite(self._camera)
        else:
            with self._camera.activate():
                self._draw_scene(state, dt, local_player_id, predicted_x, predicted_y, predicted_vx, predicted_vy)
        hud.draw(state)
        if speed is not None:
            speed_widget.draw(speed)

    def _draw_scene(
        self,
        state: GameState,
        dt: float,
        local_player_id: int | None,
        predicted_x: float | None,
        predicted_y: float | None,
        predicted_vx: float | None,
        predicted_vy: float | None,
    ) -> None:
        """Draw everything that a super-bomb shockwave should be able to warp."""
        self._draw_tiles(state)
        self._draw_shrink_warning(state)
        self._draw_powerups(state)
        self._draw_bombs(state)
        self._draw_players(state, local_player_id, predicted_x, predicted_y, predicted_vx, predicted_vy)
        self._draw_smoke(state, local_player_id, predicted_x, predicted_y)
        self._draw_explosions(state)
        self._particles.update(dt, state)
        self._particles.draw()

    # ── Tiles ─────────────────────────────────────────────────────────────────

    def _draw_tiles(self, state: GameState) -> None:
        if state.tiles_version != self._last_tiles_version:
            self._rebuild_tile_shapes(state)
        if self._tile_list:
            self._tile_list.draw()

    def _rebuild_tile_shapes(self, state: GameState) -> None:
        self._last_tiles_version = state.tiles_version
        shape_list = arcade.shape_list.ShapeElementList()
        for row in range(state.map_rows):
            for col in range(state.map_cols):
                kind = state.tiles[row][col]
                colour = _TILE_COLOURS[kind]
                cx = col * TILE_SIZE + TILE_SIZE / 2
                cy = row * TILE_SIZE + TILE_SIZE / 2
                shape_list.append(
                    arcade.shape_list.create_rectangle_filled(cx, cy, TILE_SIZE - 2,
                                                              TILE_SIZE - 2, colour)
                )
        self._tile_list = shape_list

    def _draw_shrink_warning(self, state: GameState) -> None:
        """Flash the ring of cells about to become perimeter walls, using the
        same pulsing glow as a bomb fuse (see _draw_bombs)."""
        if not state.shrink_warn_ring:
            self._shrink_warn_ring = 0
            return
        now = time.monotonic()
        if state.shrink_warn_ring != self._shrink_warn_ring:
            self._shrink_warn_ring = state.shrink_warn_ring
            self._shrink_flash_start = now
        elapsed = now - self._shrink_flash_start
        fuse_ratio = max(0.0, state.shrink_warn_ticks_remaining / SHRINK_WARN_TICKS)
        freq = 1.0 + (1.0 - fuse_ratio) * 5.0
        pulse = (-math.cos(2 * math.pi * freq * elapsed) + 1) * 0.5
        glow_alpha = int(pulse * 220)
        colour = (BOMB_PULSE_COLOUR[0], BOMB_PULSE_COLOUR[1], BOMB_PULSE_COLOUR[2], glow_alpha)
        for c, r in ring_cells(state.map_cols, state.map_rows, state.shrink_warn_ring):
            if state.tiles[r][c] == TileKind.SOLID_WALL:
                continue
            cx = c * TILE_SIZE + TILE_SIZE / 2
            cy = r * TILE_SIZE + TILE_SIZE / 2
            arcade.draw_rect_filled(arcade.XYWH(cx, cy, TILE_SIZE, TILE_SIZE), colour)

    # ── Other elements ────────────────────────────────────────────────────────

    _BOMB_EMOJI = '\U0001f4a3'         # 💣  normal (not a powerup, no POWERUP_SYMBOLS entry)
    _BOMB_FONT_SIZE = int(TILE_SIZE * 0.55)
    _BOMB_BADGE_FONT_SIZE = int(TILE_SIZE * 0.32)
    _BOMB_BADGE_OFFSET = TILE_SIZE * 0.3
    # one corner per badge kind, in a fixed order: top-right, top-left, bottom-right, bottom-left
    _BOMB_BADGE_CORNERS = (
        (_BOMB_BADGE_OFFSET, _BOMB_BADGE_OFFSET),
        (-_BOMB_BADGE_OFFSET, _BOMB_BADGE_OFFSET),
        (_BOMB_BADGE_OFFSET, -_BOMB_BADGE_OFFSET),
        (-_BOMB_BADGE_OFFSET, -_BOMB_BADGE_OFFSET),
    )

    def _draw_bombs(self, state: GameState) -> None:
        now = time.monotonic()
        active_keys: set[tuple[int, int]] = set()
        for bomb in state.bombs:
            key = (bomb.col, bomb.row)
            active_keys.add(key)
            if key not in self._bomb_start_times:
                self._bomb_start_times[key] = now
            elapsed = now - self._bomb_start_times[key]
            fuse_ratio = max(0.0, bomb.fuse_ticks_remaining / BOMB_FUSE_TICKS)
            # 1 Hz when just placed → 6 Hz when about to detonate
            freq = 1.0 + (1.0 - fuse_ratio) * 5.0
            # -cos so each bomb always starts dark (0) and immediately rises
            pulse = (-math.cos(2 * math.pi * freq * elapsed) + 1) * 0.5
            glow_alpha = int(pulse * 220)
            arcade.draw_circle_filled(
                bomb.px, bomb.py, TILE_SIZE * 0.42,
                (BOMB_PULSE_COLOUR[0], BOMB_PULSE_COLOUR[1], BOMB_PULSE_COLOUR[2], glow_alpha),
            )
            self._bomb_text.x = bomb.px
            self._bomb_text.y = bomb.py
            self._bomb_text.draw()
            badge_kinds = []
            if bomb.is_smoke:
                badge_kinds.append(PowerupKind.SMOKE_BOMB)
            if bomb.is_super:
                badge_kinds.append(PowerupKind.SUPER_BOMB)
            if bomb.is_cluster:
                badge_kinds.append(PowerupKind.CLUSTER_BOMB)
            if bomb.is_rubble:
                badge_kinds.append(PowerupKind.RUBBLE_BOMB)
            for badge_kind, (dx, dy) in zip(badge_kinds, self._BOMB_BADGE_CORNERS):
                badge = self._bomb_badge_texts[badge_kind]
                badge.x = bomb.px + dx
                badge.y = bomb.py + dy
                badge.draw()
        for key in list(self._bomb_start_times):
            if key not in active_keys:
                del self._bomb_start_times[key]

    def _draw_smoke(
        self,
        state: GameState,
        local_id: int | None,
        pred_x: float | None,
        pred_y: float | None,
    ) -> None:
        if local_id is not None and pred_x is not None and pred_y is not None:
            px, py = pred_x, pred_y
        else:
            phys = state.player_physics.get(local_id) if local_id is not None else None
            px, py = (phys.x, phys.y) if phys is not None else (-1.0e6, -1.0e6)
        self._smoke.draw(state, px, py)

    def _draw_explosions(self, state: GameState) -> None:
        for exp in state.explosions:
            cx = exp.col * TILE_SIZE + TILE_SIZE / 2
            cy = exp.row * TILE_SIZE + TILE_SIZE / 2
            arcade.draw_rect_filled(arcade.XYWH(cx, cy, TILE_SIZE, TILE_SIZE),
                                    EXPLOSION_COLOUR)
        for ray in state.explosion_rays:
            dc, dr = ray.direction
            for i in range(1, ray.length + 1):
                cx = (ray.origin_col + dc * i) * TILE_SIZE + TILE_SIZE / 2
                cy = (ray.origin_row + dr * i) * TILE_SIZE + TILE_SIZE / 2
                arcade.draw_rect_filled(arcade.XYWH(cx, cy, TILE_SIZE, TILE_SIZE),
                                        EXPLOSION_COLOUR)

    def _draw_powerups(self, state: GameState) -> None:
        for pup in state.powerups:
            cx = pup.col * TILE_SIZE + TILE_SIZE / 2
            cy = pup.row * TILE_SIZE + TILE_SIZE / 2
            kind_val = int(pup.kind)
            if kind_val in self._powerup_texts:
                t = self._powerup_texts[kind_val]
                t.x = cx
                t.y = cy
                t.draw()

    def _ensure_walk_animation(self) -> None:
        if self._walk_animation is not None:
            return
        sheet = arcade.SpriteSheet(_PLAYER_SPRITE_PATH)
        textures = sheet.get_texture_grid(
            size=(_PLAYER_ANIM_FRAME_SIZE, _PLAYER_ANIM_FRAME_SIZE),
            columns=_PLAYER_ANIM_FRAMES,
            count=_PLAYER_ANIM_FRAMES,
        )
        self._walk_animation = arcade.TextureAnimation([
            TextureKeyframe(tex, duration=_PLAYER_ANIM_DURATION_MS) for tex in textures
        ])

    def _draw_players(
        self,
        state: GameState,
        local_id: int | None,
        pred_x: float | None,
        pred_y: float | None,
        pred_vx: float | None = None,
        pred_vy: float | None = None,
    ) -> None:
        self._ensure_walk_animation()

        now = time.monotonic()
        dt = (now - self._anim_last_time) if self._anim_last_time else 0.0
        self._anim_last_time = now

        current_pids = set(state.player_physics)
        for pid in list(self._player_sprites):
            if pid not in current_pids:
                del self._player_sprites[pid]

        for pid, phys in state.player_physics.items():
            if pid not in self._player_sprites:
                sprite = arcade.TextureAnimationSprite(animation=self._walk_animation)
                sprite.width = _PLAYER_DRAW_SIZE
                sprite.height = _PLAYER_DRAW_SIZE
                self._player_sprites[pid] = sprite

            sprite = self._player_sprites[pid]
            sprite.center_x = pred_x if (pid == local_id and pred_x is not None) else phys.x
            sprite.center_y = pred_y if (pid == local_id and pred_y is not None) else phys.y
            sprite.color = (*hud.player_rgb(state, pid), 255)

            if pid == local_id and pred_vx is not None and pred_vy is not None:
                vx, vy = pred_vx, pred_vy
            else:
                vx, vy = phys.vx, phys.vy
            moving = abs(vx) > 1.0 or abs(vy) > 1.0
            if moving:
                sprite.update_animation(dt)
            else:
                sprite.time = 0.0

            arcade.draw_sprite(sprite)

            stats = state.players.get(pid)
            dizzy = stats is not None and stats.reversed_controls_ticks > 0

            if pid == local_id and stats is not None:
                if dizzy:
                    self._draw_dizzy_icon(sprite, _PLAYER_DRAW_SIZE * 0.85)
                else:
                    self._draw_bomb_count(sprite, stats)
            elif dizzy:
                self._draw_dizzy_icon(sprite, _PLAYER_DRAW_SIZE * 0.55)

    def _draw_dizzy_icon(self, sprite: arcade.Sprite, offset: float) -> None:
        self._dizzy_text.x = sprite.center_x
        self._dizzy_text.y = sprite.center_y + offset
        self._dizzy_text.draw()

    _BOMB_COUNT_OUTLINE_OFFSET = 1.5

    def _draw_bomb_count(self, sprite: arcade.Sprite, stats) -> None:
        """Draw the local player's remaining bomb count above their head,
        as white text with a black outline (four offset black copies behind
        a white copy, since arcade.Text has no native outline support)."""
        remaining = max(0, stats.bomb_capacity - stats.bombs_in_use)
        text = str(remaining)
        x = sprite.center_x
        y = sprite.center_y + _PLAYER_DRAW_SIZE * 0.85

        outline = self._bomb_count_outline_text
        outline.text = text
        off = self._BOMB_COUNT_OUTLINE_OFFSET
        for dx, dy in ((-off, -off), (-off, off), (off, -off), (off, off)):
            outline.x = x + dx
            outline.y = y + dy
            outline.draw()

        fill = self._bomb_count_fill_text
        fill.text = text
        fill.x = x
        fill.y = y
        fill.draw()

