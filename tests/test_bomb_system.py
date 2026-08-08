"""Tests for bomb placement: capacity gating and special-bomb-type flags."""

from core.components import PhysicsState, PlayerInput, PlayerStats, TileKind
from core.state import GameState
from engine.physics import PhysicsSpace
from systems.bomb_system import apply_new_bombs, process_fuses


def _make_empty_state(cols: int = 15, rows: int = 15) -> GameState:
    tiles = [[TileKind.EMPTY for _ in range(cols)] for _ in range(rows)]
    return GameState(tick=0, map_cols=cols, map_rows=rows, tiles=tiles)


def _make_space(state: GameState) -> PhysicsSpace:
    space = PhysicsSpace()
    space.rebuild_static_walls(state.tiles)
    return space


def _add_player(state: GameState, pid: int, col: int, row: int, **stat_overrides) -> PlayerStats:
    stats = PlayerStats(player_id=pid, bomb_capacity=2, **stat_overrides)
    state.players[pid] = stats
    state.player_physics[pid] = PhysicsState(x=col * 48 + 24, y=row * 48 + 24)
    return stats


def _place(state: GameState, space: PhysicsSpace, pid: int) -> None:
    apply_new_bombs(state, space, [
        PlayerInput(player_id=pid, tick=0, move_x=0.0, move_y=0.0, place_bomb=True),
    ])


def test_smoke_bomb_placed_exclusively_when_super_pending() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    _add_player(state, pid=0, col=5, row=5, has_smoke_bomb=True, has_super_bomb=True)

    _place(state, space, pid=0)

    assert len(state.bombs) == 1
    bomb = state.bombs[0]
    assert bomb.is_smoke is True
    assert bomb.is_super is False
    assert bomb.is_cluster is False
    assert bomb.is_rubble is False


def test_smoke_consumed_leaves_other_pending_flags_for_next_placement() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    stats = _add_player(state, pid=0, col=5, row=5, has_smoke_bomb=True, has_super_bomb=True)

    _place(state, space, pid=0)
    assert stats.has_smoke_bomb is False
    assert stats.has_super_bomb is True

    # Free up capacity (as if the smoke bomb had detonated) so the next
    # placement isn't blocked by bombs_in_use >= bomb_capacity, and move
    # off the smoke bomb's cell so the new bomb isn't skipped as a dupe.
    state.bombs.clear()
    stats.bombs_in_use = 0
    state.player_physics[0] = PhysicsState(x=8 * 48 + 24, y=8 * 48 + 24)

    _place(state, space, pid=0)

    assert len(state.bombs) == 1
    bomb = state.bombs[0]
    assert bomb.is_super is True
    assert bomb.is_smoke is False


def test_smoke_bomb_radius_combines_power_and_capacity() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    _add_player(state, pid=0, col=5, row=5, has_smoke_bomb=True, blast_radius=3)

    _place(state, space, pid=0)

    # _add_player defaults bomb_capacity to 2.
    assert state.bombs[0].blast_radius == 3 + 2


def test_normal_flags_still_combine_without_smoke_pending() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    _add_player(
        state, pid=0, col=5, row=5,
        has_super_bomb=True, has_cluster_bomb=True, has_rubble_bomb=True,
    )

    _place(state, space, pid=0)

    bomb = state.bombs[0]
    assert bomb.is_super is True
    assert bomb.is_cluster is True
    assert bomb.is_rubble is True
    assert bomb.is_smoke is False


def test_process_fuses_copies_is_smoke_onto_detonation_event() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    _add_player(state, pid=0, col=5, row=5, has_smoke_bomb=True)
    _place(state, space, pid=0)
    state.bombs[0].fuse_ticks_remaining = 1

    detonations = process_fuses(state)

    assert len(detonations) == 1
    assert detonations[0].is_smoke is True
