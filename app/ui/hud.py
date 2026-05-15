"""Per-player HUD rendered along the top and bottom screen edges."""
from __future__ import annotations

import arcade

from core.state import GameState
from engine.config import MAX_PLAYERS, PLAYER_COLOURS, WINDOW_H, WINDOW_W

_HALF = MAX_PLAYERS // 2  # 8 per edge

# Precompute (x, y, anchor_x, anchor_y) for all MAX_PLAYERS slots.
# Players 0.._HALF-1 → top edge; _HALF..MAX_PLAYERS-1 → bottom edge.
_HUD_POSITIONS: list[tuple[float, float, str, str]] = []
for _i in range(_HALF):
    _x = 10.0 + (WINDOW_W - 20) * _i / (_HALF - 1)
    _ax = "left" if _i == 0 else ("right" if _i == _HALF - 1 else "center")
    _HUD_POSITIONS.append((_x, WINDOW_H - 10, _ax, "top"))
for _i in range(_HALF):
    _x = 10.0 + (WINDOW_W - 20) * _i / (_HALF - 1)
    _ax = "left" if _i == 0 else ("right" if _i == _HALF - 1 else "center")
    _HUD_POSITIONS.append((_x, 10.0, _ax, "bottom"))


def draw(state: GameState) -> None:
    for pid, stats in state.players.items():
        x, y, anchor_x, anchor_y = _HUD_POSITIONS[pid % len(_HUD_POSITIONS)]
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
