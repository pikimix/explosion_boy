"""Per-player HUD: fixed-slot layout so width never grows with powerup state."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import PLAYER_COLOURS, POWERUP_COLOURS, POWERUP_SYMBOLS

HUD_WIDTH = 180.0
_X = 10.0
_TOP_MARGIN = 10.0
_NAME_SIZE = 14
_STAT_SIZE = 12
_SLOT_SIZE = 13
_NAME_H = 20.0
_STAT_H = 18.0
_SLOT_H = 20.0
_PLAYER_GAP = 8.0

# Horizontal spacing between boolean slot symbols
_SLOT_SPACING = 28.0

# Numeric stat column offsets from _X
_BOMB_X = _X
_BLAST_X = _X + 54.0
_SPEED_X = _X + 108.0

_LEGEND_SYMBOL_SIZE = 14
_LEGEND_LABEL_SIZE = 10
_LEGEND_H = 16.0
_LEGEND_LABEL_X = _X + 22.0
_LEGEND_LABEL = 'POWERUPS:'
_LEGEND_ENTRIES: list[tuple[str, str, tuple[int, int, int, int]]] = [
    (POWERUP_SYMBOLS[1], 'Extra bomb',    POWERUP_COLOURS[1]),
    (POWERUP_SYMBOLS[2], 'Blast up',      POWERUP_COLOURS[2]),
    (POWERUP_SYMBOLS[3], 'Shield',        POWERUP_COLOURS[3]),
    (POWERUP_SYMBOLS[4], 'Dizzy others',  POWERUP_COLOURS[4]),
    (POWERUP_SYMBOLS[5], 'Speed up',      POWERUP_COLOURS[5]),
    (POWERUP_SYMBOLS[6], 'Skull (bad)',   POWERUP_COLOURS[6]),
    (POWERUP_SYMBOLS[7], 'Super bomb',    POWERUP_COLOURS[7]),
    (POWERUP_SYMBOLS[8], 'Cluster bomb',  POWERUP_COLOURS[8]),
    (POWERUP_SYMBOLS[9], 'Rubble bomb',   POWERUP_COLOURS[9]),
    (POWERUP_SYMBOLS[10], 'Dizzy (self)', POWERUP_COLOURS[10]),
]

# Boolean powerup slots shown per player in a fixed row, left-to-right
_BOOL_SLOT_IDS = [3, 7, 8, 9, 10]

_legend_header: arcade.Text | None = None
_legend_symbol_texts: list[arcade.Text] = []
_legend_label_texts: list[arcade.Text] = []


def _greyscale(colour: tuple) -> tuple[int, int, int, int]:
    r, g, b = colour[0], colour[1], colour[2]
    lum = int(0.299 * r + 0.587 * g + 0.114 * b)
    v = max(40, lum // 2)
    return (v, v, v, 110)


def _slot_active(kind_id: int, stats) -> bool:
    return {
        3:  lambda s: s.shield,
        7:  lambda s: s.has_super_bomb,
        8:  lambda s: s.has_cluster_bomb,
        9:  lambda s: s.has_rubble_bomb,
        10: lambda s: s.reversed_controls_ticks > 0,
    }[kind_id](stats)


def draw(state: GameState) -> None:
    win = arcade.get_window()
    y = win.height - _TOP_MARGIN

    for pid, stats in sorted(state.players.items()):
        colour = state.player_colours.get(pid, PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
        name = state.player_names.get(pid, f'P{pid + 1}')

        # Name
        arcade.draw_text(
            name, _X, y,
            color=(*colour[:3], 255),
            font_size=_NAME_SIZE, bold=True,
            anchor_x='left', anchor_y='top',
        )
        y -= _NAME_H

        # Numeric stats: bombs available, blast radius, speed level
        available = stats.bomb_capacity - stats.bombs_in_use
        arcade.draw_text(
            f'\U0001f4a3 {available}', _BOMB_X, y,
            color=(*POWERUP_COLOURS[1][:3], 255),
            font_size=_STAT_SIZE, anchor_x='left', anchor_y='top',
        )
        arcade.draw_text(
            f'\U0001f525 {stats.blast_radius}', _BLAST_X, y,
            color=(*POWERUP_COLOURS[2][:3], 255),
            font_size=_STAT_SIZE, anchor_x='left', anchor_y='top',
        )
        speed_col = (
            (*POWERUP_COLOURS[5][:3], 255) if stats.speed_level > 0
            else _greyscale(POWERUP_COLOURS[5])
        )
        arcade.draw_text(
            f'⚡ {stats.speed_level}', _SPEED_X, y,
            color=speed_col,
            font_size=_STAT_SIZE, anchor_x='left', anchor_y='top',
        )
        y -= _STAT_H

        # Boolean powerup slots: full colour = active, greyscale = inactive
        sx = _X
        for kind_id in _BOOL_SLOT_IDS:
            active = _slot_active(kind_id, stats)
            col = (
                (*POWERUP_COLOURS[kind_id][:3], 255) if active
                else _greyscale(POWERUP_COLOURS[kind_id])
            )
            arcade.draw_text(
                POWERUP_SYMBOLS[kind_id], sx, y,
                color=col,
                font_size=_SLOT_SIZE, anchor_x='left', anchor_y='top',
            )
            sx += _SLOT_SPACING
        y -= _SLOT_H + _PLAYER_GAP

    _draw_legend(win)


def _draw_legend(win: arcade.Window) -> None:
    global _legend_header
    bottom_margin = 8.0
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
