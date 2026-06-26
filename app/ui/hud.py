"""Per-player HUD: fixed-slot layout so width never grows with powerup state."""
from __future__ import annotations

from dataclasses import dataclass, field

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
    (POWERUP_SYMBOLS[10], 'Dizzy (self)',    POWERUP_COLOURS[10]),
    (POWERUP_SYMBOLS[11], 'Blast pierce',    POWERUP_COLOURS[11]),
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


@dataclass
class _PlayerHud:
    name:        arcade.Text
    bombs:       arcade.Text
    blast:       arcade.Text
    speed:       arcade.Text
    penetration: arcade.Text
    slots:       list[arcade.Text] = field(default_factory=list)


_player_huds: dict[int, _PlayerHud] = {}


def _make_player_hud(pid: int) -> _PlayerHud:
    def _text(content: str, x: float, size: int, colour: tuple, bold: bool = False) -> arcade.Text:
        return arcade.Text(
            content, x, 0.0,
            color=colour, font_size=size, bold=bold,
            anchor_x='left', anchor_y='top',
        )

    slots = [
        _text(POWERUP_SYMBOLS[kid], _X + i * _SLOT_SPACING, _SLOT_SIZE, (255, 255, 255, 255))
        for i, kid in enumerate(_BOOL_SLOT_IDS)
    ]
    return _PlayerHud(
        name=_text(f'P{pid + 1}', _X, _NAME_SIZE, (255, 255, 255, 255), bold=True),
        bombs=_text('\U0001f4a3 1', _BOMB_X, _STAT_SIZE, (*POWERUP_COLOURS[1][:3], 255)),
        blast=_text('\U0001f525 2', _BLAST_X, _STAT_SIZE, (*POWERUP_COLOURS[2][:3], 255)),
        speed=_text('⚡ 0', _SPEED_X, _STAT_SIZE, (*POWERUP_COLOURS[5][:3], 255)),
        penetration=_text(f'{POWERUP_SYMBOLS[11]} 2', _BLAST_X, _STAT_SIZE, (*POWERUP_COLOURS[11][:3], 255)),
        slots=slots,
    )


def draw(state: GameState) -> None:
    win = arcade.get_window()

    # Drop cached huds for players who have left
    for pid in list(_player_huds):
        if pid not in state.players:
            del _player_huds[pid]

    y = win.height - _TOP_MARGIN

    for pid, stats in sorted(state.players.items()):
        if pid not in _player_huds:
            _player_huds[pid] = _make_player_hud(pid)
        hud = _player_huds[pid]

        colour = state.player_colours.get(pid, PLAYER_COLOURS[pid % len(PLAYER_COLOURS)][:3])
        name = state.player_names.get(pid, f'P{pid + 1}')

        # Name row
        hud.name.text = name
        hud.name.color = (*colour[:3], 255)
        hud.name.y = y
        hud.name.draw()
        y -= _NAME_H

        # Stat row 1: bombs / blast radius / speed
        available = stats.bomb_capacity - stats.bombs_in_use
        hud.bombs.text = f'\U0001f4a3 {available}'
        hud.bombs.y = y
        hud.bombs.draw()

        hud.blast.text = f'\U0001f525 {stats.blast_radius}'
        hud.blast.y = y
        hud.blast.draw()

        hud.speed.text = f'⚡ {stats.speed_level}'
        hud.speed.color = (
            (*POWERUP_COLOURS[5][:3], 255) if stats.speed_level > 0
            else _greyscale(POWERUP_COLOURS[5])
        )
        hud.speed.y = y
        hud.speed.draw()
        y -= _STAT_H

        # Stat row 2: blast penetration
        hud.penetration.text = f'{POWERUP_SYMBOLS[11]} {stats.blast_penetration}'
        hud.penetration.y = y
        hud.penetration.draw()
        y -= _STAT_H

        # Boolean powerup slots: full colour = active, greyscale = inactive
        for slot_text, kind_id in zip(hud.slots, _BOOL_SLOT_IDS):
            active = _slot_active(kind_id, stats)
            slot_text.color = (
                (*POWERUP_COLOURS[kind_id][:3], 255) if active
                else _greyscale(POWERUP_COLOURS[kind_id])
            )
            slot_text.y = y
            slot_text.draw()
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
