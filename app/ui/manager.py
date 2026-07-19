"""Thin arcade.gui.UIManager wrapper."""
from __future__ import annotations

import arcade.gui


class UIManager:
    """Thin wrapper around ``arcade.gui.UIManager``."""

    def __init__(self) -> None:
        self._manager = arcade.gui.UIManager()

    def enable(self) -> None:
        """Enable the underlying UI manager so it receives events."""
        self._manager.enable()

    def disable(self) -> None:
        """Disable the underlying UI manager so it stops receiving events."""
        self._manager.disable()

    def draw(self) -> None:
        """Draw all UI elements registered with the underlying manager."""
        self._manager.draw()

    @property
    def inner(self) -> arcade.gui.UIManager:
        """Return the wrapped ``arcade.gui.UIManager`` instance."""
        return self._manager
