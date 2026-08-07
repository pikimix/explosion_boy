"""Progressive perimeter shrink: endgame ring closures that flash like a bomb
fuse before converting to unbreakable walls.

The map shrinks towards the spawn-appropriate size for however many players
are currently alive (see `update_shrink_target`), driven by player deaths
rather than a fixed player-count threshold. A pure time-based fallback still
forces the shrink to creep inward on a long stalemate where nobody dies."""
from __future__ import annotations

from core.components import TileKind
from core.state import GameState
from engine.config import (
    SHRINK_INTERVAL_TICKS,
    SHRINK_MIN_INTERIOR_AXIS,
    SHRINK_TRIGGER_TICKS,
    SHRINK_WARN_TICKS,
)
from engine.physics import PhysicsSpace
from systems.bomb_system import remove_bombs
from systems.collision import players_at
from systems.event_bus import EventBus, PlayerDiedEvent
from systems.world import map_size_for_player_count, ring_cells


def _can_close_ring(cols: int, rows: int, ring: int) -> bool:
    interior_rows = rows - 2 * ring - 2
    interior_cols = cols - 2 * ring - 2
    return min(interior_rows, interior_cols) >= SHRINK_MIN_INTERIOR_AXIS


def _ring_for_map_size(cols: int, rows: int, side: int) -> int:
    """Number of rings that must close for the map to shrink down to `side`."""
    return max(0, (min(cols, rows) - side) // 2)


def update_shrink_target(state: GameState) -> None:
    """Recompute the shrink target ring for the current alive-player count.

    Call this whenever the player count changes (a death or a disconnect) so
    `process_perimeter_shrink` shrinks the map towards the same size a fresh
    round would spawn for however many players are left."""
    if not state.players:
        return
    side, _ = map_size_for_player_count(len(state.players))
    state.shrink_target_ring = _ring_for_map_size(state.map_cols, state.map_rows, side)


def _time_forced_ring(tick: int) -> int:
    """Rings the pure stalemate timer alone demands by `tick`, regardless of
    player count — a safety net so a game with no deaths still ends."""
    if tick < SHRINK_TRIGGER_TICKS:
        return 0
    return 1 + (tick - SHRINK_TRIGGER_TICKS) // SHRINK_INTERVAL_TICKS


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
    """Drive the endgame perimeter shrink: trigger, warn, and close rings.

    Each tick, works out the ring the map should have shrunk to by now — the
    larger of `state.shrink_target_ring` (kept in sync with the current
    alive-player count by `update_shrink_target`) and a pure time-based
    stalemate floor — and, once a ring behind that, starts warning for the
    next ring. Closing a ring converts it to unbreakable wall, killing any
    players or bombs caught inside.

    A death-driven target (shrink_target_ring ahead of shrink_ring) starts
    the next ring's warning immediately, ignoring the cooldown between
    closures — only the stalemate timer's own progression is paced by
    SHRINK_INTERVAL_TICKS.

    Parameters
    ----------
    state : GameState
        Current game state; shrink progress fields, tiles, and players
        are updated in place.
    space : PhysicsSpace
        Physics space to add closed-ring walls to and remove destroyed
        bombs from.
    bus : EventBus
        Event bus used to emit `PlayerDiedEvent` for players caught in a
        closing ring.
    """
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
        if _can_close_ring(state.map_cols, state.map_rows, closed_ring + 1):
            state.shrink_next_warn_tick = state.tick + SHRINK_INTERVAL_TICKS - SHRINK_WARN_TICKS
        else:
            state.shrink_stopped = True
        return

    desired_ring = max(state.shrink_target_ring, _time_forced_ring(state.tick))
    if desired_ring <= state.shrink_ring:
        return

    death_driven = state.shrink_target_ring > state.shrink_ring
    if not death_driven and state.shrink_active and state.tick < state.shrink_next_warn_tick:
        return  # pace non-death (stalemate timer) closures SHRINK_INTERVAL_TICKS apart

    next_ring = state.shrink_ring + 1
    if not _can_close_ring(state.map_cols, state.map_rows, next_ring):
        state.shrink_stopped = True
        return
    state.shrink_active = True
    _start_ring_warning(state, next_ring)
