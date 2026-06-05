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

_name_texts: dict[int, arcade.Text] = {}
_stat_texts: dict[int, arcade.Text] = {}


def draw(state: GameState) -> None:
    win = arcade.get_window()
    y = win.height - _TOP_MARGIN
    for pid, stats in sorted(state.players.items()):
        colour = state.player_colours.get(pid, PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
        name = state.player_names.get(pid, f'P{pid + 1}')

        if pid not in _name_texts:
            _name_texts[pid] = arcade.Text(
                name, _X, y,
                color=colour[:3], font_size=_NAME_SIZE, bold=True,
                anchor_x='left', anchor_y='top',
            )
        nt = _name_texts[pid]
        nt.text = name
        nt.y = y
        nt.color = colour[:3]
        nt.draw()
        y -= _NAME_H

        stat_str = (
            f'\U0001f4a3 {stats.bomb_capacity - stats.bombs_in_use}'
            f'  \U0001f525 {stats.blast_radius}'
        )
        if pid not in _stat_texts:
            _stat_texts[pid] = arcade.Text(
                stat_str, _X, y,
                color=colour[:3], font_size=_STAT_SIZE,
                anchor_x='left', anchor_y='top',
            )
        st = _stat_texts[pid]
        st.text = stat_str
        st.y = y
        st.color = colour[:3]
        st.draw()
        y -= _STAT_H + _PLAYER_GAP
