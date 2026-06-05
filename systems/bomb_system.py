"""Bomb placement, fuse countdown, and detonation triggering."""
from __future__ import annotations

from dataclasses import dataclass

from core.components import BombComponent, PlayerInput
from core.state import GameState
from engine.config import BOMB_FUSE_TICKS, TILE_SIZE
from engine.physics import PhysicsSpace


@dataclass
class DetonationEvent:
    bomb_idx: int
    col: int
    row: int
    blast_radius: int
    owner_id: int


def apply_new_bombs(
    state: GameState,
    space: PhysicsSpace,
    inputs: list[PlayerInput],
) -> None:
    bomb_cells: set[tuple[int, int]] = {(b.col, b.row) for b in state.bombs}
    for inp in inputs:
        if not inp.place_bomb:
            continue
        pid = inp.player_id
        stats = state.players.get(pid)
        if stats is None:
            continue
        if stats.bombs_in_use >= stats.bomb_capacity:
            continue

        phys = state.player_physics.get(pid)
        if phys is None:
            continue

        col = int(phys.x // TILE_SIZE)
        row = int(phys.y // TILE_SIZE)

        if (col, row) in bomb_cells:
            continue

        px = col * TILE_SIZE + TILE_SIZE / 2
        py = row * TILE_SIZE + TILE_SIZE / 2

        bomb = BombComponent(
            owner_id=pid,
            fuse_ticks_remaining=BOMB_FUSE_TICKS,
            blast_radius=stats.blast_radius,
            col=col, row=row,
            px=px, py=py,
        )
        state.bombs.append(bomb)
        space.add_bomb(len(state.bombs) - 1, px, py)
        stats.bombs_in_use += 1
        bomb_cells.add((col, row))


def sync_pushed_bombs(state: GameState, space: PhysicsSpace) -> None:
    """Snap slow-moving bombs back to grid and update col/row."""
    for i, bomb in enumerate(state.bombs):
        pos = space.get_bomb_position(i)
        if pos is None:
            continue
        bx, by = pos
        # If velocity is below threshold, snap to nearest cell centre
        speed = (bomb.vx ** 2 + bomb.vy ** 2) ** 0.5
        if speed < 5.0:
            col = round((bx - TILE_SIZE / 2) / TILE_SIZE)
            row = round((by - TILE_SIZE / 2) / TILE_SIZE)
            snap_x = col * TILE_SIZE + TILE_SIZE / 2
            snap_y = row * TILE_SIZE + TILE_SIZE / 2
            bomb.px, bomb.py = snap_x, snap_y
            bomb.col, bomb.row = col, row
        else:
            bomb.px, bomb.py = bx, by
            bomb.col = int(bx // TILE_SIZE)
            bomb.row = int(by // TILE_SIZE)


def process_fuses(state: GameState) -> list[DetonationEvent]:
    detonations: list[DetonationEvent] = []
    for i, bomb in enumerate(state.bombs):
        bomb.fuse_ticks_remaining -= 1
        if bomb.fuse_ticks_remaining <= 0:
            detonations.append(DetonationEvent(
                bomb_idx=i,
                col=bomb.col, row=bomb.row,
                blast_radius=bomb.blast_radius,
                owner_id=bomb.owner_id,
            ))
    return detonations


def remove_bombs(
    state: GameState,
    space: PhysicsSpace,
    indices: list[int],
) -> None:
    """Remove bombs by index (highest first to preserve indices)."""
    for i in sorted(indices, reverse=True):
        if i < len(state.bombs):
            bomb = state.bombs[i]
            owner = state.players.get(bomb.owner_id)
            if owner and owner.bombs_in_use > 0:
                owner.bombs_in_use -= 1
            space.remove_bomb(i)
            state.bombs.pop(i)
    # Re-register remaining bomb bodies so indices stay consistent
    _reindex_bomb_bodies(state, space)


def _reindex_bomb_bodies(state: GameState, space: PhysicsSpace) -> None:
    """After removal, re-add bomb bodies at correct indices."""
    for idx in list(space.bomb_indices()):
        space.remove_bomb(idx)
    for i, bomb in enumerate(state.bombs):
        space.add_bomb(i, bomb.px, bomb.py)
