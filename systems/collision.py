"""Pure occupancy query functions over GameState. No mutations."""
from __future__ import annotations

from core.components import PowerupComponent, TileKind
from core.state import GameState
from engine.config import TILE_SIZE


def px_to_grid(px: float, py: float) -> tuple[int, int]:
    """Convert pixel coordinates to grid column/row indices.

    Parameters
    ----------
    px : float
        X position in pixels.
    py : float
        Y position in pixels.

    Returns
    -------
    tuple[int, int]
        The ``(col, row)`` grid indices containing the given pixel position.
    """
    return int(px // TILE_SIZE), int(py // TILE_SIZE)


def cell_is_passable(state: GameState, col: int, row: int) -> bool:
    """Check whether a grid cell is within bounds and not a solid tile.

    Parameters
    ----------
    state : GameState
        Current game state.
    col : int
        Grid column to check.
    row : int
        Grid row to check.

    Returns
    -------
    bool
        True if the cell is in bounds and empty, False otherwise.
    """
    if row < 0 or row >= state.map_rows or col < 0 or col >= state.map_cols:
        return False
    return state.tiles[row][col] == TileKind.EMPTY


def cell_has_bomb(state: GameState, col: int, row: int) -> bool:
    """Check whether a bomb occupies the given grid cell.

    Parameters
    ----------
    state : GameState
        Current game state.
    col : int
        Grid column to check.
    row : int
        Grid row to check.

    Returns
    -------
    bool
        True if any bomb is located at ``(col, row)``, False otherwise.
    """
    return any(b.col == col and b.row == row for b in state.bombs)


def cell_has_explosion(state: GameState, col: int, row: int) -> bool:
    """Check whether an explosion or explosion ray covers the given cell.

    Parameters
    ----------
    state : GameState
        Current game state.
    col : int
        Grid column to check.
    row : int
        Grid row to check.

    Returns
    -------
    bool
        True if an active explosion or explosion ray covers ``(col, row)``,
        False otherwise.
    """
    if any(e.col == col and e.row == row for e in state.explosions):
        return True
    return any(
        _ray_covers(r, col, row) for r in state.explosion_rays
    )


def cell_has_powerup(state: GameState, col: int, row: int) -> PowerupComponent | None:
    """Find the powerup located at the given grid cell, if any.

    Parameters
    ----------
    state : GameState
        Current game state.
    col : int
        Grid column to check.
    row : int
        Grid row to check.

    Returns
    -------
    PowerupComponent or None
        The powerup at ``(col, row)``, or None if the cell has no powerup.
    """
    for p in state.powerups:
        if p.col == col and p.row == row:
            return p
    return None


def players_at(state: GameState, col: int, row: int) -> list[int]:
    """Find the IDs of all players occupying the given grid cell.

    Parameters
    ----------
    state : GameState
        Current game state.
    col : int
        Grid column to check.
    row : int
        Grid row to check.

    Returns
    -------
    list[int]
        IDs of players whose current position maps to ``(col, row)``.
    """
    result = []
    for pid, phys in state.player_physics.items():
        pcol, prow = px_to_grid(phys.x, phys.y)
        if pcol == col and prow == row:
            result.append(pid)
    return result


def sync_grid_positions(state: GameState) -> None:
    """Update bomb col/row from their physics positions."""
    for bomb in state.bombs:
        bomb.col = int(bomb.px // TILE_SIZE)
        bomb.row = int(bomb.py // TILE_SIZE)


def _ray_covers(ray, col: int, row: int) -> bool:
    dc, dr = ray.direction
    for i in range(1, ray.length + 1):
        if ray.origin_col + dc * i == col and ray.origin_row + dr * i == row:
            return True
    return False
