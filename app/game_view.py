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

from app.ui import hud, volume_widget
from app.ui.hud import HUD_WIDTH
from core.components import TileKind
from core.state import GameState
from engine.config import (
    BOMB_BASE_COLOUR, BOMB_FUSE_TICKS, BOMB_PULSE_COLOUR, EMPTY_TILE_COLOUR,
    EXPLOSION_COLOUR, GRID_COLS, GRID_ROWS, PLAYER_COLOURS, POWERUP_COLOURS,
    SOFT_BLOCK_COLOUR, SOLID_WALL_COLOUR, TILE_SIZE, WINDOW_H, WINDOW_W,
)

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
        volume: float = 1.0,
    ) -> None:
        with self._camera.activate():
            self._draw_tiles(state)
            self._draw_powerups(state)
            self._draw_bombs(state)
            self._draw_explosions(state)
            self._draw_players(state, local_player_id, predicted_x, predicted_y)
        hud.draw(state)
        self._draw_volume(volume)

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
            colour = POWERUP_COLOURS.get(int(pup.kind), (255, 255, 255, 255))
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
            rgb = state.player_colours.get(pid, PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
            colour = (*rgb, 255)
            arcade.draw_circle_filled(x, y, TILE_SIZE * 0.38, colour)

    def _draw_volume(self, volume: float) -> None:
        volume_widget.draw(volume)
