"""Bomb placement, fuse countdown, and detonation triggering."""
from __future__ import annotations

from dataclasses import dataclass

from core.components import BombComponent, Cell, PlayerInput
from core.state import GameState
from engine.config import BOMB_FUSE_TICKS, TILE_SIZE
from engine.physics import PhysicsSpace


@dataclass
class DetonationEvent:
    """Describe a bomb that has finished its fuse and must detonate."""

    bomb_idx: int
    col: int
    row: int
    blast_radius: int
    owner_id: int
    is_super:          bool = False
    is_cluster:        bool = False
    is_rubble:         bool = False
    blast_penetration: int  = 1
    is_smoke:          bool = False


def apply_new_bombs(
    state: GameState,
    space: PhysicsSpace,
    inputs: list[PlayerInput],
) -> None:
    """Place a new bomb for each input requesting one, subject to capacity.

    Skips players who are unknown, at their bomb capacity, or standing on
    a physics-unmapped tile, and skips placement on a cell that already
    holds a bomb.

    Parameters
    ----------
    state : GameState
        Current game state; new bombs are appended to `state.bombs` and
        the placing player's `bombs_in_use` and pending bomb-type flags
        are updated.
    space : PhysicsSpace
        Physics space to register the new bomb bodies with.
    inputs : list[PlayerInput]
        Per-player inputs for this tick; only those with `place_bomb`
        set are considered.
    """
    bomb_cells: set[Cell] = {Cell(b.col, b.row) for b in state.bombs}
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

        if Cell(col, row) in bomb_cells:
            continue

        px = col * TILE_SIZE + TILE_SIZE / 2
        py = row * TILE_SIZE + TILE_SIZE / 2

        if stats.has_smoke_bomb:
            # Exclusive: never combines with super/cluster/rubble on this
            # bomb. Jumps the queue but does NOT discard the other pending
            # flags — they remain queued for this player's next placement.
            # Smoke has no real blast, so blast_radius here is repurposed
            # as the cloud's radius: blast power + bomb capacity combined,
            # so both stats grow the smoke coverage.
            bomb = BombComponent(
                owner_id=pid,
                fuse_ticks_remaining=BOMB_FUSE_TICKS,
                blast_radius=stats.blast_radius + stats.bomb_capacity,
                col=col, row=row,
                px=px, py=py,
                is_smoke=True,
                blast_penetration=stats.blast_penetration,
            )
            stats.has_smoke_bomb = False
        else:
            bomb = BombComponent(
                owner_id=pid,
                fuse_ticks_remaining=BOMB_FUSE_TICKS,
                blast_radius=stats.blast_radius,
                col=col, row=row,
                px=px, py=py,
                is_super=stats.has_super_bomb,
                is_cluster=stats.has_cluster_bomb,
                is_rubble=stats.has_rubble_bomb,
                blast_penetration=stats.blast_penetration,
            )
            stats.has_super_bomb = False
            stats.has_cluster_bomb = False
            stats.has_rubble_bomb = False
        state.bombs.append(bomb)
        space.add_bomb(len(state.bombs) - 1, px, py)
        stats.bombs_in_use += 1
        bomb_cells.add(Cell(col, row))


def sync_pushed_bombs(state: GameState, space: PhysicsSpace) -> None:
    """Snap slow-moving bombs back to grid and update col/row."""
    for i, bomb in enumerate(state.bombs):
        pos = space.get_bomb_position(i)
        if pos is None:
            continue
        bx, by = pos.x, pos.y
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
    """Count down every bomb's fuse and collect those that have expired.

    Parameters
    ----------
    state : GameState
        Current game state; each bomb's `fuse_ticks_remaining` is
        decremented in place.

    Returns
    -------
    list[DetonationEvent]
        One event per bomb whose fuse has reached zero, in bomb order.
    """
    detonations: list[DetonationEvent] = []
    for i, bomb in enumerate(state.bombs):
        bomb.fuse_ticks_remaining -= 1
        if bomb.fuse_ticks_remaining <= 0:
            detonations.append(DetonationEvent(
                bomb_idx=i,
                col=bomb.col, row=bomb.row,
                blast_radius=bomb.blast_radius,
                owner_id=bomb.owner_id,
                is_super=bomb.is_super,
                is_cluster=bomb.is_cluster,
                is_rubble=bomb.is_rubble,
                blast_penetration=bomb.blast_penetration,
                is_smoke=bomb.is_smoke,
            ))
    return detonations


def remove_bombs(
    state: GameState,
    space: PhysicsSpace,
    indices: list[int],
) -> None:
    """Remove bombs by index (highest first to preserve indices)."""
    if not indices:
        return
    for i in sorted(indices, reverse=True):
        if i < len(state.bombs):
            bomb = state.bombs[i]
            owner = state.players.get(bomb.owner_id)
            if owner and owner.bombs_in_use > 0:
                owner.bombs_in_use -= 1
            space.remove_bomb(i)
            state.bombs.pop(i)
    # Re-key remaining bomb bodies so indices stay consistent
    _reindex_bomb_bodies(space)


def _reindex_bomb_bodies(space: PhysicsSpace) -> None:
    """Renumber surviving bomb bodies to close the gaps left by removed ones.

    The caller already removed each detonated bomb's physics body by its old
    index; the survivors are still keyed by their old index, which no longer
    matches their compacted position in state.bombs. Re-key them in place —
    no pymunk body/shape recreation — so bombs unrelated to the removal keep
    their momentum instead of getting reset to a stop.
    """
    old_indices = sorted(space.bomb_indices())
    space.rekey_bombs({old: new for new, old in enumerate(old_indices)})
