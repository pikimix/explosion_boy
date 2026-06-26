"""Scene stack manager. Window delegates all lifecycle calls here."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseScene(Protocol):
    def update(self, dt: float) -> None: ...
    def draw(self) -> None: ...
    def on_key_press(self, key: int, modifiers: int) -> None: ...
    def on_key_release(self, key: int, modifiers: int) -> None: ...


class SceneManager:
    def __init__(self) -> None:
        self._stack: list[BaseScene] = []

    def push(self, scene: BaseScene) -> None:
        self._stack.append(scene)

    def pop(self) -> None:
        if self._stack:
            self._stack.pop()

    def replace(self, scene: BaseScene) -> None:
        if self._stack:
            self._stack.pop()
        self._stack.append(scene)

    def update(self, dt: float) -> None:
        if self._stack:
            self._stack[-1].update(dt)

    def draw(self) -> None:
        if self._stack:
            self._stack[-1].draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        if self._stack:
            self._stack[-1].on_key_press(key, modifiers)

    def on_key_release(self, key: int, modifiers: int) -> None:
        if self._stack:
            self._stack[-1].on_key_release(key, modifiers)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_press'):
                scene.on_mouse_press(x, y, button, modifiers)

    def on_mouse_drag(
        self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int
    ) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_drag'):
                scene.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_release'):
                scene.on_mouse_release(x, y, button, modifiers)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_motion'):
                scene.on_mouse_motion(x, y, dx, dy)

    def on_text(self, text: str) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_text'):
                scene.on_text(text)

    def on_resize(self, width: int, height: int) -> None:
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_resize'):
                scene.on_resize(width, height)
