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
from systems.collision import cell_has_explosion, px_to_grid
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

    while queue:
        det = queue.popleft()
        if det.bomb_idx in processed_indices:
            continue
        processed_indices.add(det.bomb_idx)

        bus.emit(BombDetonatedEvent(det.col, det.row))
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
                    bus.emit(SoftBlockDestroyedEvent(c, r))
                    maybe_drop_powerup(state, c, r)
                    # Rebuild static walls to remove this block from physics
                    space.rebuild_static_walls(state.tiles)
                    ray_len = dist
                    break

                # Check for chain-reacting bomb at this cell
                for bi, bomb in enumerate(state.bombs):
                    if (bomb.col == c and bomb.row == r
                            and bi not in processed_indices):
                        queue.append(DetonationEvent(
                            bomb_idx=bi,
                            col=bomb.col, row=bomb.row,
                            blast_radius=bomb.blast_radius,
                            owner_id=bomb.owner_id,
                        ))

                ray_len = dist

            if ray_len > 0:
                state.explosion_rays.append(ExplosionRay(
                    origin_col=det.col, origin_row=det.row,
                    direction=(dc, dr), length=ray_len,
                    ticks_remaining=EXPLOSION_DURATION_TICKS,
                ))

    remove_bombs(state, space, list(processed_indices))
    _kill_players_in_explosions(state, bus)


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
    dead: list[int] = []
    for pid, phys in state.player_physics.items():
        col, row = px_to_grid(phys.x, phys.y)
        if cell_has_explosion(state, col, row):
            stats = state.players.get(pid)
            if stats is not None and stats.shield:
                stats.shield = False
            else:
                dead.append(pid)

    for pid in dead:
        bus.emit(PlayerDiedEvent(pid, state.tick))
        state.players.pop(pid, None)
        state.player_physics.pop(pid, None)
