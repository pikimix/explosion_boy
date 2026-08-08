"""Tests for detonation dispatch and cluster/super/rubble powerup combinations."""

from core.components import BombComponent, Cell, PhysicsState, PlayerStats, SmokeCloud, TileKind
from core.state import GameState
from engine.config import TICK_RATE, TILE_SIZE
from engine.physics import PhysicsSpace
from systems.bomb_system import DetonationEvent
from systems.event_bus import EventBus
from systems.explosion_system import process_detonations, tick_explosions, tick_smoke_clouds


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


def test_overlapping_super_bombs_dedupe_explosion_centers() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    # blast_radius=4 -> half=2, so each bomb covers a 5x5 box.
    # bomb0 at col 5 covers cols 3..7; bomb1 at col 7 covers cols 5..9 -> overlap cols 5..7.
    bombs = [
        BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
                      col=5, row=7, px=0, py=0, is_super=True),
        BombComponent(owner_id=1, fuse_ticks_remaining=1, blast_radius=4,
                      col=7, row=7, px=0, py=0, is_super=True),
    ]
    for i, b in enumerate(bombs):
        state.bombs.append(b)
        space.add_bomb(i, b.px, b.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=5, row=7, blast_radius=4, owner_id=0, is_super=True),
        DetonationEvent(bomb_idx=1, col=7, row=7, blast_radius=4, owner_id=1, is_super=True),
    ]
    process_detonations(state, space, dets, EventBus())

    cells = [(e.col, e.row) for e in state.explosions]
    # No cell should have more than one ExplosionCenter, even though both
    # bombs' 5x5 AOE boxes overlap over a 3x5 region.
    assert len(cells) == len(set(cells))
    # 25 + 25 - 15 (overlap) = 35 distinct cells; without dedup this would be 50.
    assert len(cells) == 35


def test_overlapping_super_bombs_still_destroy_softblocks_in_overlap() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    # Soft block placed inside the overlap region shared by both bombs.
    state.tiles[7][6] = TileKind.SOFT_BLOCK
    space.rebuild_static_walls(state.tiles)

    bombs = [
        BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
                      col=5, row=7, px=0, py=0, is_super=True),
        BombComponent(owner_id=1, fuse_ticks_remaining=1, blast_radius=4,
                      col=7, row=7, px=0, py=0, is_super=True),
    ]
    for i, b in enumerate(bombs):
        state.bombs.append(b)
        space.add_bomb(i, b.px, b.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=5, row=7, blast_radius=4, owner_id=0, is_super=True),
        DetonationEvent(bomb_idx=1, col=7, row=7, blast_radius=4, owner_id=1, is_super=True),
    ]
    process_detonations(state, space, dets, EventBus())

    assert state.tiles[7][6] == TileKind.EMPTY
    assert (6, 7) in {(e.col, e.row) for e in state.explosions}


def test_non_overlapping_bombs_each_keep_their_own_explosion_centers() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
        col=2, row=2, px=0, py=0,
    )
    other = BombComponent(
        owner_id=1, fuse_ticks_remaining=1, blast_radius=2,
        col=12, row=12, px=0, py=0,
    )
    state.bombs.extend([bomb, other])
    space.add_bomb(0, bomb.px, bomb.py)
    space.add_bomb(1, other.px, other.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=2, row=2, blast_radius=2, owner_id=0),
        DetonationEvent(bomb_idx=1, col=12, row=12, blast_radius=2, owner_id=1),
    ]
    process_detonations(state, space, dets, EventBus())

    cells = {(e.col, e.row) for e in state.explosions}
    assert (2, 2) in cells
    assert (12, 12) in cells
    assert len(cells) == 2


def _add_player(state: GameState, pid: int, col: int, row: int) -> None:
    state.players[pid] = PlayerStats(player_id=pid)
    state.player_physics[pid] = PhysicsState(
        x=col * TILE_SIZE + TILE_SIZE / 2,
        y=row * TILE_SIZE + TILE_SIZE / 2,
    )


def test_lit_cells_cache_reused_across_unchanged_ticks() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=3,
                         col=5, row=5, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=3, owner_id=0)
    process_detonations(state, space, [det], EventBus())

    assert state.lit_cells_dirty is False
    cache_after_detonation = state.lit_cells_cache
    assert cache_after_detonation is not None

    # A tick where nothing expires and nothing new detonates: dirty stays
    # False and the same cached set object is reused, not rebuilt.
    tick_explosions(state)
    assert state.lit_cells_dirty is False
    process_detonations(state, space, [], EventBus())
    assert state.lit_cells_cache is cache_after_detonation


def test_lit_cells_cache_invalidated_on_new_detonation() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
                         col=2, row=2, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)
    process_detonations(
        state, space,
        [DetonationEvent(bomb_idx=0, col=2, row=2, blast_radius=2, owner_id=0)],
        EventBus(),
    )
    first_cache = state.lit_cells_cache
    assert Cell(2, 2) in first_cache

    other = BombComponent(owner_id=1, fuse_ticks_remaining=1, blast_radius=2,
                          col=12, row=12, px=0, py=0)
    state.bombs.append(other)
    space.add_bomb(1, other.px, other.py)
    process_detonations(
        state, space,
        [DetonationEvent(bomb_idx=1, col=12, row=12, blast_radius=2, owner_id=1)],
        EventBus(),
    )

    assert state.lit_cells_dirty is False
    assert state.lit_cells_cache is not first_cache
    assert Cell(2, 2) in state.lit_cells_cache
    assert Cell(12, 12) in state.lit_cells_cache


def test_lit_cells_cache_invalidated_when_explosion_expires() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
                         col=5, row=5, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)
    process_detonations(
        state, space,
        [DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=2, owner_id=0)],
        EventBus(),
    )
    assert state.lit_cells_dirty is False

    # Age every active explosion/ray past its ticks_remaining so it's removed.
    for e in state.explosions:
        e.ticks_remaining = 1
    for r in state.explosion_rays:
        r.ticks_remaining = 1
    tick_explosions(state)

    assert state.explosions == []
    assert state.explosion_rays == []
    assert state.lit_cells_dirty is True


def test_cached_lit_cells_still_detect_player_who_moves_into_blast() -> None:
    """The cache stores which cells are lit, not which players are dead —

    a player who steps into an already-active blast on a later, otherwise
    unchanged tick must still be killed."""
    state = _make_empty_state()
    space = _make_space(state)
    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=3,
                         col=5, row=5, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=3, owner_id=0)
    process_detonations(state, space, [det], EventBus())
    assert state.lit_cells_dirty is False

    # Player steps into the still-active blast cell on a later tick where
    # nothing about the explosion batch itself changes (cache is reused).
    _add_player(state, pid=1, col=5, row=5)
    tick_explosions(state)
    assert state.lit_cells_dirty is False
    process_detonations(state, space, [], EventBus())

    assert 1 not in state.players
    assert 1 not in state.player_physics


def test_crossing_normal_bomb_rays_are_not_deduped() -> None:
    """Two normal bombs whose rays cross the same cell each keep their own ray

    (they're distinct blast lines from distinct origins, not duplicate data)."""
    state = _make_empty_state()
    space = _make_space(state)
    bombs = [
        BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=3,
                      col=5, row=5, px=0, py=0),
        BombComponent(owner_id=1, fuse_ticks_remaining=1, blast_radius=3,
                      col=7, row=2, px=0, py=0),
    ]
    for i, b in enumerate(bombs):
        state.bombs.append(b)
        space.add_bomb(i, b.px, b.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=3, owner_id=0),
        DetonationEvent(bomb_idx=1, col=7, row=2, blast_radius=3, owner_id=1),
    ]
    process_detonations(state, space, dets, EventBus())

    # bomb0's rightward ray and bomb1's downward ray both cross (7, 5).
    lit: set[tuple[int, int]] = set()
    for ray in state.explosion_rays:
        dc, dr = ray.direction
        for i in range(1, ray.length + 1):
            lit.add((ray.origin_col + dc * i, ray.origin_row + dr * i))
    assert (7, 5) in lit

    origins = {(r.origin_col, r.origin_row) for r in state.explosion_rays}
    assert (5, 5) in origins and (7, 2) in origins
    # Both bombs' own origins get an ExplosionCenter, and they're distinct.
    assert {(e.col, e.row) for e in state.explosions} == {(5, 5), (7, 2)}


def test_chain_triggered_normal_bomb_inside_super_aoe_dedupes_origin() -> None:
    """A normal bomb chain-triggered from inside a super bomb's already-lit AOE

    doesn't get a second ExplosionCenter at the same cell."""
    state = _make_empty_state()
    space = _make_space(state)
    # Super bomb at (5,5), blast_radius=4 -> half=2, covers cols 3..7, rows 3..7.
    super_bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
        col=5, row=5, px=0, py=0, is_super=True,
    )
    # Normal bomb sitting inside that AOE, chain-triggered rather than detonated directly.
    inner_bomb = BombComponent(
        owner_id=1, fuse_ticks_remaining=1, blast_radius=2,
        col=6, row=5, px=0, py=0,
    )
    state.bombs.extend([super_bomb, inner_bomb])
    space.add_bomb(0, super_bomb.px, super_bomb.py)
    space.add_bomb(1, inner_bomb.px, inner_bomb.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=4, owner_id=0, is_super=True),
    ]
    process_detonations(state, space, dets, EventBus())

    cells = [(e.col, e.row) for e in state.explosions]
    assert cells.count((6, 5)) == 1
    assert len(cells) == len(set(cells))


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


def test_smoke_bomb_detonation_spawns_cloud_and_deals_no_damage() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    state.tiles[7][6] = TileKind.SOFT_BLOCK
    space.rebuild_static_walls(state.tiles)
    _add_player(state, pid=1, col=7, row=7)

    bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=3,
        col=7, row=7, px=0, py=0, is_smoke=True, blast_penetration=2,
    )
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    det = DetonationEvent(
        bomb_idx=0, col=7, row=7, blast_radius=3, owner_id=0,
        is_smoke=True, blast_penetration=2,
    )
    process_detonations(state, space, [det], EventBus())

    assert len(state.smoke_clouds) == 1
    cloud = state.smoke_clouds[0]
    assert (cloud.col, cloud.row) == (7, 7)
    assert cloud.radius == 3
    assert cloud.ticks_total == round(2 * 2 * 2 * TICK_RATE)
    assert cloud.ticks_remaining == cloud.ticks_total

    # No damage: soft block survives, no explosions/rays recorded.
    assert state.tiles[7][6] == TileKind.SOFT_BLOCK
    assert state.explosions == []
    assert state.explosion_rays == []
    # No kill: player standing on the smoke bomb's own cell survives.
    assert 1 in state.players
    assert 1 in state.player_physics


def test_tick_explosions_does_not_affect_smoke_clouds() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    state.smoke_clouds.append(SmokeCloud(col=3, row=3, radius=2, ticks_remaining=5, ticks_total=5))
    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=2,
                         col=10, row=10, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)
    process_detonations(
        state, space,
        [DetonationEvent(bomb_idx=0, col=10, row=10, blast_radius=2, owner_id=0)],
        EventBus(),
    )
    assert state.explosions  # sanity: the unrelated explosion did age-able state

    for _ in range(3):
        tick_explosions(state)

    assert state.smoke_clouds[0].ticks_remaining == 5


def test_tick_smoke_clouds_ages_and_removes_independently() -> None:
    state = _make_empty_state()
    state.smoke_clouds.append(SmokeCloud(col=3, row=3, radius=2, ticks_remaining=3, ticks_total=3))

    tick_smoke_clouds(state)
    assert len(state.smoke_clouds) == 1
    assert state.smoke_clouds[0].ticks_remaining == 2

    tick_smoke_clouds(state)
    assert len(state.smoke_clouds) == 1
    assert state.smoke_clouds[0].ticks_remaining == 1

    tick_smoke_clouds(state)
    assert state.smoke_clouds == []


def test_nearby_explosion_does_not_shorten_smoke_cloud() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    state.smoke_clouds.append(SmokeCloud(col=5, row=5, radius=2, ticks_remaining=100, ticks_total=100))

    bomb = BombComponent(owner_id=0, fuse_ticks_remaining=1, blast_radius=3,
                         col=5, row=5, px=0, py=0)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)
    process_detonations(
        state, space,
        [DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=3, owner_id=0)],
        EventBus(),
    )

    assert len(state.smoke_clouds) == 1
    assert state.smoke_clouds[0].ticks_remaining == 100
    assert state.smoke_clouds[0].ticks_total == 100


def test_chain_reacted_smoke_bomb_keeps_its_captured_blast_penetration() -> None:
    state = _make_empty_state()
    space = _make_space(state)
    # Rubble bomb at (5,5), blast_radius=4 -> half=2, covers cols 3..7, rows 3..7.
    rubble_bomb = BombComponent(
        owner_id=0, fuse_ticks_remaining=1, blast_radius=4,
        col=5, row=5, px=0, py=0, is_rubble=True,
    )
    # Smoke bomb parked inside that AOE, with a non-default blast_penetration.
    smoke_bomb = BombComponent(
        owner_id=1, fuse_ticks_remaining=1, blast_radius=2,
        col=6, row=5, px=0, py=0, is_smoke=True, blast_penetration=5,
    )
    state.bombs.extend([rubble_bomb, smoke_bomb])
    space.add_bomb(0, rubble_bomb.px, rubble_bomb.py)
    space.add_bomb(1, smoke_bomb.px, smoke_bomb.py)

    dets = [
        DetonationEvent(bomb_idx=0, col=5, row=5, blast_radius=4, owner_id=0, is_rubble=True),
    ]
    process_detonations(state, space, dets, EventBus())

    assert len(state.smoke_clouds) == 1
    cloud = state.smoke_clouds[0]
    assert (cloud.col, cloud.row) == (6, 5)
    assert cloud.ticks_total == round(5 * 2 * 2 * TICK_RATE)
