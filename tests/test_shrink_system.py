from core.components import BombComponent, PhysicsState, PlayerStats, TileKind
from core.state import GameState
from engine.config import (
    SHRINK_INTERVAL_TICKS,
    SHRINK_TRIGGER_TICKS,
    SHRINK_WARN_TICKS,
    TILE_SIZE,
)
from engine.physics import PhysicsSpace
from systems.event_bus import EventBus, PlayerDiedEvent
from systems.shrink_system import process_perimeter_shrink
from systems.world import generate_map, map_size_for_player_count, spawn_points_for_grid


def _grid_centre(col: int, row: int) -> tuple[float, float]:
    return col * TILE_SIZE + TILE_SIZE / 2, row * TILE_SIZE + TILE_SIZE / 2


def _make_round(num_players: int, seed: int = 1) -> tuple[GameState, PhysicsSpace, EventBus, list]:
    cols, rows = map_size_for_player_count(num_players)
    spawn_points = spawn_points_for_grid(cols, rows)
    tiles = generate_map(
        cols=cols, rows=rows, num_players=num_players, seed=seed, spawn_points=spawn_points
    )
    state = GameState(
        tick=0, map_cols=cols, map_rows=rows, tiles=tiles,
        starting_player_count=num_players,
    )
    for pid in range(num_players):
        state.players[pid] = PlayerStats(player_id=pid)
        px, py = _grid_centre(*spawn_points[pid])
        state.player_physics[pid] = PhysicsState(px, py)

    space = PhysicsSpace()
    space.rebuild_static_walls(state.tiles)
    for pid, phys in state.player_physics.items():
        space.add_player(pid, phys.x, phys.y)

    died: list[int] = []
    bus = EventBus()
    bus.subscribe(PlayerDiedEvent, lambda e: died.append(e.player_id))

    return state, space, bus, died


def test_shrink_does_not_trigger_before_timer_or_player_threshold():
    state, space, bus, _died = _make_round(3)
    state.tick = SHRINK_TRIGGER_TICKS - 1
    process_perimeter_shrink(state, space, bus)
    assert not state.shrink_active


def test_shrink_triggers_on_timer_and_begins_warning_ring_one():
    state, space, bus, _died = _make_round(3)
    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)
    assert state.shrink_active
    assert state.shrink_warn_ring == 1
    assert state.shrink_warn_ticks_remaining == SHRINK_WARN_TICKS


def test_shrink_triggers_immediately_when_dropping_to_two_players():
    state, space, bus, _died = _make_round(3)
    state.players.pop(2)
    state.tick = 100  # well before the 5-minute timer
    process_perimeter_shrink(state, space, bus)
    assert state.shrink_active
    assert state.shrink_warn_ring == 1


def test_shrink_does_not_trigger_immediately_for_a_round_that_starts_with_two_players():
    state, space, bus, _died = _make_round(2)
    state.tick = 100
    process_perimeter_shrink(state, space, bus)
    assert not state.shrink_active, "a 2-player start must not shrink until the timer elapses"

    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)
    assert state.shrink_active, "the timer must still apply to a 2-player start"


def test_tiles_stay_passable_during_the_warning_window():
    state, space, bus, _died = _make_round(3)
    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)
    ring1_cell = (1, 1)
    assert state.tiles[ring1_cell[1]][ring1_cell[0]] != TileKind.SOLID_WALL


def test_ring_closes_kills_occupant_and_removes_bomb_after_warning_expires():
    state, space, bus, died = _make_round(3)

    # Move every player away from ring 1 first — on small grids the default
    # spawn points can themselves sit on ring 1, which would kill bystanders
    # and make this test's assertions about the *deliberately placed* victim
    # and bomb ambiguous.
    centre = (state.map_cols // 2, state.map_rows // 2)
    for phys in state.player_physics.values():
        phys.x, phys.y = _grid_centre(*centre)

    victim_col, victim_row = 1, 1
    state.player_physics[0].x, state.player_physics[0].y = _grid_centre(victim_col, victim_row)

    bomb_col, bomb_row = state.map_cols - 2, 1
    bomb = BombComponent(owner_id=1, fuse_ticks_remaining=999, blast_radius=2,
                          col=bomb_col, row=bomb_row,
                          px=bomb_col * TILE_SIZE + TILE_SIZE / 2,
                          py=bomb_row * TILE_SIZE + TILE_SIZE / 2)
    state.bombs.append(bomb)
    space.add_bomb(0, bomb.px, bomb.py)

    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)  # trigger, start warning

    for _ in range(SHRINK_WARN_TICKS - 1):
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_warn_ring == 1, "should still be warning one tick before closing"
    assert 0 in state.players

    state.tick += 1
    process_perimeter_shrink(state, space, bus)

    assert state.shrink_ring == 1
    assert state.shrink_warn_ring == 0
    assert state.tiles[victim_row][victim_col] == TileKind.SOLID_WALL
    assert died == [0]
    assert 0 not in state.players
    assert len(state.bombs) == 0


def test_next_ring_warning_starts_interval_ticks_after_previous_close():
    # Use the largest round (25x25) — small grids hit the SHRINK_MIN_INTERIOR_AXIS
    # floor after only one ring, which would make this test's second-ring
    # assertion vacuous (see test_shrink_stops_permanently_once_floor_reached).
    state, space, bus, _died = _make_round(16)
    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)

    for _ in range(SHRINK_WARN_TICKS):
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_ring == 1
    close_tick_ring1 = state.tick
    next_warn_tick = state.shrink_next_warn_tick

    while state.tick < next_warn_tick:
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_warn_ring == 2
    assert state.tick == next_warn_tick
    assert next_warn_tick - close_tick_ring1 == SHRINK_INTERVAL_TICKS - SHRINK_WARN_TICKS

    # The actual spec requirement: ring closures land exactly INTERVAL apart.
    for _ in range(SHRINK_WARN_TICKS):
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_ring == 2
    assert state.tick - close_tick_ring1 == SHRINK_INTERVAL_TICKS


def test_shrink_stops_permanently_once_floor_reached():
    state, space, bus, _died = _make_round(2)  # smallest grid: 7x7
    state.tick = SHRINK_TRIGGER_TICKS
    process_perimeter_shrink(state, space, bus)
    assert state.shrink_active
    assert state.shrink_warn_ring == 1

    # 7x7 interior after closing ring 1 is 3x3 (< SHRINK_MIN_INTERIOR_AXIS=7),
    # so ring 2 must never open — shrink should stop right after ring 1 closes.
    for _ in range(SHRINK_WARN_TICKS):
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_ring == 1
    assert state.shrink_stopped

    # Further ticks must not resume shrinking.
    for _ in range(SHRINK_INTERVAL_TICKS):
        state.tick += 1
        process_perimeter_shrink(state, space, bus)
    assert state.shrink_warn_ring == 0
    assert state.shrink_ring == 1
