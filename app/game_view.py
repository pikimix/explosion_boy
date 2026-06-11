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
from app.ui import hud, speed_widget, volume_widget
from app.ui.hud import HUD_WIDTH
from core.components import TileKind
from core.state import GameState
from engine.config import (
    BOMB_BASE_COLOUR, BOMB_FUSE_TICKS, BOMB_PULSE_COLOUR, EMPTY_TILE_COLOUR,
    EXPLOSION_COLOUR, GRID_COLS, GRID_ROWS, PLAYER_COLOURS, POWERUP_COLOURS,
    POWERUP_SYMBOLS, SOFT_BLOCK_COLOUR, SOLID_WALL_COLOUR, TILE_SIZE, WINDOW_H, WINDOW_W,
)

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
    def __init__(self) -> None:
        self._tile_list: arcade.shape_list.ShapeElementList | None = None
        self._last_tiles: list[list[TileKind]] | None = None
        self._bomb_start_times: dict[tuple[int, int], float] = {}
        self._map_w = GRID_COLS * TILE_SIZE
        self._map_h = GRID_ROWS * TILE_SIZE
        self._camera = self._make_camera(WINDOW_W, WINDOW_H)
        self._walk_animation: arcade.TextureAnimation | None = None
        self._player_sprites: dict[int, arcade.TextureAnimationSprite] = {}
        self._anim_last_time: float = 0.0
        self._last_frame_time: float = 0.0
        self._particles = ExplosionParticleSystem()
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

    def _make_camera(self, width: float, height: float) -> arcade.camera.Camera2D:
        play_w = width - HUD_WIDTH
        return arcade.camera.Camera2D(
            viewport=arcade.LBWH(HUD_WIDTH, 0, play_w, height),
            position=(self._map_w / 2, self._map_h / 2),
            zoom=min(play_w / self._map_w, height / self._map_h),
        )

    def on_resize(self, width: int, height: int) -> None:
        self._camera = self._make_camera(width, height)

    def draw(
        self,
        state: GameState,
        local_player_id: int | None = None,
        predicted_x: float | None = None,
        predicted_y: float | None = None,
        predicted_vx: float | None = None,
        predicted_vy: float | None = None,
        volume: float = 1.0,
        speed: float | None = None,
    ) -> None:
        now = time.monotonic()
        dt = now - self._last_frame_time if self._last_frame_time else 0.0
        self._last_frame_time = now

        with self._camera.activate():
            self._draw_tiles(state)
            self._draw_powerups(state)
            self._draw_bombs(state)
            self._draw_explosions(state)
            self._particles.update(dt, state)
            self._particles.draw()
            self._draw_players(state, local_player_id, predicted_x, predicted_y, predicted_vx, predicted_vy)
        hud.draw(state)
        self._draw_volume(volume)
        if speed is not None:
            speed_widget.draw(speed)

    # ── Tiles ─────────────────────────────────────────────────────────────────

    def _draw_tiles(self, state: GameState) -> None:
        if state.tiles is not self._last_tiles:
            self._rebuild_tile_shapes(state)
        if self._tile_list:
            self._tile_list.draw()

    def _rebuild_tile_shapes(self, state: GameState) -> None:
        self._last_tiles = state.tiles
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

    # ── Other elements ────────────────────────────────────────────────────────

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
            r = int(BOMB_BASE_COLOUR[0] + pulse * (BOMB_PULSE_COLOUR[0] - BOMB_BASE_COLOUR[0]))
            g = int(BOMB_BASE_COLOUR[1] + pulse * (BOMB_PULSE_COLOUR[1] - BOMB_BASE_COLOUR[1]))
            b = int(BOMB_BASE_COLOUR[2] + pulse * (BOMB_PULSE_COLOUR[2] - BOMB_BASE_COLOUR[2]))
            arcade.draw_circle_filled(bomb.px, bomb.py, TILE_SIZE * 0.35, (r, g, b, 255))
        for key in list(self._bomb_start_times):
            if key not in active_keys:
                del self._bomb_start_times[key]

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
            rgb = state.player_colours.get(pid, PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
            sprite.color = (*rgb, 255)

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
            if stats is not None and stats.reversed_controls_ticks > 0:
                arcade.draw_text(
                    '\U0001f635',
                    sprite.center_x, sprite.center_y + _PLAYER_DRAW_SIZE * 0.55,
                    font_size=14,
                    anchor_x='center', anchor_y='bottom',
                )

    def _draw_volume(self, volume: float) -> None:
        volume_widget.draw(volume)
