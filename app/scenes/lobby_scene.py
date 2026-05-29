"""Lobby waiting room. Connects to server, shows player list and ready status."""
from __future__ import annotations

import arcade
import arcade.camera
import arcade.shape_list

from app.ui import volume_widget
from app.ui.hud import HUD_WIDTH
from core.components import TileKind
from net.client import GameClient
from net.protocol import GameStartMsg, LobbyUpdateMsg
from engine.config import (
    GRID_COLS, GRID_ROWS, PLAYER_COLOURS, SPAWN_POINTS,
    TILE_SIZE, WINDOW_H, WINDOW_W,
)

_SOLID_COLOUR = (60,  60,  60,  255)
_EMPTY_COLOUR = (180, 180, 180, 255)
_PLAYER_RADIUS = TILE_SIZE * 0.38

_HUD_X = 10.0
_HUD_TOP_MARGIN = 10.0
_NAME_SIZE = 13
_STATUS_SIZE = 11
_NAME_H = 17.0
_STATUS_H = 15.0
_PLAYER_GAP = 8.0


class LobbyScene:
    def __init__(self, client: GameClient, player_name: str,
                 scene_manager: "SceneManager") -> None:  # type: ignore[name-defined]
        self._client = client
        self._scene_manager = scene_manager
        self._player_name = player_name
        self._players: list[dict] = []
        self._ready = False
        self._volume = 1.0
        self._spawn_shapes: arcade.shape_list.ShapeElementList = (
            arcade.shape_list.ShapeElementList()
        )
        self._spawn_texts: list[arcade.Text] = []

        self._tile_shapes = self._build_preview_tiles()
        self._map_w = GRID_COLS * TILE_SIZE
        self._map_h = GRID_ROWS * TILE_SIZE
        self._camera = self._make_camera(WINDOW_W, WINDOW_H)

        play_cx = HUD_WIDTH + (WINDOW_W - HUD_WIDTH) / 2
        self._title_text = arcade.Text(
            'EXPLOSION BOY',
            play_cx, WINDOW_H - 40,
            arcade.color.WHITE, font_size=32, bold=True,
            anchor_x='center',
        )
        self._waiting_text = arcade.Text(
            'Waiting for players…',
            play_cx, WINDOW_H / 2,
            arcade.color.WHITE, font_size=16,
            anchor_x='center',
        )

        client.send_join(player_name)

    # ── Camera ────────────────────────────────────────────────────────────────

    def _make_camera(self, width: float, height: float) -> arcade.camera.Camera2D:
        play_w = width - HUD_WIDTH
        return arcade.camera.Camera2D(
            viewport=arcade.LBWH(HUD_WIDTH, 0, play_w, height),
            position=(self._map_w / 2, self._map_h / 2),
            zoom=min(play_w / self._map_w, height / self._map_h),
        )

    # ── Map preview ───────────────────────────────────────────────────────────

    def _build_preview_tiles(self) -> arcade.shape_list.ShapeElementList:
        shape_list = arcade.shape_list.ShapeElementList()
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                is_wall = (
                    row == 0 or row == GRID_ROWS - 1
                    or col == 0 or col == GRID_COLS - 1
                    or (row % 2 == 0 and col % 2 == 0)
                )
                colour = _SOLID_COLOUR if is_wall else _EMPTY_COLOUR
                cx = col * TILE_SIZE + TILE_SIZE / 2
                cy = row * TILE_SIZE + TILE_SIZE / 2
                shape_list.append(
                    arcade.shape_list.create_rectangle_filled(
                        cx, cy, TILE_SIZE - 2, TILE_SIZE - 2, colour,
                    )
                )
        return shape_list

    # ── Network ───────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        for msg in self._client.poll_messages():
            if isinstance(msg, LobbyUpdateMsg):
                self._players = msg.players
                self._rebuild_spawn_markers()
            elif isinstance(msg, GameStartMsg):
                from app.scenes.game_scene import GameScene
                self._scene_manager.replace(
                    GameScene(self._client, self._scene_manager, self._player_name,
                              volume=self._volume)
                )
                return

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self) -> None:
        with self._camera.activate():
            self._tile_shapes.draw()
            self._spawn_shapes.draw()
            for t in self._spawn_texts:
                t.draw()
        self._title_text.draw()
        if not self._players:
            self._waiting_text.draw()
        self._draw_hud()

    def _draw_hud(self) -> None:
        win = arcade.get_window()
        y = win.height - _HUD_TOP_MARGIN

        arcade.draw_text(
            'Players', _HUD_X, y,
            color=(200, 200, 200),
            font_size=12,
            bold=True,
            anchor_x='left',
            anchor_y='top',
        )
        y -= 22.0

        for p in self._players:
            pid = p['id']
            colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
            arcade.draw_text(
                p['name'], _HUD_X, y,
                color=colour[:3],
                font_size=_NAME_SIZE,
                bold=True,
                anchor_x='left',
                anchor_y='top',
            )
            y -= _NAME_H
            ready = p['ready']
            arcade.draw_text(
                '✓ Ready' if ready else '… Waiting',
                _HUD_X, y,
                color=(100, 220, 100) if ready else (180, 180, 180),
                font_size=_STATUS_SIZE,
                anchor_x='left',
                anchor_y='top',
            )
            y -= _STATUS_H + _PLAYER_GAP

        volume_widget.draw(self._volume)

        # Space-to-ready hint at bottom of HUD
        if self._ready:
            hint = 'Ready!\nWaiting for\nothers…'
            hint_colour = (100, 220, 100)
        else:
            hint = 'Press SPACE\nto ready up'
            hint_colour = (200, 200, 200)
        arcade.draw_text(
            hint, _HUD_X, 70,
            color=hint_colour,
            font_size=11,
            anchor_x='left',
            anchor_y='bottom',
            multiline=True,
            width=int(HUD_WIDTH - _HUD_X * 2),
        )

    def on_resize(self, width: int, height: int) -> None:
        self._camera = self._make_camera(width, height)
        play_cx = HUD_WIDTH + (width - HUD_WIDTH) / 2
        self._title_text.x = play_cx
        self._title_text.y = height - 40
        self._waiting_text.x = play_cx
        self._waiting_text.y = height / 2

    def on_key_press(self, key: int, modifiers: int) -> None:
        if key == arcade.key.SPACE:
            self._ready = not self._ready
            self._client.send_ready(self._ready)
        elif key == arcade.key.BRACKETLEFT:
            self._volume = round(max(0.0, self._volume - 0.1), 1)
        elif key == arcade.key.BRACKETRIGHT:
            self._volume = round(min(1.0, self._volume + 0.1), 1)

    def on_key_release(self, key: int, modifiers: int) -> None:
        pass

    # ── Spawn markers ─────────────────────────────────────────────────────────

    def _rebuild_spawn_markers(self) -> None:
        shapes = arcade.shape_list.ShapeElementList()
        texts = []
        for p in self._players:
            pid = p['id']
            col, row = SPAWN_POINTS[pid]
            px = col * TILE_SIZE + TILE_SIZE / 2
            py = row * TILE_SIZE + TILE_SIZE / 2
            colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
            shapes.append(
                arcade.shape_list.create_ellipse_filled(
                    px, py, _PLAYER_RADIUS, _PLAYER_RADIUS, colour,
                )
            )
            label = f"{p['name']}  {'✓' if p['ready'] else '…'}"
            texts.append(arcade.Text(
                label, px, py + _PLAYER_RADIUS + 4,
                colour, font_size=11, bold=True,
                anchor_x='center',
            ))
        self._spawn_shapes = shapes
        self._spawn_texts = texts
