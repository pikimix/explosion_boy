"""Per-player HUD rendered as a vertical list on the left side of the screen."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import PLAYER_COLOURS

HUD_WIDTH = 180.0
_X = 10.0
_TOP_MARGIN = 10.0
_NAME_SIZE = 14
_STAT_SIZE = 12
_NAME_H = 18.0
_STAT_H = 16.0
_PLAYER_GAP = 8.0


def draw(state: GameState) -> None:
    win = arcade.get_window()
    y = win.height - _TOP_MARGIN
    for pid, stats in sorted(state.players.items()):
        colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
        name = state.player_names.get(pid, f'P{pid + 1}')
        arcade.draw_text(
            name, _X, y,
            color=colour[:3],
            font_size=_NAME_SIZE,
            bold=True,
            anchor_x='left',
            anchor_y='top',
        )
        y -= _NAME_H
        arcade.draw_text(
            f'\U0001f4a3 {stats.bomb_capacity - stats.bombs_in_use}'
            f'  \U0001f525 {stats.blast_radius}',
            _X, y,
            color=colour[:3],
            font_size=_STAT_SIZE,
            anchor_x='left',
            anchor_y='top',
        )
        y -= _STAT_H + _PLAYER_GAP
