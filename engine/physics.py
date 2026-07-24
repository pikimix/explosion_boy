"""
pymunk Space wrapper.

Used by:
  - Server: full space (all players, all bombs, all tile walls).
  - Client prediction (systems/prediction.py): lightweight space
    (local player + static walls + bomb shapes rebuilt from server snapshot).
"""
from __future__ import annotations

import pymunk

from engine.config import (
    BOMB_FRICTION,
    BOMB_HALF_SIZE,
    PLAYER_DAMPING,
    PLAYER_RADIUS,
    TILE_SIZE,
)

_PASSABLE_TILE = 0   # TileKind.EMPTY — avoid importing core here


class PhysicsSpace:
    """Wrapper around a pymunk ``Space`` managing players, bombs, and tile walls.

    Used identically by the server (full space: all players, all bombs, all
    tile walls) and by client-side prediction (a lightweight local space
    rebuilt from server snapshots).
    """

    def __init__(self) -> None:
        self._space = pymunk.Space()
        self._space.gravity = (0, 0)
        self._space.damping = PLAYER_DAMPING
        self._player_bodies: dict[int, tuple[pymunk.Body, pymunk.Shape]] = {}
        self._bomb_bodies: dict[int, tuple[pymunk.Body, pymunk.Shape]] = {}
        self._static_shapes: dict[tuple[int, int], pymunk.Shape] = {}
        self._tiles: list[list[int]] = []

        # Collision handler: player (type 1) pushes bomb (type 2)
        handler = self._space.add_collision_handler(1, 2)
        handler.post_solve = self._on_player_bomb_collision

    # ── Tile walls ────────────────────────────────────────────────────────────

    def rebuild_static_walls(self, tiles: list[list]) -> None:
        """Rebuild all static wall shapes from a tile grid, replacing any existing ones.

        Parameters
        ----------
        tiles : list of list
            Row-major grid of tile kind values; any value other than the
            passable tile kind gets a static wall shape.
        """
        for shape in self._static_shapes.values():
            self._space.remove(shape)
        self._static_shapes.clear()
        self._tiles = tiles

        rows = len(tiles)
        cols = len(tiles[0]) if rows else 0
        for row in range(rows):
            for col in range(cols):
                if tiles[row][col] != _PASSABLE_TILE:
                    self._static_shapes[(col, row)] = self._make_wall_shape(col, row)

    def _make_wall_shape(self, col: int, row: int) -> pymunk.Shape:
        x = col * TILE_SIZE
        y = row * TILE_SIZE
        verts = [(x, y), (x + TILE_SIZE, y),
                 (x + TILE_SIZE, y + TILE_SIZE), (x, y + TILE_SIZE)]
        shape = pymunk.Poly(self._space.static_body, verts)
        shape.elasticity = 0.0
        shape.friction = 0.0
        self._space.add(shape)
        return shape

    def remove_wall(self, col: int, row: int) -> None:
        """Remove the wall shape at a tile position, if one exists, and mark it passable.

        Parameters
        ----------
        col : int
            Tile column index.
        row : int
            Tile row index.
        """
        shape = self._static_shapes.pop((col, row), None)
        if shape is not None:
            self._space.remove(shape)
        if self._tiles:
            self._tiles[row][col] = _PASSABLE_TILE

    def add_wall(self, col: int, row: int, kind: int = 2) -> None:
        """Add a wall shape at a tile position and record its tile kind.

        Parameters
        ----------
        col : int
            Tile column index.
        row : int
            Tile row index.
        kind : int, optional
            Tile kind to store for this position (default 2,
            ``TileKind.SOFT_BLOCK``, to preserve existing callers such as
            rubble-bomb scatter). Pass ``TileKind.SOLID_WALL`` explicitly for
            indestructible walls such as the perimeter shrink.
        """
        if (col, row) not in self._static_shapes:
            self._static_shapes[(col, row)] = self._make_wall_shape(col, row)
        if self._tiles:
            self._tiles[row][col] = kind

    # ── Players ───────────────────────────────────────────────────────────────

    def add_player(self, player_id: int, px: float, py: float) -> None:
        """Add a player body to the space at the given position.

        Parameters
        ----------
        player_id : int
            Identifier of the player.
        px : float
            Initial x position, in pixels.
        py : float
            Initial y position, in pixels.
        """
        body = pymunk.Body(mass=1, moment=float('inf'))  # no rotation
        body.position = (px, py)
        shape = pymunk.Circle(body, PLAYER_RADIUS)
        shape.elasticity = 0.0
        shape.friction = 0.8
        shape.collision_type = 1
        self._space.add(body, shape)
        self._player_bodies[player_id] = (body, shape)

    def remove_player(self, player_id: int) -> None:
        """Remove a player's body and shape from the space, if present.

        Parameters
        ----------
        player_id : int
            Identifier of the player to remove.
        """
        entry = self._player_bodies.pop(player_id, None)
        if entry:
            body, shape = entry
            self._space.remove(body, shape)

    def set_player_velocity(self, player_id: int, vx: float, vy: float) -> None:
        """Set a player body's velocity directly.

        Parameters
        ----------
        player_id : int
            Identifier of the player.
        vx : float
            Velocity along x, in pixels per second.
        vy : float
            Velocity along y, in pixels per second.
        """
        if entry := self._player_bodies.get(player_id):
            entry[0].velocity = (vx, vy)

    def get_player_position(self, player_id: int) -> tuple[float, float] | None:
        """Get a player's current position.

        Parameters
        ----------
        player_id : int
            Identifier of the player.

        Returns
        -------
        tuple of float, or None
            The ``(x, y)`` position in pixels, or None if the player has no
            body in the space.
        """
        if entry := self._player_bodies.get(player_id):
            pos = entry[0].position
            return pos.x, pos.y
        return None

    def get_player_velocity(self, player_id: int) -> tuple[float, float]:
        """Get a player's current velocity.

        Parameters
        ----------
        player_id : int
            Identifier of the player.

        Returns
        -------
        tuple of float
            The ``(vx, vy)`` velocity in pixels per second, or ``(0.0, 0.0)``
            if the player has no body in the space.
        """
        if entry := self._player_bodies.get(player_id):
            v = entry[0].velocity
            return v.x, v.y
        return (0.0, 0.0)

    def has_player(self, player_id: int) -> bool:
        """Check whether a player currently has a body in the space.

        Parameters
        ----------
        player_id : int
            Identifier of the player.

        Returns
        -------
        bool
            True if the player has a body in the space.
        """
        return player_id in self._player_bodies

    # ── Bombs ─────────────────────────────────────────────────────────────────

    def add_bomb(self, bomb_idx: int, px: float, py: float) -> None:
        """Add a bomb body to the space at the given position.

        Parameters
        ----------
        bomb_idx : int
            Index of the bomb in the game state's bomb list.
        px : float
            Initial x position, in pixels.
        py : float
            Initial y position, in pixels.
        """
        size = BOMB_HALF_SIZE * 2
        body = pymunk.Body(
            mass=0.5,
            moment=pymunk.moment_for_box(0.5, (size, size)),
        )
        body.position = (px, py)
        shape = pymunk.Poly.create_box(body, (size, size))
        shape.elasticity = 0.2
        shape.friction = BOMB_FRICTION
        shape.collision_type = 2
        self._space.add(body, shape)
        self._bomb_bodies[bomb_idx] = (body, shape)

    def remove_bomb(self, bomb_idx: int) -> None:
        """Remove a bomb's body and shape from the space, if present.

        Parameters
        ----------
        bomb_idx : int
            Index of the bomb to remove.
        """
        entry = self._bomb_bodies.pop(bomb_idx, None)
        if entry:
            body, shape = entry
            self._space.remove(body, shape)

    def get_bomb_position(self, bomb_idx: int) -> tuple[float, float] | None:
        """Get a bomb's current position.

        Parameters
        ----------
        bomb_idx : int
            Index of the bomb.

        Returns
        -------
        tuple of float, or None
            The ``(x, y)`` position in pixels, or None if the bomb has no
            body in the space.
        """
        if entry := self._bomb_bodies.get(bomb_idx):
            pos = entry[0].position
            return pos.x, pos.y
        return None

    def bomb_indices(self) -> list[int]:
        """List the indices of all bombs currently in the space.

        Returns
        -------
        list of int
            Indices of bombs with bodies in the space.
        """
        return list(self._bomb_bodies.keys())

    # ── Step ──────────────────────────────────────────────────────────────────

    def step(self, dt: float) -> None:
        """Advance the physics simulation by one time step.

        Parameters
        ----------
        dt : float
            Time step duration, in seconds.
        """
        self._space.step(dt)
        if self._tiles:
            self._correct_player_positions()

    def _correct_player_positions(self) -> None:
        """Push players out of any solid tile they overlap and cancel velocity into walls."""
        tiles = self._tiles
        rows = len(tiles)
        cols = len(tiles[0]) if rows else 0
        r = PLAYER_RADIUS

        for body, _ in self._player_bodies.values():
            x, y = body.position.x, body.position.y
            vx, vy = body.velocity.x, body.velocity.y

            col0 = max(0, int((x - r) // TILE_SIZE))
            col1 = min(cols - 1, int((x + r) // TILE_SIZE))
            row0 = max(0, int((y - r) // TILE_SIZE))
            row1 = min(rows - 1, int((y + r) // TILE_SIZE))

            for tr in range(row0, row1 + 1):
                for tc in range(col0, col1 + 1):
                    if tiles[tr][tc] == _PASSABLE_TILE:
                        continue
                    tx = tc * TILE_SIZE
                    ty = tr * TILE_SIZE
                    # Nearest point on tile AABB to circle centre
                    cx = max(tx, min(x, tx + TILE_SIZE))
                    cy = max(ty, min(y, ty + TILE_SIZE))
                    dx, dy = x - cx, y - cy
                    dist_sq = dx * dx + dy * dy
                    if dist_sq >= r * r:
                        continue
                    dist = dist_sq ** 0.5
                    if dist < 1e-6:
                        nx, ny = 1.0, 0.0
                    else:
                        nx, ny = dx / dist, dy / dist
                    # Push out with a small gap
                    overlap = r - dist
                    x += nx * (overlap + 0.5)
                    y += ny * (overlap + 0.5)
                    # Cancel velocity component into this wall
                    dot = vx * nx + vy * ny
                    if dot < 0:
                        vx -= nx * dot
                        vy -= ny * dot

            body.position = (x, y)
            body.velocity = (vx, vy)

    # ── Collision callbacks ───────────────────────────────────────────────────

    def _on_player_bomb_collision(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: object
    ) -> None:
        """Transfer an impulse from the player body to the bomb body."""
        if len(arbiter.shapes) < 2:
            return
        player_shape, bomb_shape = arbiter.shapes[0], arbiter.shapes[1]
        if player_shape.collision_type != 1:
            player_shape, bomb_shape = bomb_shape, player_shape

        pv = player_shape.body.velocity
        n = arbiter.normal
        # Project player velocity onto contact normal and apply as impulse to bomb
        dot = pv.x * n.x + pv.y * n.y
        if dot > 0:
            bomb_shape.body.apply_impulse_at_local_point(
                (n.x * dot * bomb_shape.body.mass,
                 n.y * dot * bomb_shape.body.mass)
            )
