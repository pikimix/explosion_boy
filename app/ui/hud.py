"""Per-player HUD rendered along the top and bottom screen edges."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import MAX_PLAYERS, PLAYER_COLOURS

_HALF = MAX_PLAYERS // 2  # 8 per edge


def _hud_positions(w: float, h: float) -> list[tuple[float, float, str, str]]:
    positions: list[tuple[float, float, str, str]] = []
    for i in range(_HALF):
        x = 10.0 + (w - 20) * i / (_HALF - 1)
        ax = "left" if i == 0 else ("right" if i == _HALF - 1 else "center")
        positions.append((x, h - 10, ax, "top"))
    for i in range(_HALF):
        x = 10.0 + (w - 20) * i / (_HALF - 1)
        ax = "left" if i == 0 else ("right" if i == _HALF - 1 else "center")
        positions.append((x, 10.0, ax, "bottom"))
    return positions


def draw(state: GameState) -> None:
    win = arcade.get_window()
    positions = _hud_positions(win.width, win.height)
    for pid, stats in state.players.items():
        x, y, anchor_x, anchor_y = positions[pid % len(positions)]
        colour = PLAYER_COLOURS[pid % len(PLAYER_COLOURS)]
        label = (
            f"P{pid + 1}  \U0001f4a3 {stats.bomb_capacity - stats.bombs_in_use}"
            f"  \U0001f525 {stats.blast_radius}"
        )
        arcade.draw_text(
            label, x, y,
            color=colour[:3],
            font_size=14,
            bold=True,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
        )
