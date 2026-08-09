"""Tests for the PhysicsSpace wall/tile helpers in engine/physics.py."""

from core.components import Cell, TileKind
from engine.physics import PhysicsSpace


def _empty_space(cols: int = 3, rows: int = 3) -> PhysicsSpace:
    space = PhysicsSpace()
    tiles = [[TileKind.EMPTY] * cols for _ in range(rows)]
    space.rebuild_static_walls(tiles)
    return space


def test_add_wall_defaults_to_soft_block_for_existing_callers():
    """Verify add_wall defaults to a destructible SOFT_BLOCK when no kind is given."""
    space = _empty_space()
    space.add_wall(0, 0)
    assert space._tiles[0][0] == TileKind.SOFT_BLOCK


def test_add_wall_accepts_explicit_kind_for_indestructible_shrink_walls():
    """Verify add_wall honours an explicit SOLID_WALL kind for shrink walls."""
    space = _empty_space()
    space.add_wall(1, 1, TileKind.SOLID_WALL)
    assert space._tiles[1][1] == TileKind.SOLID_WALL


def test_add_wall_does_not_alias_soft_block_over_solid_wall():
    """Regression: add_wall used to hardcode its internal tile write to
    SOFT_BLOCK, which — because rebuild_static_walls aliases the tiles list
    rather than copying it — silently downgraded any SOLID_WALL written by a
    caller to a destructible SOFT_BLOCK immediately afterwards."""
    space = _empty_space()
    tiles = space._tiles
    tiles[2][2] = TileKind.SOLID_WALL
    space.add_wall(2, 2, TileKind.SOLID_WALL)
    assert tiles[2][2] == TileKind.SOLID_WALL


def test_rebuild_static_walls_is_noop_when_tiles_unchanged():
    """Regression: rebuild_static_walls used to tear down and recreate every
    wall shape on every call, even when the tile grid was identical to what
    was already loaded. py-spy profiling under live load showed this as a
    ~25% CPU hotspot, because the server rollback path (net/server.py's
    _replay_from) called it on every late/reordered input packet. Calling it
    again with an equal (but distinct) tiles grid must leave the existing
    shape objects untouched."""
    tiles = [[TileKind.EMPTY, TileKind.SOLID_WALL], [TileKind.EMPTY, TileKind.EMPTY]]
    space = PhysicsSpace()
    space.rebuild_static_walls(tiles)
    wall_shape = space._static_shapes[Cell(1, 0)]

    space.rebuild_static_walls([row[:] for row in tiles])

    assert space._static_shapes[Cell(1, 0)] is wall_shape
    assert len(space._space.shapes) == 1


def test_rebuild_static_walls_still_rebuilds_when_tiles_actually_change():
    """The unchanged-tiles fast path must not mask a real wall change, e.g.
    a bomb destroying a soft block mid-rollback-window."""
    space = _empty_space()
    space.rebuild_static_walls([[TileKind.SOLID_WALL, TileKind.EMPTY],
                                [TileKind.EMPTY, TileKind.EMPTY]])
    assert Cell(0, 0) in space._static_shapes

    space.rebuild_static_walls([[TileKind.EMPTY, TileKind.EMPTY],
                                [TileKind.EMPTY, TileKind.EMPTY]])

    assert Cell(0, 0) not in space._static_shapes
    assert len(space._space.shapes) == 0
