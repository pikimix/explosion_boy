"""Scene stack manager. Window delegates all lifecycle calls here."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BaseScene(Protocol):
    """Interface a scene must implement to be managed by `SceneManager`.

    Implementors are pushed onto the `SceneManager` stack and receive
    the calls below whenever they are the active (topmost) scene.
    """

    def update(self, dt: float) -> None:
        """Advance the scene's state by one frame; called every tick while active."""
        ...

    def draw(self) -> None:
        """Render the scene's current state; called every frame after `update`."""
        ...

    def on_key_press(self, key: int, modifiers: int) -> None:
        """Handle a key-down event forwarded from the window."""
        ...

    def on_key_release(self, key: int, modifiers: int) -> None:
        """Handle a key-up event forwarded from the window."""
        ...


class SceneManager:
    """Manage a stack of scenes, dispatching lifecycle and input events to the active one."""

    def __init__(self) -> None:
        self._stack: list[BaseScene] = []

    def push(self, scene: BaseScene) -> None:
        """Push a new scene onto the stack, making it the active scene.

        Parameters
        ----------
        scene : BaseScene
            The scene to push; it becomes the top of the stack and
            receives subsequent update/draw/input calls.
        """
        self._stack.append(scene)

    def pop(self) -> None:
        """Pop the active scene off the stack, if any, exposing the scene beneath it."""
        if self._stack:
            self._stack.pop()

    def replace(self, scene: BaseScene) -> None:
        """Replace the active scene with a new one.

        Parameters
        ----------
        scene : BaseScene
            The scene to push in place of the current active scene.
        """
        if self._stack:
            self._stack.pop()
        self._stack.append(scene)

    def update(self, dt: float) -> None:
        """Advance the active scene by one frame, if a scene is active.

        Parameters
        ----------
        dt : float
            Elapsed time in seconds since the last update.
        """
        if self._stack:
            self._stack[-1].update(dt)

    def draw(self) -> None:
        """Draw the active scene, if any."""
        if self._stack:
            self._stack[-1].draw()

    def on_key_press(self, key: int, modifiers: int) -> None:
        """Forward a key-down event to the active scene.

        Parameters
        ----------
        key : int
            The key symbol that was pressed.
        modifiers : int
            Bitmask of modifier keys held during the press.
        """
        if self._stack:
            self._stack[-1].on_key_press(key, modifiers)

    def on_key_release(self, key: int, modifiers: int) -> None:
        """Forward a key-up event to the active scene.

        Parameters
        ----------
        key : int
            The key symbol that was released.
        modifiers : int
            Bitmask of modifier keys held during the release.
        """
        if self._stack:
            self._stack[-1].on_key_release(key, modifiers)

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
        """Forward a mouse-button-down event to the active scene, if it supports it.

        Parameters
        ----------
        x : float
            The x-coordinate of the mouse at the time of the press.
        y : float
            The y-coordinate of the mouse at the time of the press.
        button : int
            The mouse button that was pressed.
        modifiers : int
            Bitmask of modifier keys held during the press.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_press'):
                scene.on_mouse_press(x, y, button, modifiers)

    def on_mouse_drag(
        self, x: float, y: float, dx: float, dy: float, buttons: int, modifiers: int
    ) -> None:
        """Forward a mouse-drag event to the active scene, if it supports it.

        Parameters
        ----------
        x : float
            The current x-coordinate of the mouse.
        y : float
            The current y-coordinate of the mouse.
        dx : float
            The change in x since the last event.
        dy : float
            The change in y since the last event.
        buttons : int
            Bitmask of mouse buttons held during the drag.
        modifiers : int
            Bitmask of modifier keys held during the drag.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_drag'):
                scene.on_mouse_drag(x, y, dx, dy, buttons, modifiers)

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
        """Forward a mouse-button-up event to the active scene, if it supports it.

        Parameters
        ----------
        x : float
            The x-coordinate of the mouse at the time of release.
        y : float
            The y-coordinate of the mouse at the time of release.
        button : int
            The mouse button that was released.
        modifiers : int
            Bitmask of modifier keys held during the release.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_release'):
                scene.on_mouse_release(x, y, button, modifiers)

    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
        """Forward a mouse-motion event to the active scene, if it supports it.

        Parameters
        ----------
        x : float
            The current x-coordinate of the mouse.
        y : float
            The current y-coordinate of the mouse.
        dx : float
            The change in x since the last event.
        dy : float
            The change in y since the last event.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_mouse_motion'):
                scene.on_mouse_motion(x, y, dx, dy)

    def on_text(self, text: str) -> None:
        """Forward a text-input event to the active scene, if it supports it.

        Parameters
        ----------
        text : str
            The text that was entered.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_text'):
                scene.on_text(text)

    def on_resize(self, width: int, height: int) -> None:
        """Forward a window-resize event to the active scene, if it supports it.

        Parameters
        ----------
        width : int
            The new width of the window in pixels.
        height : int
            The new height of the window in pixels.
        """
        if self._stack:
            scene = self._stack[-1]
            if hasattr(scene, 'on_resize'):
                scene.on_resize(width, height)
