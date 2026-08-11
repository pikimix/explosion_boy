#!/usr/bin/env python
"""Standalone viewer for the smoke-cloud particle shader.

Spawns a single SmokeCloud and drives SmokeCloudSystem directly — no
networking, lobby, or game-loop machinery, just enough fake state to
exercise the real shader pipeline unchanged. Move the mouse to act as the
local player (cuts the hole); a second dummy player orbits the cloud
automatically so the wind push is visible without needing two inputs.

Controls:
  Up/Down    - particle density per tile (respawns the cloud)
  Left/Right - per-cloud particle cap (respawns the cloud)
  R          - hot-reload the .vert/.frag files from disk, no restart needed

Usage: uv run shader_test.py
"""
import math
import time

import arcade

import app.smoke_system as smoke_system
from app.smoke_system import SmokeCloudSystem
from core.components import PhysicsState, SmokeCloud
from core.state import GameState
from engine.config import TILE_SIZE

WINDOW_W, WINDOW_H = 900, 700
LOCAL_ID = 0
ORBIT_ID = 1

CLOUD_COL = WINDOW_W // TILE_SIZE // 2
CLOUD_ROW = WINDOW_H // TILE_SIZE // 2
CLOUD_RADIUS = 2
CLOUD_TICKS_TOTAL = 999_999  # never decremented — cloud just holds at full opacity

ORBIT_RADIUS = TILE_SIZE * 2.5
ORBIT_ANGULAR_SPEED = 1.2  # rad/s

_DENSITY_STEP = 1.25   # multiplicative step per key press
_CAP_STEP = 1.25


class ShaderTestWindow(arcade.Window):
    """Renders one SmokeCloud with a mouse-controlled and an auto-orbiting player."""

    def __init__(self) -> None:
        super().__init__(WINDOW_W, WINDOW_H, "Smoke shader test")
        arcade.set_background_color((200, 200, 205))

        self._smoke = SmokeCloudSystem()
        self._state = GameState(tick=0, map_cols=20, map_rows=20)
        self._state.smoke_clouds.append(SmokeCloud(
            col=CLOUD_COL, row=CLOUD_ROW, radius=CLOUD_RADIUS,
            ticks_remaining=CLOUD_TICKS_TOTAL, ticks_total=CLOUD_TICKS_TOTAL,
        ))

        self._mouse_x = WINDOW_W / 2
        self._mouse_y = WINDOW_H / 2
        self._prev_mouse = (self._mouse_x, self._mouse_y)
        self._start = time.monotonic()

        self._hud_text = arcade.Text('', 10, WINDOW_H - 20, arcade.color.BLACK, 13)
        self._hint_text = arcade.Text(
            'Up/Down: density/tile   Left/Right: cap/cloud   R: reload shaders',
            10, WINDOW_H - 40, arcade.color.BLACK, 13,
        )
        self._update_hud_text()

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        self._mouse_x, self._mouse_y = x, y

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if symbol == arcade.key.UP:
            smoke_system._DENSITY_PER_TILE = round(smoke_system._DENSITY_PER_TILE * _DENSITY_STEP)
            self._respawn_cloud()
        elif symbol == arcade.key.DOWN:
            smoke_system._DENSITY_PER_TILE = max(1, round(smoke_system._DENSITY_PER_TILE / _DENSITY_STEP))
            self._respawn_cloud()
        elif symbol == arcade.key.RIGHT:
            smoke_system._MAX_PARTICLES_PER_CLOUD = round(smoke_system._MAX_PARTICLES_PER_CLOUD * _CAP_STEP)
            self._respawn_cloud()
        elif symbol == arcade.key.LEFT:
            smoke_system._MAX_PARTICLES_PER_CLOUD = max(
                40, round(smoke_system._MAX_PARTICLES_PER_CLOUD / _CAP_STEP),
            )
            self._respawn_cloud()
        elif symbol == arcade.key.R:
            self._reload_shaders()
            return
        else:
            return
        self._update_hud_text()

    def _respawn_cloud(self) -> None:
        """Drop the cached particle block so the next update() rebuilds it
        from the (just-changed) density/cap constants."""
        key = (CLOUD_COL, CLOUD_ROW)
        slot = self._smoke._slot_of.pop(key, None)
        if slot is not None:
            self._smoke._free_slots.append(slot)
        self._smoke._blocks.pop(key, None)
        self._smoke._fade.pop(key, None)

    def _reload_shaders(self) -> None:
        """Force SmokeCloudSystem to re-read and recompile the shader files."""
        self._smoke._enabled = None
        self._smoke._dirty = True

    def _update_hud_text(self) -> None:
        self._hud_text.text = (
            f'density/tile={smoke_system._DENSITY_PER_TILE}  '
            f'cap/cloud={smoke_system._MAX_PARTICLES_PER_CLOUD}'
        )

    def on_update(self, dt: float) -> None:
        prev_x, prev_y = self._prev_mouse
        vx = (self._mouse_x - prev_x) / dt if dt > 0 else 0.0
        vy = (self._mouse_y - prev_y) / dt if dt > 0 else 0.0
        self._prev_mouse = (self._mouse_x, self._mouse_y)
        self._state.player_physics[LOCAL_ID] = PhysicsState(self._mouse_x, self._mouse_y, vx, vy)

        cx = CLOUD_COL * TILE_SIZE + TILE_SIZE / 2
        cy = CLOUD_ROW * TILE_SIZE + TILE_SIZE / 2
        angle = (time.monotonic() - self._start) * ORBIT_ANGULAR_SPEED
        ox = cx + ORBIT_RADIUS * math.cos(angle)
        oy = cy + ORBIT_RADIUS * math.sin(angle)
        ovx = -ORBIT_RADIUS * ORBIT_ANGULAR_SPEED * math.sin(angle)
        ovy = ORBIT_RADIUS * ORBIT_ANGULAR_SPEED * math.cos(angle)
        self._state.player_physics[ORBIT_ID] = PhysicsState(ox, oy, ovx, ovy)

        self._smoke.update(dt, self._state, LOCAL_ID, self._mouse_x, self._mouse_y)

    def on_draw(self) -> None:
        self.clear()
        self._smoke.draw()
        self._hud_text.draw()
        self._hint_text.draw()


def main() -> None:
    ShaderTestWindow()
    arcade.run()


if __name__ == "__main__":
    main()
