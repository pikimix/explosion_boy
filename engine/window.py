"""arcade.Window subclass. Owns the main loop and delegates to SceneManager."""
from __future__ import annotations

import arcade

from engine.config import TARGET_FPS, WINDOW_H, WINDOW_TITLE, WINDOW_W


class GameWindow(arcade.Window):
    def __init__(self) -> None:
        super().__init__(WINDOW_W, WINDOW_H, WINDOW_TITLE,
                         update_rate=1 / TARGET_FPS)
        self._scene_manager: "SceneManager | None" = None  # set after import

    def set_scene_manager(self, manager: "SceneManager") -> None:  # type: ignore[name-defined]
        self._scene_manager = manager

    def on_update(self, delta_time: float) -> None:
        if self._scene_manager:
            self._scene_manager.update(delta_time)

    def on_draw(self) -> None:
        self.clear()
        if self._scene_manager:
            self._scene_manager.draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        if self._scene_manager:
            self._scene_manager.on_key_press(key, modifiers)

    def on_key_release(self, key: int, modifiers: int) -> None:
        if self._scene_manager:
            self._scene_manager.on_key_release(key, modifiers)
