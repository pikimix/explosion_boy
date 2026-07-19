"""Tests for the PhysicsSpace wall/tile helpers in engine/physics.py."""

from core.components import TileKind
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
