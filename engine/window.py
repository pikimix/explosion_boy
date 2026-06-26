"""arcade.Window subclass. Owns the main loop and delegates to SceneManager."""
from __future__ import annotations

import arcade

from engine.config import TARGET_FPS, WINDOW_H, WINDOW_TITLE, WINDOW_W


class GameWindow(arcade.Window):
    def __init__(self) -> None:
        super().__init__(WINDOW_W, WINDOW_H, WINDOW_TITLE,
                         update_rate=1 / TARGET_FPS, resizable=True)
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

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        if self._scene_manager:
            self._scene_manager.on_mouse_press(x, y, button, modifiers)

    def on_mouse_drag(
        self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int
    ) -> None:
        if self._scene_manager:
            self._scene_manager.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
        if self._scene_manager:
            self._scene_manager.on_mouse_release(x, y, button, modifiers)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        if self._scene_manager:
            self._scene_manager.on_mouse_motion(x, y, dx, dy)

    def on_text(self, text: str) -> None:
        if self._scene_manager:
            self._scene_manager.on_text(text)

    def on_resize(self, width: int, height: int) -> None:
        super().on_resize(width, height)
        if self._scene_manager:
            self._scene_manager.on_resize(width, height)
