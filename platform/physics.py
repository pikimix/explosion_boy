"""
pymunk Space wrapper.

Used by:
  - Server: full space (all players, all bombs, all tile walls).
  - Client prediction (systems/prediction.py): lightweight space
    (local player + static walls + bomb shapes rebuilt from server snapshot).
"""
from __future__ import annotations

import pymunk

from platform.config import (
    BOMB_FRICTION,
    BOMB_HALF_SIZE,
    PLAYER_DAMPING,
    PLAYER_RADIUS,
    TILE_SIZE,
)

_PASSABLE_TILE = 0   # TileKind.EMPTY — avoid importing core here


class PhysicsSpace:
    def __init__(self) -> None:
        self._space = pymunk.Space()
        self._space.gravity = (0, 0)
        self._space.damping = PLAYER_DAMPING
        self._player_bodies: dict[int, tuple[pymunk.Body, pymunk.Shape]] = {}
        self._bomb_bodies: dict[int, tuple[pymunk.Body, pymunk.Shape]] = {}
        self._static_shapes: list[pymunk.Shape] = []

        # Collision handler: player (type 1) pushes bomb (type 2)
        handler = self._space.add_collision_handler(1, 2)
        handler.post_solve = self._on_player_bomb_collision

    # ── Tile walls ────────────────────────────────────────────────────────────

    def rebuild_static_walls(self, tiles: list[list[int]]) -> None:
        """Replace all static segment shapes from the tile grid.
        Tiles with value == 0 (EMPTY) have no physics body.
        """
        for shape in self._static_shapes:
            self._space.remove(shape)
        self._static_shapes.clear()

        body = self._space.static_body
        rows = len(tiles)
        cols = len(tiles[0]) if rows else 0

        for row in range(rows):
            for col in range(cols):
                if tiles[row][col] == _PASSABLE_TILE:
                    continue
                x = col * TILE_SIZE
                y = row * TILE_SIZE
                corners = [
                    (x, y), (x + TILE_SIZE, y),
                    (x + TILE_SIZE, y + TILE_SIZE), (x, y + TILE_SIZE),
                ]
                for i in range(4):
                    seg = pymunk.Segment(
                        body, corners[i], corners[(i + 1) % 4], 0
                    )
                    seg.elasticity = 0.0
                    seg.friction = 1.0
                    self._space.add(seg)
                    self._static_shapes.append(seg)

    # ── Players ───────────────────────────────────────────────────────────────

    def add_player(self, player_id: int, px: float, py: float) -> None:
        body = pymunk.Body(
            mass=1,
            moment=pymunk.moment_for_circle(1, 0, PLAYER_RADIUS),
        )
        body.position = (px, py)
        shape = pymunk.Circle(body, PLAYER_RADIUS)
        shape.elasticity = 0.0
        shape.friction = 0.8
        shape.collision_type = 1
        self._space.add(body, shape)
        self._player_bodies[player_id] = (body, shape)

    def remove_player(self, player_id: int) -> None:
        entry = self._player_bodies.pop(player_id, None)
        if entry:
            body, shape = entry
            self._space.remove(body, shape)

    def set_player_velocity(self, player_id: int, vx: float, vy: float) -> None:
        if entry := self._player_bodies.get(player_id):
            entry[0].velocity = (vx, vy)

    def get_player_position(self, player_id: int) -> tuple[float, float] | None:
        if entry := self._player_bodies.get(player_id):
            pos = entry[0].position
            return pos.x, pos.y
        return None

    def get_player_velocity(self, player_id: int) -> tuple[float, float]:
        if entry := self._player_bodies.get(player_id):
            v = entry[0].velocity
            return v.x, v.y
        return (0.0, 0.0)

    def has_player(self, player_id: int) -> bool:
        return player_id in self._player_bodies

    # ── Bombs ─────────────────────────────────────────────────────────────────

    def add_bomb(self, bomb_idx: int, px: float, py: float) -> None:
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
        entry = self._bomb_bodies.pop(bomb_idx, None)
        if entry:
            body, shape = entry
            self._space.remove(body, shape)

    def get_bomb_position(self, bomb_idx: int) -> tuple[float, float] | None:
        if entry := self._bomb_bodies.get(bomb_idx):
            pos = entry[0].position
            return pos.x, pos.y
        return None

    def bomb_indices(self) -> list[int]:
        return list(self._bomb_bodies.keys())

    # ── Step ──────────────────────────────────────────────────────────────────

    def step(self, dt: float) -> None:
        self._space.step(dt)

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
