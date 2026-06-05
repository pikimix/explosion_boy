"""Debug speed multiplier widget drawn above the volume widget in the HUD strip."""
from __future__ import annotations

import arcade

from app.ui.hud import HUD_WIDTH

_PADDING = 10.0
_WIDGET_H = 36
# Sit just above the volume widget (which occupies roughly the bottom 44px)
_BOTTOM_Y = 54.0
_BAR_CX = HUD_WIDTH / 2

_label: arcade.Text | None = None
_hint_label: arcade.Text | None = None


def draw(speed: float) -> None:
    global _label, _hint_label
    bg_w = HUD_WIDTH - _PADDING * 2
    cx = _BAR_CX

    arcade.draw_rect_filled(
        arcade.XYWH(cx, _BOTTOM_Y + _WIDGET_H / 2, bg_w + 12, _WIDGET_H),
        (0, 0, 0, 140),
    )

    if _label is None:
        _label = arcade.Text(
            '', cx, _BOTTOM_Y + 20,
            color=(220, 220, 220, 200),
            font_size=10, anchor_x='center', anchor_y='bottom',
        )
    _label.text = f'Speed: {speed:.3f}x'
    _label.draw()

    if _hint_label is None:
        _hint_label = arcade.Text(
            'press T to raise',
            cx, _BOTTOM_Y + 6,
            color=(160, 160, 160, 180),
            font_size=8, anchor_x='center', anchor_y='bottom',
        )
    _hint_label.draw()
