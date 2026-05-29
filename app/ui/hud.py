"""Per-player HUD rendered as a vertical list on the left side of the screen."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import PLAYER_COLOURS

_X = 10.0
_TOP_MARGIN = 10.0
_LINE_HEIGHT = 22.0


def draw(state: GameState) -> None:
    win = arcade.get_window()
    y = win.height - _TOP_MARGIN
    for pid, stats in sorted(state.players.items()):
        colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
        name = state.player_names.get(pid, f'P{pid + 1}')
        label = (
            f'{name}  \U0001f4a3 {stats.bomb_capacity - stats.bombs_in_use}'
            f'  \U0001f525 {stats.blast_radius}'
        )
        arcade.draw_text(
            label, _X, y,
            color=colour[:3],
            font_size=14,
            bold=True,
            anchor_x='left',
            anchor_y='top',
        )
        y -= _LINE_HEIGHT
