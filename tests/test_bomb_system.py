"""Tests for bomb placement: capacity gating and special-bomb-type flags."""

from core.components import BombComponent, PhysicsState, PlayerInput, PlayerStats, TileKind
from core.state import GameState
from engine.physics import PhysicsSpace
from systems.bomb_system import apply_new_bombs, process_fuses, remove_bombs


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


def _add_bomb(state: GameState, space: PhysicsSpace, col: int, row: int) -> None:
    px, py = col * 48 + 24, row * 48 + 24
    idx = len(state.bombs)
    state.bombs.append(BombComponent(
        owner_id=0, fuse_ticks_remaining=10, blast_radius=2, col=col, row=row, px=px, py=py,
    ))
    space.add_bomb(idx, px, py)


def test_remove_bombs_with_nothing_to_remove_is_noop() -> None:
    """Regression: remove_bombs used to unconditionally reindex every bomb's
    pymunk body, even when nothing detonated. Since process_detonations
    calls remove_bombs on every tick regardless of whether anything actually
    needs removing, this ran 60 times a second per active bomb — found via
    py-spy as a hotspot that scaled with tick rate, not detonation rate. An
    empty index list must leave existing bomb bodies untouched."""
    state = _make_empty_state()
    space = _make_space(state)
    _add_bomb(state, space, col=1, row=1)
    body, shape = space._bomb_bodies[0]

    remove_bombs(state, space, [])

    assert space._bomb_bodies[0] == (body, shape)


def test_remove_bombs_rekeys_survivors_without_recreating_bodies() -> None:
    """Regression: removing one bomb used to tear down and recreate every
    surviving bomb's pymunk body to keep indices aligned with state.bombs,
    resetting their velocity to zero. A bomb mid-flight from a push would
    snap to a dead stop whenever any *other* bomb detonated. Survivors must
    keep their existing body/shape (and velocity) and just be re-keyed."""
    state = _make_empty_state()
    space = _make_space(state)
    for col, row in [(1, 1), (2, 2), (3, 3)]:
        _add_bomb(state, space, col, row)
    survivor_body, survivor_shape = space._bomb_bodies[2]
    survivor_body.velocity = (40.0, 0.0)

    remove_bombs(state, space, [1])  # detonate the middle bomb

    assert len(state.bombs) == 2
    assert set(space.bomb_indices()) == {0, 1}
    assert space._bomb_bodies[1] == (survivor_body, survivor_shape)
    assert space._bomb_bodies[1][0].velocity.x == 40.0
