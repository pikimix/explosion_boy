"""Volume bar widget drawn in the HUD strip at the bottom-left of the screen."""
from __future__ import annotations

import arcade

from app.ui.hud import HUD_WIDTH

_PADDING = 10.0
_BAR_H = 10
_BAR_W = HUD_WIDTH - _PADDING * 2


def draw(volume: float) -> None:
    bar_left = _PADDING
    bar_right = bar_left + _BAR_W
    bar_cx = bar_left + _BAR_W / 2
    bar_y = _PADDING + _BAR_H / 2

    label_h = 16
    bg_pad = 6
    bg_w = _BAR_W + bg_pad * 2
    bg_h = _BAR_H + label_h + 4 + bg_pad * 2
    bg_y = bar_y + (label_h + 4) / 2 - bg_pad / 2
    arcade.draw_rect_filled(
        arcade.XYWH(bar_cx, bg_y, bg_w, bg_h),
        (0, 0, 0, 140),
    )

    arcade.draw_rect_filled(
        arcade.XYWH(bar_cx, bar_y, _BAR_W, _BAR_H),
        (60, 60, 60, 180),
    )
    fill_w = _BAR_W * volume
    if fill_w > 0:
        arcade.draw_rect_filled(
            arcade.XYWH(bar_left + fill_w / 2, bar_y, fill_w, _BAR_H),
            (220, 220, 220, 220),
        )
    arcade.draw_rect_outline(
        arcade.XYWH(bar_cx, bar_y, _BAR_W, _BAR_H),
        (200, 200, 200, 180),
        border_width=1,
    )
    arcade.draw_text(
        f'\U0001f50a {int(volume * 100)}%  [ ]',
        bar_cx, bar_y + _BAR_H / 2 + 4,
        color=(220, 220, 220, 200),
        font_size=10,
        anchor_x='center',
        anchor_y='bottom',
    )
