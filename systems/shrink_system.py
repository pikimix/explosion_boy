"""Progressive perimeter shrink: endgame ring closures that flash like a bomb
fuse before converting to unbreakable walls."""
from __future__ import annotations

from core.components import TileKind
from core.state import GameState
from engine.config import (
    SHRINK_INTERVAL_TICKS,
    SHRINK_MIN_INTERIOR_AXIS,
    SHRINK_TRIGGER_PLAYER_COUNT,
    SHRINK_TRIGGER_TICKS,
    SHRINK_WARN_TICKS,
)
from engine.physics import PhysicsSpace
from systems.bomb_system import remove_bombs
from systems.collision import players_at
from systems.event_bus import EventBus, PlayerDiedEvent
from systems.world import ring_cells


def _can_close_ring(cols: int, rows: int, ring: int) -> bool:
    interior_rows = rows - 2 * ring - 2
    interior_cols = cols - 2 * ring - 2
    return min(interior_rows, interior_cols) >= SHRINK_MIN_INTERIOR_AXIS


def _start_ring_warning(state: GameState, ring: int) -> None:
    state.shrink_warn_ring = ring
    state.shrink_warn_ticks_remaining = SHRINK_WARN_TICKS


def _close_ring(state: GameState, space: PhysicsSpace, bus: EventBus, ring: int) -> None:
    dead: list[int] = []
    bomb_indices: list[int] = []
    for c, r in ring_cells(state.map_cols, state.map_rows, ring):
        if state.tiles[r][c] == TileKind.SOLID_WALL:
            continue
        state.tiles[r][c] = TileKind.SOLID_WALL
        state.tiles_dirty = True
        space.add_wall(c, r, TileKind.SOLID_WALL)
        dead.extend(players_at(state, c, r))
        bomb_indices.extend(i for i, b in enumerate(state.bombs) if b.col == c and b.row == r)

    if bomb_indices:
        remove_bombs(state, space, bomb_indices)

    for pid in dead:
        state.players.pop(pid, None)
        state.player_physics.pop(pid, None)
    for pid in dead:
        bus.emit(PlayerDiedEvent(pid, state.tick))


def process_perimeter_shrink(state: GameState, space: PhysicsSpace, bus: EventBus) -> None:
    if not state.shrink_active:
        player_trigger = (
            len(state.players) <= SHRINK_TRIGGER_PLAYER_COUNT < state.starting_player_count
        )
        if state.tick >= SHRINK_TRIGGER_TICKS or player_trigger:
            state.shrink_active = True
            _start_ring_warning(state, 1)
        return

    if state.shrink_stopped:
        return

    if state.shrink_warn_ring:
        state.shrink_warn_ticks_remaining -= 1
        if state.shrink_warn_ticks_remaining > 0:
            return
        closed_ring = state.shrink_warn_ring
        _close_ring(state, space, bus, closed_ring)
        state.shrink_ring = closed_ring
        state.shrink_warn_ring = 0
        next_ring = closed_ring + 1
        if _can_close_ring(state.map_cols, state.map_rows, next_ring):
            state.shrink_next_warn_tick = state.tick + SHRINK_INTERVAL_TICKS - SHRINK_WARN_TICKS
        else:
            state.shrink_stopped = True
    elif state.tick >= state.shrink_next_warn_tick:
        _start_ring_warning(state, state.shrink_ring + 1)
