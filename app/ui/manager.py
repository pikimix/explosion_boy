"""Thin arcade.gui.UIManager wrapper."""
from __future__ import annotations

import arcade.gui


class UIManager:
    def __init__(self) -> None:
        self._manager = arcade.gui.UIManager()

    def enable(self) -> None:
        self._manager.enable()

    def disable(self) -> None:
        self._manager.disable()

    def draw(self) -> None:
        self._manager.draw()

    @property
    def inner(self) -> arcade.gui.UIManager:
        return self._manager
