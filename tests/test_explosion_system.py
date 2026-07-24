"""Tests for detonation dispatch and cluster/super/rubble powerup combinations."""

from core.components import BombComponent, TileKind
from core.state import GameState
from engine.physics import PhysicsSpace
from systems.bomb_system import DetonationEvent
from systems.event_bus import EventBus
from systems.explosion_system import process_detonations


def _make_empty_state(cols: int = 15, rows: int = 15) -> GameState:
    tiles = [[TileKind.EMPTY for _ in range(cols)] for _ in range(rows)]
    return GameState(tick=0, map_cols=cols, map_rows=rows, tiles=tiles)


def _make_space(state: GameState) -> PhysicsSpace:
    space = PhysicsSpace()
    space.rebuild_static_walls(state.tiles)
    return space


def test_cluster_alone_spawns_plain_sub_bombs() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
        col=7, row=7, px=0, py=0, is_cluster=True,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=2, owner_id=0, is_cluster=True,
    )
    process_detonations(state, space, [det], EventBus())

    sub_bombs = [b for b in state.bombs if b.owner_id == -1]
    assert sub_bombs
    assert all(not b.is_super and not b.is_rubble for b in sub_bombs)


def test_cluster_combined_with_super_upgrades_sub_bombs() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
        col=7, row=7, px=0, py=0, is_cluster=True, is_super=True,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=2, owner_id=0,
        is_cluster=True, is_super=True,
    )
    process_detonations(state, space, [det], EventBus())

    sub_bombs = [b for b in state.bombs if b.owner_id == -1]
    assert sub_bombs
    assert all(b.is_super for b in sub_bombs)


def test_cluster_combined_with_rubble_upgrades_sub_bombs() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
        col=7, row=7, px=0, py=0, is_cluster=True, is_rubble=True,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=2, owner_id=0,
        is_cluster=True, is_rubble=True,
    )
    process_detonations(state, space, [det], EventBus())

    sub_bombs = [b for b in state.bombs if b.owner_id == -1]
    assert sub_bombs
    assert all(b.is_rubble for b in sub_bombs)


def test_rubble_alone_uses_half_radius() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
        col=7, row=7, px=0, py=0, is_rubble=True,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=4, owner_id=0, is_rubble=True,
    )
    process_detonations(state, space, [det], EventBus())

    # half radius of 4 -> reaches col/row 5..9 but not col 3 or col 11
    lit = {(e.col, e.row) for e in state.explosions}
    assert (5, 7) in lit
    assert (3, 7) not in lit


def test_rubble_combined_with_super_uses_full_radius() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
        col=7, row=7, px=0, py=0, is_rubble=True, is_super=True,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=4, owner_id=0,
        is_rubble=True, is_super=True,
    )
    process_detonations(state, space, [det], EventBus())

    # full radius of 4 -> now reaches col 3, which the un-combined rubble bomb didn't
    lit = {(e.col, e.row) for e in state.explosions}
    assert (3, 7) in lit
