"""Explosion propagation, chain reactions, player kills, and soft block destruction."""
from __future__ import annotations

from collections import deque

from core.components import (
    ExplosionCenter,
    ExplosionRay,
    TileKind,
)
from core.state import GameState
from core.tick import TICK_DT
from engine.config import EXPLOSION_DURATION_TICKS, TILE_SIZE
from engine.physics import PhysicsSpace
from systems.bomb_system import DetonationEvent, remove_bombs
from systems.collision import px_to_grid
from systems.event_bus import (
    BombDetonatedEvent,
    EventBus,
    PlayerDiedEvent,
    SoftBlockDestroyedEvent,
)
from systems.powerup_system import maybe_drop_powerup

_DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


def process_detonations(
    state: GameState,
    space: PhysicsSpace,
    detonations: list[DetonationEvent],
    bus: EventBus,
) -> None:
    queue: deque[DetonationEvent] = deque(detonations)
    processed_indices: set[int] = set()
    cluster_origins: list[tuple[int, int, int]] = []
    bomb_by_cell: dict[tuple[int, int], int] = {
        (b.col, b.row): bi for bi, b in enumerate(state.bombs)
    }

    while queue:
        det = queue.popleft()
        if det.bomb_idx in processed_indices:
            continue
        processed_indices.add(det.bomb_idx)

        bus.emit(BombDetonatedEvent(det.col, det.row))

        if det.is_super:
            _super_bomb_explosion(state, space, det, bus, bomb_by_cell, queue, processed_indices)
        else:
            state.explosions.append(
                ExplosionCenter(det.col, det.row, EXPLOSION_DURATION_TICKS)
            )

            for dc, dr in _DIRECTIONS:
                ray_len = 0
                for dist in range(1, det.blast_radius + 1):
                    c = det.col + dc * dist
                    r = det.row + dr * dist

                    if r < 0 or r >= state.map_rows or c < 0 or c >= state.map_cols:
                        break
                    tile = state.tiles[r][c]

                    if tile == TileKind.SOLID_WALL:
                        break

                    if tile == TileKind.SOFT_BLOCK:
                        state.tiles[r][c] = TileKind.EMPTY
                        state.tiles_dirty = True
                        bus.emit(SoftBlockDestroyedEvent(c, r))
                        maybe_drop_powerup(state, c, r)
                        # Rebuild static walls to remove this block from physics
                        space.rebuild_static_walls(state.tiles)
                        ray_len = dist
                        break

                    # Check for chain-reacting bomb at this cell
                    bi = bomb_by_cell.get((c, r))
                    if bi is not None and bi not in processed_indices:
                        bomb = state.bombs[bi]
                        queue.append(DetonationEvent(
                            bomb_idx=bi,
                            col=bomb.col, row=bomb.row,
                            blast_radius=bomb.blast_radius,
                            owner_id=bomb.owner_id,
                            is_super=bomb.is_super,
                            is_cluster=bomb.is_cluster,
                        ))

                    ray_len = dist

                if ray_len > 0:
                    state.explosion_rays.append(ExplosionRay(
                        origin_col=det.col, origin_row=det.row,
                        direction=(dc, dr), length=ray_len,
                        ticks_remaining=EXPLOSION_DURATION_TICKS,
                    ))

        if det.is_cluster:
            cluster_origins.append((det.col, det.row, det.blast_radius))

    remove_bombs(state, space, list(processed_indices))
    if cluster_origins:
        _spawn_cluster_sub_bombs(state, space, cluster_origins)
    _kill_players_in_explosions(state, bus)


def _super_bomb_explosion(
    state: GameState,
    space: PhysicsSpace,
    det: DetonationEvent,
    bus: EventBus,
    bomb_by_cell: dict[tuple[int, int], int],
    queue: deque[DetonationEvent],
    processed_indices: set[int],
) -> None:
    """AOE explosion scaled to half the owner's blast radius (min 5×5), passes through solid walls."""
    needs_rebuild = False
    half = max(2, det.blast_radius // 2)
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            c, r = det.col + dc, det.row + dr
            if not (0 <= r < state.map_rows and 0 <= c < state.map_cols):
                continue
            state.explosions.append(ExplosionCenter(c, r, EXPLOSION_DURATION_TICKS))
            if state.tiles[r][c] == TileKind.SOFT_BLOCK:
                state.tiles[r][c] = TileKind.EMPTY
                state.tiles_dirty = True
                bus.emit(SoftBlockDestroyedEvent(c, r))
                maybe_drop_powerup(state, c, r)
                needs_rebuild = True
            bi = bomb_by_cell.get((c, r))
            if bi is not None and bi not in processed_indices and bi != det.bomb_idx:
                b = state.bombs[bi]
                queue.append(DetonationEvent(
                    bomb_idx=bi, col=b.col, row=b.row,
                    blast_radius=b.blast_radius, owner_id=b.owner_id,
                    is_super=b.is_super, is_cluster=b.is_cluster,
                ))
    if needs_rebuild:
        space.rebuild_static_walls(state.tiles)


def _spawn_cluster_sub_bombs(
    state: GameState,
    space: PhysicsSpace,
    origins: list[tuple[int, int, int]],
) -> None:
    """Spawn up to 4 sub-bombs from each cluster origin; sub-bombs don't count toward cap."""
    from core.components import BombComponent
    from engine.config import TILE_SIZE
    from systems.powerup_system import CLUSTER_SUB_FUSE_TICKS

    for col, row, blast_radius in origins:
        bomb_cells = {(b.col, b.row) for b in state.bombs}
        for dc, dr in _DIRECTIONS:
            for dist in range(1, 4):
                c, r = col + dc * dist, row + dr * dist
                if not (0 <= r < state.map_rows and 0 <= c < state.map_cols):
                    break
                if state.tiles[r][c] != TileKind.EMPTY:
                    break  # wall or soft block stops placement in this direction
                if dist < 2:
                    continue  # walk through adjacent cell without placing
                if (c, r) in bomb_cells:
                    continue  # cell occupied — try one step further
                px = c * TILE_SIZE + TILE_SIZE / 2
                py = r * TILE_SIZE + TILE_SIZE / 2
                sub = BombComponent(
                    owner_id=-1,
                    fuse_ticks_remaining=CLUSTER_SUB_FUSE_TICKS,
                    blast_radius=blast_radius,
                    col=c, row=r, px=px, py=py,
                )
                state.bombs.append(sub)
                space.add_bomb(len(state.bombs) - 1, px, py)
                bomb_cells.add((c, r))
                break


def tick_explosions(state: GameState, bus: EventBus) -> None:
    """Age all active explosions. Player kills are handled by process_detonations."""
    state.explosions = [
        e for e in state.explosions
        if _tick_and_keep(e)
    ]
    state.explosion_rays = [
        r for r in state.explosion_rays
        if _tick_and_keep(r)
    ]


def _tick_and_keep(obj) -> bool:
    obj.ticks_remaining -= 1
    return obj.ticks_remaining > 0


def _kill_players_in_explosions(state: GameState, bus: EventBus) -> None:
    lit: set[tuple[int, int]] = {(e.col, e.row) for e in state.explosions}
    for ray in state.explosion_rays:
        dc, dr = ray.direction
        for i in range(1, ray.length + 1):
            lit.add((ray.origin_col + dc * i, ray.origin_row + dr * i))

    dead: list[int] = []
    for pid, phys in state.player_physics.items():
        col, row = px_to_grid(phys.x, phys.y)
        if (col, row) not in lit:
            continue
        stats = state.players.get(pid)
        if stats is not None and stats.shield_invincibility_ticks > 0:
            continue
        if stats is not None and stats.shield:
            stats.shield = False
            stats.shield_invincibility_ticks = EXPLOSION_DURATION_TICKS
        else:
            dead.append(pid)

    for pid in dead:
        state.players.pop(pid, None)
        state.player_physics.pop(pid, None)

    for pid in dead:
        bus.emit(PlayerDiedEvent(pid, state.tick))
