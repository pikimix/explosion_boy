"""Tests for the world/map-generation helpers in systems/world.py."""

from core.components import TileKind
from engine.config import MAX_GRID_SIZE, MAX_PLAYERS, MIN_GRID_SIZE
from systems.world import generate_map, map_size_for_player_count, ring_cells, spawn_points_for_grid


def test_map_size_is_square_odd_and_bounded():
    """Map sizes for every valid player count are square, odd, and within grid bounds."""
    for n in range(2, MAX_PLAYERS + 1):
        cols, rows = map_size_for_player_count(n)
        assert cols == rows
        assert cols % 2 == 1
        assert MIN_GRID_SIZE <= cols <= MAX_GRID_SIZE


def test_map_size_is_non_decreasing_with_player_count():
    """Map size never shrinks as the player count increases."""
    sizes = [map_size_for_player_count(n)[0] for n in range(2, MAX_PLAYERS + 1)]
    assert sizes == sorted(sizes)


def test_map_size_endpoints():
    """Map size matches the min grid at the lowest and max grid at the highest player count."""
    assert map_size_for_player_count(2) == (MIN_GRID_SIZE, MIN_GRID_SIZE)
    assert map_size_for_player_count(MAX_PLAYERS) == (MAX_GRID_SIZE, MAX_GRID_SIZE)


def test_map_size_clamps_out_of_range_player_counts():
    """Out-of-range player counts are clamped to the nearest valid endpoint."""
    assert map_size_for_player_count(0) == map_size_for_player_count(2)
    assert map_size_for_player_count(999) == map_size_for_player_count(MAX_PLAYERS)


def test_spawn_points_stay_in_bounds_and_off_pillars():
    """Generated spawn points stay within the playable grid and never land on a pillar cell."""
    for n in (2, 8, 16):
        cols, rows = map_size_for_player_count(n)
        points = spawn_points_for_grid(cols, rows)
        assert len(points) == 16
        for col, row in points[:n]:
            assert 1 <= col <= cols - 2
            assert 1 <= row <= rows - 2
            assert not (col % 2 == 0 and row % 2 == 0)


def test_spawn_points_are_unique_for_active_players():
    """Spawn points assigned to active players contain no duplicates."""
    for n in (2, 8, 16):
        cols, rows = map_size_for_player_count(n)
        points = spawn_points_for_grid(cols, rows)[:n]
        assert len(set(points)) == len(points)


def test_generate_map_matches_requested_dimensions():
    """Generated map tiles have the requested number of rows and columns."""
    for n in (2, 16):
        cols, rows = map_size_for_player_count(n)
        spawn_points = spawn_points_for_grid(cols, rows)
        tiles = generate_map(
            cols=cols, rows=rows, num_players=n, seed=42, spawn_points=spawn_points
        )
        assert len(tiles) == rows
        assert len(tiles[0]) == cols


def test_generate_map_border_is_solid():
    """The outer border of a generated map is entirely solid wall tiles."""
    cols, rows = 15, 13
    spawn_points = spawn_points_for_grid(cols, rows)
    tiles = generate_map(cols=cols, rows=rows, num_players=4, seed=1, spawn_points=spawn_points)
    assert all(tiles[0][c] == TileKind.SOLID_WALL for c in range(cols))
    assert all(tiles[rows - 1][c] == TileKind.SOLID_WALL for c in range(cols))
    assert all(tiles[r][0] == TileKind.SOLID_WALL for r in range(rows))
    assert all(tiles[r][cols - 1] == TileKind.SOLID_WALL for r in range(rows))


def test_generate_map_places_pillars_unconditionally_even_near_spawns():
    """Pillar cells are always solid walls, even when they fall inside a spawn's safety zone."""
    # Pillars are a fixed structural feature of the map and are always placed,
    # regardless of spawn safety zones — only soft (breakable) blocks are kept
    # out of a spawn's safety zone.
    cols, rows = 15, 13
    spawn_points = spawn_points_for_grid(cols, rows)
    tiles = generate_map(cols=cols, rows=rows, num_players=2, seed=3, spawn_points=spawn_points)
    pillars = {
        (c, r)
        for r in range(1, rows - 1)
        for c in range(1, cols - 1)
        if r % 2 == 0 and c % 2 == 0
    }
    assert pillars
    assert all(tiles[r][c] == TileKind.SOLID_WALL for c, r in pillars)


def test_soft_blocks_respect_safety_zone_for_the_exact_active_spawns():
    """Regression: the safety zone must be carved around the spawn cells
    actually used by real players (active_spawns), not just spawn_points[:n].
    Player ids aren't guaranteed contiguous 0..n-1 (a player can leave a lobby
    mid-session, freeing a lower id without every higher id shifting down), so
    a player occupying a higher-index spawn point than spawn_points[:n] could
    otherwise get no safety zone and spawn right next to breakable blocks."""
    cols, rows = map_size_for_player_count(3)
    spawn_points = spawn_points_for_grid(cols, rows)
    # Simulate ids {0, 2, 3} for 3 players (id 1 left the lobby and was not
    # backfilled) — spawn_points[:3] would only cover indices 0, 1, 2, missing
    # the real spawn at index 3.
    active_spawns = [spawn_points[0], spawn_points[2], spawn_points[3]]
    tiles = generate_map(
        cols=cols, rows=rows, num_players=3, seed=11,
        spawn_points=spawn_points, active_spawns=active_spawns,
    )
    for col, row in active_spawns:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                c, r = col + dc, row + dr
                if not (0 <= r < rows and 0 <= c < cols):
                    continue
                assert tiles[r][c] != TileKind.SOFT_BLOCK, (
                    f"spawn=({col},{row}) cell=({c},{r}) has a breakable block in its safety zone"
                )


def test_ring_cells_ring_one_on_7x7():
    """The first ring on a 7x7 grid matches the expected border-adjacent cells."""
    cols, rows = 7, 7
    ring1 = set(ring_cells(cols, rows, 1))
    expected = (
        {(c, 1) for c in range(1, 6)}
        | {(c, 5) for c in range(1, 6)}
        | {(1, r) for r in range(2, 5)}
        | {(5, r) for r in range(2, 5)}
    )
    assert ring1 == expected


def test_ring_cells_ring_two_on_7x7():
    """The second ring on a 7x7 grid matches the expected set of cells."""
    ring2 = set(ring_cells(7, 7, 2))
    expected = {(2, 2), (3, 2), (4, 2), (2, 4), (3, 4), (4, 4), (2, 3), (4, 3)}
    assert ring2 == expected


def test_ring_cells_beyond_grid_is_empty():
    """Ring cells beyond the grid bounds return an empty sequence."""
    assert not list(ring_cells(7, 7, 4))
