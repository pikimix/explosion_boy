"""Per-player HUD rendered as a vertical list on the left side of the screen."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import PLAYER_COLOURS, POWERUP_COLOURS, POWERUP_SYMBOLS

HUD_WIDTH = 180.0
_X = 10.0
_TOP_MARGIN = 10.0
_NAME_SIZE = 14
_STAT_SIZE = 12
_NAME_H = 18.0
_STAT_H = 16.0
_PLAYER_GAP = 8.0

_VOLUME_WIDGET_H = 10 + 10 + 28 + 4 + 6 * 2  # _PADDING + _BAR_H + _LABEL_H + 4 + _BG_PAD*2

_LEGEND_SYMBOL_SIZE = 14
_LEGEND_LABEL_SIZE = 10
_LEGEND_H = 16.0
_LEGEND_LABEL_X = _X + 22.0
_LEGEND_LABEL = 'POWERUPS:'
_LEGEND_ENTRIES: list[tuple[str, str, tuple[int, int, int, int]]] = [
    (POWERUP_SYMBOLS[1], 'Extra bomb',      POWERUP_COLOURS[1]),
    (POWERUP_SYMBOLS[2], 'Blast up',        POWERUP_COLOURS[2]),
    (POWERUP_SYMBOLS[3], 'Shield',          POWERUP_COLOURS[3]),
    (POWERUP_SYMBOLS[4], 'Reverse controls',POWERUP_COLOURS[4]),
    (POWERUP_SYMBOLS[5], 'Speed up',        POWERUP_COLOURS[5]),
    (POWERUP_SYMBOLS[6], 'Skull (bad)',     POWERUP_COLOURS[6]),
    (POWERUP_SYMBOLS[7], 'Super bomb',      POWERUP_COLOURS[7]),
    (POWERUP_SYMBOLS[8], 'Cluster bomb',    POWERUP_COLOURS[8]),
    (POWERUP_SYMBOLS[9], 'Rubble bomb',     POWERUP_COLOURS[9]),
]

_name_texts: dict[int, arcade.Text] = {}
_stat_texts: dict[int, arcade.Text] = {}
_legend_header: arcade.Text | None = None
_legend_symbol_texts: list[arcade.Text] = []
_legend_label_texts: list[arcade.Text] = []


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
            + (f'  ⚡{stats.speed_level}' if stats.speed_level > 0 else '')
            + ('  \U0001f6e1' if stats.shield else '')
            + ('  \U0001f635' if stats.reversed_controls_ticks > 0 else '')
            + ('  \U0001f4a5S' if stats.has_super_bomb else '')
            + ('  \U0001f4a5C' if stats.has_cluster_bomb else '')
            + ('  \U0001f4a5R' if stats.has_rubble_bomb else '')
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

    _draw_legend(win)


def _draw_legend(win: arcade.Window) -> None:
    global _legend_header
    bottom_margin = _VOLUME_WIDGET_H + 8.0
    total_h = _LEGEND_H + len(_LEGEND_ENTRIES) * _LEGEND_H
    y = bottom_margin + total_h - _LEGEND_H

    if _legend_header is None:
        _legend_header = arcade.Text(
            _LEGEND_LABEL, _X, y,
            color=(200, 200, 200, 200), font_size=_LEGEND_LABEL_SIZE, bold=True,
            anchor_x='left', anchor_y='bottom',
        )
        row_y = y - _LEGEND_H
        for symbol, label, colour in _LEGEND_ENTRIES:
            _legend_symbol_texts.append(arcade.Text(
                symbol, _X, row_y,
                color=colour[:3], font_size=_LEGEND_SYMBOL_SIZE,
                anchor_x='left', anchor_y='bottom',
            ))
            _legend_label_texts.append(arcade.Text(
                label, _LEGEND_LABEL_X, row_y,
                color=colour[:3], font_size=_LEGEND_LABEL_SIZE,
                anchor_x='left', anchor_y='bottom',
            ))
            row_y -= _LEGEND_H

    _legend_header.draw()
    row_y = y - _LEGEND_H
    for sym_t, lbl_t in zip(_legend_symbol_texts, _legend_label_texts):
        sym_t.y = row_y
        lbl_t.y = row_y
        sym_t.draw()
        lbl_t.draw()
        row_y -= _LEGEND_H
