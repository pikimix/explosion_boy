"""Shared screen overlays."""
from __future__ import annotations

import arcade


def draw_rejected(reason: str) -> None:
    """Draw a full-screen error overlay for version/connection rejection."""
    win = arcade.get_window()
    cx, cy = win.width / 2, win.height / 2
    arcade.draw_rect_filled(
        arcade.XYWH(cx, cy, win.width, win.height),
        (0, 0, 0, 220),
    )
    arcade.draw_text(
        "Connection Rejected",
        cx, cy + 30,
        arcade.color.RED,
        font_size=28,
        bold=True,
        anchor_x="center",
        anchor_y="center",
    )
    arcade.draw_text(
        reason,
        cx, cy - 20,
        arcade.color.WHITE,
        font_size=16,
        anchor_x="center",
        anchor_y="center",
    )


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
