"""Lobby waiting room. Connects to server, shows player list, ready button."""
from __future__ import annotations

import arcade
import arcade.camera
import arcade.gui
import arcade.shape_list

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


class LobbyScene:
    def __init__(self, client: GameClient, player_name: str,
                 scene_manager: "SceneManager") -> None:  # type: ignore[name-defined]
        self._client = client
        self._scene_manager = scene_manager
        self._player_name = player_name
        self._players: list[dict] = []
        self._ready_sent = False
        self._spawn_shapes: arcade.shape_list.ShapeElementList = (
            arcade.shape_list.ShapeElementList()
        )
        self._spawn_texts: list[arcade.Text] = []

        self._tile_shapes = self._build_preview_tiles()
        map_w = GRID_COLS * TILE_SIZE
        map_h = GRID_ROWS * TILE_SIZE
        self._camera = arcade.camera.Camera2D(
            position=(map_w / 2, map_h / 2),
            zoom=min(WINDOW_W / map_w, WINDOW_H / map_h),
        )

        self._title_text = arcade.Text(
            "EXPLOSION BOY",
            WINDOW_W / 2, WINDOW_H - 40,
            arcade.color.WHITE, font_size=32, bold=True,
            anchor_x="center",
        )
        self._waiting_text = arcade.Text(
            "Waiting for players…",
            WINDOW_W / 2, WINDOW_H / 2,
            arcade.color.WHITE, font_size=16,
            anchor_x="center",
        )

        self._ui = arcade.gui.UIManager()
        self._ui.enable()

        ready_btn = arcade.gui.UIFlatButton(text="Ready", width=200)
        ready_btn.on_click = self._on_ready_click  # type: ignore[method-assign]

        self._ui.add(
            arcade.gui.UIAnchorLayout().add(
                ready_btn,
                anchor_x="center_x",
                anchor_y="bottom",
                align_y=20,
            )
        )

        client.send_join(player_name)

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

    def _on_ready_click(self, _event) -> None:
        if not self._ready_sent:
            self._ready_sent = True
            self._client.send_ready()

    def update(self, dt: float) -> None:
        for msg in self._client.poll_messages():
            if isinstance(msg, LobbyUpdateMsg):
                self._players = msg.players
                self._rebuild_spawn_markers()
            elif isinstance(msg, GameStartMsg):
                from app.scenes.game_scene import GameScene
                self._ui.disable()
                self._scene_manager.replace(
                    GameScene(self._client, self._scene_manager, self._player_name)
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
        self._ui.draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        pass

    def on_key_release(self, key: int, modifiers: int) -> None:
        pass

    # ── Spawn markers ─────────────────────────────────────────────────────────

    def _rebuild_spawn_markers(self) -> None:
        shapes = arcade.shape_list.ShapeElementList()
        texts = []
        for p in self._players:
            pid = p["id"]
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
                anchor_x="center",
            ))
        self._spawn_shapes = shapes
        self._spawn_texts = texts
