"""Shared screen overlays."""
from __future__ import annotations

import arcade


def draw_reconnecting() -> None:
    """Draw a semi-transparent 'Reconnecting…' overlay over the current frame."""
    win = arcade.get_window()
    cx, cy = win.width / 2, win.height / 2
    arcade.draw_rect_filled(
        arcade.XYWH(cx, cy, win.width, win.height),
        (0, 0, 0, 160),
    )
    arcade.draw_text(
        "Reconnecting…",
        cx, cy,
        arcade.color.WHITE,
        font_size=24,
        bold=True,
        anchor_x="center",
        anchor_y="center",
    )
