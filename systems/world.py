"""Map generation, sized per round to the player count."""
from __future__ import annotations

import random

from core.components import TileKind
from engine.config import (
    GRID_COLS,
    GRID_ROWS,
    MAX_GRID_SIZE,
    MAX_PLAYERS,
    MIN_GRID_SIZE,
    SPAWN_POINTS,
)

# SPAWN_POINTS was hand-tuned for this exact grid size — spawn_points_for_grid
# rescales those 16 relative positions into whatever grid a round actually uses.
_BASE_COLS, _BASE_ROWS = 29, 25


def generate_map(
    cols: int = GRID_COLS,
    rows: int = GRID_ROWS,
    num_players: int = 4,
    seed: int | None = None,
    spawn_points: list[tuple[int, int]] | None = None,
) -> list[list[TileKind]]:
    spawn_points = spawn_points if spawn_points is not None else SPAWN_POINTS
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
    for col, row in spawn_points[:num_players]:
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


def spawn_position_px(player_idx: int, spawn_points: list[tuple[int, int]] | None = None) -> tuple[float, float]:
    """Return pixel centre for spawn point at index player_idx."""
    from engine.config import TILE_SIZE
    spawn_points = spawn_points if spawn_points is not None else SPAWN_POINTS
    col, row = spawn_points[player_idx]
    return col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2


def _round_odd(x: float) -> int:
    """Round to the nearest odd integer, so cols/rows stay odd — generate_map's
    border sits at row/col 0 and -1, and pillars at even-col AND even-row, which
    only stays symmetric when the grid dimension itself is odd."""
    return 2 * round((x - 1) / 2) + 1


def map_size_for_player_count(n: int) -> tuple[int, int]:
    """Square grid side, scaled linearly from MIN_GRID_SIZE at 2 players up to
    MAX_GRID_SIZE at MAX_PLAYERS."""
    n = max(2, min(MAX_PLAYERS, n))
    t = (n - 2) / (MAX_PLAYERS - 2)
    side = _round_odd(MIN_GRID_SIZE + t * (MAX_GRID_SIZE - MIN_GRID_SIZE))
    return side, side


def _rescale_and_snap(base_v: int, base_dim: int, new_dim: int) -> int:
    ratio = (base_v - 1) / (base_dim - 2)
    v = 1 + round(ratio * (new_dim - 2))
    return max(1, min(new_dim - 2, v))


def _avoid_pillar(col: int, row: int) -> tuple[int, int]:
    if col % 2 == 0 and row % 2 == 0:
        row = row - 1 if row > 1 else row + 1
    return col, row


def spawn_points_for_grid(cols: int, rows: int) -> list[tuple[int, int]]:
    """Rescale the hand-tuned baseline SPAWN_POINTS layout into an arbitrary
    (cols, rows) grid, keeping each point's relative corner/edge/ring position
    and nudging it off any pillar cell it would otherwise land on."""
    result = []
    for base_col, base_row in SPAWN_POINTS:
        col = _rescale_and_snap(base_col, _BASE_COLS, cols)
        row = _rescale_and_snap(base_row, _BASE_ROWS, rows)
        result.append(_avoid_pillar(col, row))
    return result


def ring_cells(cols: int, rows: int, ring: int):
    """Yield the (col, row) cells forming the rectangular frame at distance
    `ring` from the border (ring 1 = one step in from the border generate_map
    already fills with SOLID_WALL)."""
    r0, r1 = ring, rows - 1 - ring
    c0, c1 = ring, cols - 1 - ring
    if r0 > r1 or c0 > c1:
        return
    for c in range(c0, c1 + 1):
        yield c, r0
        if r1 != r0:
            yield c, r1
    for r in range(r0 + 1, r1):
        yield c0, r
        if c1 != c0:
            yield c1, r
