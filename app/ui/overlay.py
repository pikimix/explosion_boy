"""Shared screen overlays."""
from __future__ import annotations

import arcade

_rejected_title: arcade.Text | None = None
_rejected_reason: arcade.Text | None = None
_reconnecting_text: arcade.Text | None = None


def draw_rejected(reason: str) -> None:
    """Draw a full-screen error overlay for version/connection rejection."""
    global _rejected_title, _rejected_reason
    win = arcade.get_window()
    cx, cy = win.width / 2, win.height / 2
    arcade.draw_rect_filled(
        arcade.XYWH(cx, cy, win.width, win.height),
        (0, 0, 0, 220),
    )
    if _rejected_title is None:
        _rejected_title = arcade.Text(
            "Connection Rejected",
            cx, cy + 30,
            arcade.color.RED,
            font_size=28,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        _rejected_reason = arcade.Text(
            reason,
            cx, cy - 20,
            arcade.color.WHITE,
            font_size=16,
            anchor_x="center",
            anchor_y="center",
        )
    assert _rejected_reason is not None
    _rejected_title.x, _rejected_title.y = cx, cy + 30
    _rejected_title.draw()
    _rejected_reason.text = reason
    _rejected_reason.x, _rejected_reason.y = cx, cy - 20
    _rejected_reason.draw()


def draw_reconnecting() -> None:
    """Draw a semi-transparent 'Reconnecting…' overlay over the current frame."""
    global _reconnecting_text
    win = arcade.get_window()
    cx, cy = win.width / 2, win.height / 2
    arcade.draw_rect_filled(
        arcade.XYWH(cx, cy, win.width, win.height),
        (0, 0, 0, 160),
    )
    if _reconnecting_text is None:
        _reconnecting_text = arcade.Text(
            "Reconnecting…",
            cx, cy,
            arcade.color.WHITE,
            font_size=24,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
    _reconnecting_text.x, _reconnecting_text.y = cx, cy
    _reconnecting_text.draw()
