"""
Stateless renderer. Accepts a GameState and draws it each frame.
Not an arcade.View — it's a plain class owned by GameScene.

Predicted position for the local player comes from PredictionEngine and
overrides the server-state position for rendering only.
"""
from __future__ import annotations

import math
import time

import arcade

import arcade.camera

from app.ui import hud
from core.components import TileKind
from core.state import GameState
from engine.config import BOMB_FUSE_TICKS, GRID_COLS, GRID_ROWS, PLAYER_COLOURS, TILE_SIZE, WINDOW_H, WINDOW_W

_TILE_COLOURS = {
    TileKind.SOLID_WALL: arcade.color.DARK_GRAY,
    TileKind.SOFT_BLOCK: arcade.color.SADDLE_BROWN,
    TileKind.EMPTY:      arcade.color.LIGHT_GRAY,
}

_EXPLOSION_COLOUR  = (255, 180, 0, 200)
_BOMB_BASE         = (30, 30, 30)
_BOMB_PULSE        = (255, 220, 0)
_POWERUP_COLOURS   = {1: arcade.color.GOLD, 2: arcade.color.ORANGE_RED}


class GameView:
    def __init__(self) -> None:
        self._tile_list: arcade.shape_list.ShapeElementList | None = None
        self._last_tiles: list[list[TileKind]] | None = None
        self._bomb_start_times: dict[tuple[int, int], float] = {}
        map_w = GRID_COLS * TILE_SIZE
        map_h = GRID_ROWS * TILE_SIZE
        self._camera = arcade.camera.Camera2D(
            position=(map_w / 2, map_h / 2),
            zoom=min(WINDOW_W / map_w, WINDOW_H / map_h),
        )

    def draw(
        self,
        state: GameState,
        local_player_id: int | None = None,
        predicted_x: float | None = None,
        predicted_y: float | None = None,
    ) -> None:
        with self._camera.activate():
            self._draw_tiles(state)
            self._draw_powerups(state)
            self._draw_bombs(state)
            self._draw_explosions(state)
            self._draw_players(state, local_player_id, predicted_x, predicted_y)
        hud.draw(state)

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
            r = int(_BOMB_BASE[0] + pulse * (_BOMB_PULSE[0] - _BOMB_BASE[0]))
            g = int(_BOMB_BASE[1] + pulse * (_BOMB_PULSE[1] - _BOMB_BASE[1]))
            b = int(_BOMB_BASE[2] + pulse * (_BOMB_PULSE[2] - _BOMB_BASE[2]))
            arcade.draw_circle_filled(bomb.px, bomb.py, TILE_SIZE * 0.35, (r, g, b, 255))
        for key in list(self._bomb_start_times):
            if key not in active_keys:
                del self._bomb_start_times[key]

    def _draw_explosions(self, state: GameState) -> None:
        for exp in state.explosions:
            cx = exp.col * TILE_SIZE + TILE_SIZE / 2
            cy = exp.row * TILE_SIZE + TILE_SIZE / 2
            arcade.draw_rect_filled(arcade.XYWH(cx, cy, TILE_SIZE, TILE_SIZE),
                                    _EXPLOSION_COLOUR)
        for ray in state.explosion_rays:
            dc, dr = ray.direction
            for i in range(1, ray.length + 1):
                cx = (ray.origin_col + dc * i) * TILE_SIZE + TILE_SIZE / 2
                cy = (ray.origin_row + dr * i) * TILE_SIZE + TILE_SIZE / 2
                arcade.draw_rect_filled(arcade.XYWH(cx, cy, TILE_SIZE, TILE_SIZE),
                                        _EXPLOSION_COLOUR)

    def _draw_powerups(self, state: GameState) -> None:
        for pup in state.powerups:
            cx = pup.col * TILE_SIZE + TILE_SIZE / 2
            cy = pup.row * TILE_SIZE + TILE_SIZE / 2
            colour = _POWERUP_COLOURS.get(int(pup.kind), arcade.color.WHITE)
            arcade.draw_circle_filled(cx, cy, TILE_SIZE * 0.25, colour)

    def _draw_players(
        self,
        state: GameState,
        local_id: int | None,
        pred_x: float | None,
        pred_y: float | None,
    ) -> None:
        for pid, phys in state.player_physics.items():
            x = pred_x if (pid == local_id and pred_x is not None) else phys.x
            y = pred_y if (pid == local_id and pred_y is not None) else phys.y
            colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
            arcade.draw_circle_filled(x, y, TILE_SIZE * 0.38, colour)
