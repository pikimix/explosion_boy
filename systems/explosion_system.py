"""Explosion propagation, chain reactions, player kills, and soft block destruction."""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from core.components import (
    Cell,
    ExplosionCenter,
    ExplosionRay,
    SmokeCloud,
    TileKind,
)
from core.state import GameState
from engine.config import EXPLOSION_DURATION_TICKS, TICK_RATE, TILE_SIZE
from engine.physics import PhysicsSpace
from systems.bomb_system import DetonationEvent, remove_bombs
from systems.collision import px_to_grid
from systems.event_bus import BombDetonatedEvent, EventBus, SoftBlockDestroyedEvent
from systems.players import kill_players
from systems.powerup_system import maybe_drop_powerup

_DIRECTIONS = [(1, 0), (-1, 0), (0, 1), (0, -1)]


@dataclass(frozen=True)
class ClusterOrigin:
    """A cluster bomb's detonation point and the traits its sub-bombs inherit."""
    col: int
    row: int
    blast_radius: int
    blast_penetration: int
    is_super: bool
    is_rubble: bool


def process_detonations(
    state: GameState,
    space: PhysicsSpace,
    detonations: list[DetonationEvent],
    bus: EventBus,
) -> None:
    """Resolve a batch of bomb detonations, including chain reactions.

    Processes each detonation (dispatching to rubble/super/normal blast
    handling), following chain reactions into other bombs hit by the
    blast, spawning cluster-bomb sub-bombs, removing detonated bombs, and
    killing any players caught in the resulting explosions.

    Parameters
    ----------
    state : GameState
        Current game state; tiles, bombs, explosions, and players are
        updated in place.
    space : PhysicsSpace
        Physics space to remove detonated/chained bomb bodies from and
        to update destroyed-wall geometry on.
    detonations : list[DetonationEvent]
        Bombs whose fuses have just expired and must explode.
    bus : EventBus
        Event bus used to emit detonation, soft-block-destroyed, and
        player-died events.
    """
    if detonations:
        # New explosions/rays are about to be added — the cached lit-cell
        # set from _kill_players_in_explosions is no longer valid.
        state.lit_cells_dirty = True

    queue: deque[DetonationEvent] = deque(detonations)
    processed_indices: set[int] = set()
    cluster_origins: list[ClusterOrigin] = []
    bomb_by_cell: dict[Cell, int] = {
        Cell(b.col, b.row): bi for bi, b in enumerate(state.bombs)
    }
    # Cells already given an ExplosionCenter this batch — overlapping blasts
    # (chain reactions, adjacent super/rubble AOEs) would otherwise each
    # append their own duplicate entry for the same cell.
    lit_cells: set[Cell] = set()

    while queue:
        det = queue.popleft()
        if det.bomb_idx in processed_indices:
            continue
        processed_indices.add(det.bomb_idx)

        bus.emit(BombDetonatedEvent(det.col, det.row))

        if det.is_smoke:
            _spawn_smoke_cloud(state, det)
        elif det.is_rubble:
            _rubble_bomb_explosion(state, space, det, bus, bomb_by_cell, queue, processed_indices, lit_cells)
        elif det.is_super:
            _super_bomb_explosion(state, space, det, bus, bomb_by_cell, queue, processed_indices, lit_cells)
        else:
            if Cell(det.col, det.row) not in lit_cells:
                lit_cells.add(Cell(det.col, det.row))
                state.explosions.append(
                    ExplosionCenter(det.col, det.row, EXPLOSION_DURATION_TICKS)
                )

            for dc, dr in _DIRECTIONS:
                ray_len = 0
                blocks_destroyed = 0
                for dist in range(1, det.blast_radius + 1):
                    c = det.col + dc * dist
                    r = det.row + dr * dist

                    if r < 0 or r >= state.map_rows or c < 0 or c >= state.map_cols:
                        break
                    tile = state.tiles[r][c]

                    if tile == TileKind.SOLID_WALL:
                        break

                    if tile == TileKind.SOFT_BLOCK:
                        _destroy_soft_block(state, space, bus, c, r)
                        ray_len = dist
                        blocks_destroyed += 1
                        if blocks_destroyed >= det.blast_penetration:
                            break
                        continue  # penetrate through the now-empty block

                    # Check for chain-reacting bomb at this cell
                    bi = bomb_by_cell.get(Cell(c, r))
                    if bi is not None and bi not in processed_indices:
                        queue.append(DetonationEvent.from_bomb(bi, state.bombs[bi]))

                    ray_len = dist

                if ray_len > 0:
                    state.explosion_rays.append(ExplosionRay(
                        origin_col=det.col, origin_row=det.row,
                        direction=(dc, dr), length=ray_len,
                        ticks_remaining=EXPLOSION_DURATION_TICKS,
                    ))

        if det.is_cluster:
            cluster_origins.append(ClusterOrigin(
                col=det.col, row=det.row, blast_radius=det.blast_radius,
                blast_penetration=det.blast_penetration,
                is_super=det.is_super, is_rubble=det.is_rubble,
            ))

    remove_bombs(state, space, list(processed_indices))
    if cluster_origins:
        _spawn_cluster_sub_bombs(state, space, cluster_origins)
    _kill_players_in_explosions(state, bus)


def _destroy_soft_block(state: GameState, space: PhysicsSpace, bus: EventBus, c: int, r: int) -> None:
    """Clear a soft-block tile, roll its powerup drop, and remove its wall shape."""
    state.tiles[r][c] = TileKind.EMPTY
    state.tiles_dirty = True
    bus.emit(SoftBlockDestroyedEvent(c, r))
    maybe_drop_powerup(state, c, r)
    space.remove_wall(c, r)


def _aoe_blast(
    state: GameState,
    space: PhysicsSpace,
    bus: EventBus,
    det: DetonationEvent,
    bomb_by_cell: dict[Cell, int],
    queue: deque[DetonationEvent],
    processed_indices: set[int],
    lit_cells: set[Cell],
    half: int,
) -> list[Cell]:
    """Light a `half`-radius square AOE around det's origin, passing through solid walls.

    Marks each in-bounds cell lit, destroys any soft block there, and chain-reacts
    any bomb caught inside. Returns the in-bounds cells covered, for callers (e.g.
    rubble bombs) that need a further pass over the same area.
    """
    affected: list[Cell] = []
    for dr in range(-half, half + 1):
        for dc in range(-half, half + 1):
            c, r = det.col + dc, det.row + dr
            if not (0 <= r < state.map_rows and 0 <= c < state.map_cols):
                continue
            cell = Cell(c, r)
            affected.append(cell)
            if cell not in lit_cells:
                lit_cells.add(cell)
                state.explosions.append(ExplosionCenter(c, r, EXPLOSION_DURATION_TICKS))
            if state.tiles[r][c] == TileKind.SOFT_BLOCK:
                _destroy_soft_block(state, space, bus, c, r)
            bi = bomb_by_cell.get(cell)
            if bi is not None and bi not in processed_indices and bi != det.bomb_idx:
                queue.append(DetonationEvent.from_bomb(bi, state.bombs[bi]))
    return affected


def _super_bomb_explosion(
    state: GameState,
    space: PhysicsSpace,
    det: DetonationEvent,
    bus: EventBus,
    bomb_by_cell: dict[Cell, int],
    queue: deque[DetonationEvent],
    processed_indices: set[int],
    lit_cells: set[Cell],
) -> None:
    """AOE explosion scaled to half the owner's blast radius (min 5×5), passes through solid walls."""
    half = max(2, det.blast_radius // 2)
    _aoe_blast(state, space, bus, det, bomb_by_cell, queue, processed_indices, lit_cells, half)


def _rubble_bomb_explosion(
    state: GameState,
    space: PhysicsSpace,
    det: DetonationEvent,
    bus: EventBus,
    bomb_by_cell: dict[Cell, int],
    queue: deque[DetonationEvent],
    processed_indices: set[int],
    lit_cells: set[Cell],
) -> None:
    """AOE explosion like super bomb, then scatters soft blocks on empty cells (1-in-5 chance).

    Combined with a super powerup, the AOE is the full blast radius rather
    than halved, so collecting both upgrades the rubble bomb's reach.
    """
    half = det.blast_radius if det.is_super else max(2, det.blast_radius // 2)
    affected = _aoe_blast(state, space, bus, det, bomb_by_cell, queue, processed_indices, lit_cells, half)

    # Scatter new soft blocks on empty cells within the AOE (1-in-5 chance each)
    player_cells = {px_to_grid(phys.x, phys.y) for phys in state.player_physics.values()}
    bomb_cells = {Cell(b.col, b.row) for b in state.bombs}
    for cell in affected:
        c, r = cell.col, cell.row
        if state.tiles[r][c] == TileKind.EMPTY and cell not in player_cells and cell not in bomb_cells:
            if random.random() < 0.2:
                state.tiles[r][c] = TileKind.SOFT_BLOCK
                state.tiles_dirty = True
                space.add_wall(c, r)


def _spawn_smoke_cloud(state: GameState, det: DetonationEvent) -> None:
    """Spawn a smoke cloud — a pure visual utility effect, no damage or kill logic.

    Radius and fade duration are captured from the bomb's stats at
    placement time (det.blast_radius / det.blast_penetration), the same
    convention every other bomb type already uses. Smoke bombs never
    scatter soft blocks, damage players, or chain-react other bombs.

    The cloud holds at near-full opacity for blast_penetration*2 seconds,
    then fades out over an equal-length second phase — the client (see
    smoke.frag) splits ticks_total exactly in half to render this.
    """
    hold_seconds = det.blast_penetration * 2
    ticks_total = round(hold_seconds * 2 * TICK_RATE)
    state.smoke_clouds.append(SmokeCloud(
        col=det.col, row=det.row, radius=det.blast_radius,
        ticks_remaining=ticks_total, ticks_total=ticks_total,
    ))


def _spawn_cluster_sub_bombs(
    state: GameState,
    space: PhysicsSpace,
    origins: list[ClusterOrigin],
) -> None:
    """Spawn up to 4 sub-bombs from each cluster origin; sub-bombs don't count toward cap.

    Sub-bombs inherit the origin bomb's super/rubble status, so a cluster
    combined with a super or rubble powerup produces sub-bombs of that
    same upgraded kind.
    """
    from core.components import BombComponent
    from systems.powerup_system import CLUSTER_SUB_FUSE_TICKS

    for origin in origins:
        bomb_cells = {Cell(b.col, b.row) for b in state.bombs}
        for dc, dr in _DIRECTIONS:
            for dist in range(1, 4):
                c, r = origin.col + dc * dist, origin.row + dr * dist
                if not (0 <= r < state.map_rows and 0 <= c < state.map_cols):
                    break
                if state.tiles[r][c] != TileKind.EMPTY:
                    break  # wall or soft block stops placement in this direction
                if dist < 2:
                    continue  # walk through adjacent cell without placing
                if Cell(c, r) in bomb_cells:
                    continue  # cell occupied — try one step further
                px = c * TILE_SIZE + TILE_SIZE / 2
                py = r * TILE_SIZE + TILE_SIZE / 2
                sub = BombComponent(
                    owner_id=-1,
                    fuse_ticks_remaining=CLUSTER_SUB_FUSE_TICKS,
                    blast_radius=origin.blast_radius,
                    col=c, row=r, px=px, py=py,
                    blast_penetration=origin.blast_penetration,
                    is_super=origin.is_super,
                    is_rubble=origin.is_rubble,
                )
                state.bombs.append(sub)
                space.add_bomb(len(state.bombs) - 1, px, py)
                bomb_cells.add(Cell(c, r))
                break


def tick_explosions(state: GameState) -> None:
    """Age all active explosions. Player kills are handled by process_detonations."""
    prev_count = len(state.explosions) + len(state.explosion_rays)
    state.explosions = [
        e for e in state.explosions
        if _tick_and_keep(e)
    ]
    state.explosion_rays = [
        r for r in state.explosion_rays
        if _tick_and_keep(r)
    ]
    if len(state.explosions) + len(state.explosion_rays) != prev_count:
        # Something aged out — the cached lit-cell set no longer matches.
        state.lit_cells_dirty = True


def tick_smoke_clouds(state: GameState) -> None:
    """Age all active smoke clouds.

    Deliberately separate from tick_explosions: a smoke cloud's remaining
    life must never be shortened, cleared, or otherwise touched by nearby
    or overlapping bomb detonations — process_detonations never writes to
    state.smoke_clouds except to append new ones via _spawn_smoke_cloud.
    """
    state.smoke_clouds = [sc for sc in state.smoke_clouds if _tick_and_keep(sc)]


def _tick_and_keep(obj) -> bool:
    obj.ticks_remaining -= 1
    return obj.ticks_remaining > 0


def _kill_players_in_explosions(state: GameState, bus: EventBus) -> None:
    if state.lit_cells_dirty or state.lit_cells_cache is None:
        lit: set[Cell] = {Cell(e.col, e.row) for e in state.explosions}
        for ray in state.explosion_rays:
            dc, dr = ray.direction
            for i in range(1, ray.length + 1):
                lit.add(Cell(ray.origin_col + dc * i, ray.origin_row + dr * i))
        state.lit_cells_cache = lit
        state.lit_cells_dirty = False
    else:
        lit = state.lit_cells_cache

    dead: list[int] = []
    for pid, phys in state.player_physics.items():
        cell = px_to_grid(phys.x, phys.y)
        if cell not in lit:
            continue
        stats = state.players.get(pid)
        if stats is not None and stats.shield_invincibility_ticks > 0:
            continue
        if stats is not None and stats.shield:
            stats.shield = False
            stats.shield_invincibility_ticks = EXPLOSION_DURATION_TICKS
        else:
            dead.append(pid)

    kill_players(state, bus, dead)
