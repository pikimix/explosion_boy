"""Fixed-size map generation."""
from __future__ import annotations

import random

from core.components import TileKind
from engine.config import GRID_COLS, GRID_ROWS, SPAWN_POINTS


def generate_map(
    cols: int = GRID_COLS,
    rows: int = GRID_ROWS,
    num_players: int = 4,
    seed: int | None = None,
) -> list[list[TileKind]]:
    rng = random.Random(seed)
    tiles: list[list[TileKind]] = [
        [TileKind.EMPTY] * cols for _ in range(rows)
    ]

    # Border and alternating solid walls
    for row in range(rows):
        for col in range(cols):
            if row == 0 or row == rows - 1 or col == 0 or col == cols - 1:
                tiles[row][col] = TileKind.SOLID_WALL
            elif row % 2 == 0 and col % 2 == 0:
                tiles[row][col] = TileKind.SOLID_WALL

    # 2-tile safety zones around each active spawn point
    safe: set[tuple[int, int]] = set()
    for col, row in SPAWN_POINTS[:num_players]:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                safe.add((col + dc, row + dr))

    # Scatter soft blocks
    for row in range(rows):
        for col in range(cols):
            if tiles[row][col] != TileKind.EMPTY:
                continue
            if (col, row) in safe:
                continue
            if rng.random() < 0.65:
                tiles[row][col] = TileKind.SOFT_BLOCK

    return tiles


def spawn_position_px(player_idx: int) -> tuple[float, float]:
    """Return pixel centre for spawn point at index player_idx."""
    from engine.config import TILE_SIZE
    col, row = SPAWN_POINTS[player_idx]
    return col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2
