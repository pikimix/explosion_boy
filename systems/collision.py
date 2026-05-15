"""Pure occupancy query functions over GameState. No mutations."""
from __future__ import annotations

from core.components import PowerupComponent, TileKind
from core.state import GameState
from engine.config import TILE_SIZE


def px_to_grid(px: float, py: float) -> tuple[int, int]:
    return int(px // TILE_SIZE), int(py // TILE_SIZE)


def cell_is_passable(state: GameState, col: int, row: int) -> bool:
    if row < 0 or row >= state.map_rows or col < 0 or col >= state.map_cols:
        return False
    return state.tiles[row][col] == TileKind.EMPTY


def cell_has_bomb(state: GameState, col: int, row: int) -> bool:
    return any(b.col == col and b.row == row for b in state.bombs)


def cell_has_explosion(state: GameState, col: int, row: int) -> bool:
    if any(e.col == col and e.row == row for e in state.explosions):
        return True
    return any(
        _ray_covers(r, col, row) for r in state.explosion_rays
    )


def cell_has_powerup(state: GameState, col: int, row: int) -> PowerupComponent | None:
    for p in state.powerups:
        if p.col == col and p.row == row:
            return p
    return None


def players_at(state: GameState, col: int, row: int) -> list[int]:
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
