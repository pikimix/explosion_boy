"""Shared volume bar widget drawn in the bottom-right corner of the screen."""
from __future__ import annotations

import arcade


def draw(volume: float) -> None:
    win = arcade.get_window()
    bar_w, bar_h = 120, 12
    padding = 14
    hint_gap = 6

    bar_right = win.width - padding
    bar_left = bar_right - bar_w
    bar_cx = bar_left + bar_w / 2
    bar_y = padding + bar_h / 2

    label_h = 18
    bg_inner_pad = 8
    bg_w = bar_w + hint_gap * 2 + 16 + bg_inner_pad * 2
    bg_h = bar_h + label_h + 4 + bg_inner_pad * 2
    bg_y = bar_y + (label_h + 4) / 2 - bg_inner_pad / 2
    arcade.draw_rect_filled(
        arcade.XYWH(bar_cx, bg_y, bg_w, bg_h),
        (0, 0, 0, 140),
    )

    arcade.draw_rect_filled(
        arcade.XYWH(bar_cx, bar_y, bar_w, bar_h),
        (60, 60, 60, 180),
    )
    fill_w = bar_w * volume
    if fill_w > 0:
        arcade.draw_rect_filled(
            arcade.XYWH(bar_left + fill_w / 2, bar_y, fill_w, bar_h),
            (220, 220, 220, 220),
        )
    arcade.draw_rect_outline(
        arcade.XYWH(bar_cx, bar_y, bar_w, bar_h),
        (200, 200, 200, 180),
        border_width=1,
    )
    arcade.draw_text(
        f'\U0001f50a {int(volume * 100)}%',
        bar_cx, bar_y + bar_h / 2 + 4,
        color=(220, 220, 220, 200),
        font_size=11,
        anchor_x='center',
        anchor_y='bottom',
    )
    arcade.draw_text(
        '[',
        bar_left - hint_gap, bar_y,
        color=(160, 160, 160, 180),
        font_size=11,
        anchor_x='right',
        anchor_y='center',
    )
    arcade.draw_text(
        ']',
        bar_right + hint_gap, bar_y,
        color=(160, 160, 160, 180),
        font_size=11,
        anchor_x='left',
        anchor_y='center',
    )
