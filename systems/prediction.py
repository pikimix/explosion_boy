"""
Client-side prediction.

Maintains a local pymunk space populated from the last confirmed server
GameState. On each local frame the player's own input is applied immediately,
giving responsive movement before the server echoes the result.

On server state receipt:
  1. Rebuild the prediction space from the new snapshot.
  2. Replay all pending (unconfirmed) inputs on top.
  3. The resulting predicted position is used for rendering.
"""
from __future__ import annotations

import copy
from collections import deque

from core.components import PlayerInput, PhysicsState
from core.state import GameState
from core.tick import TICK_DT
from engine.config import MAX_PLAYER_SPEED, TILE_SIZE
from engine.physics import PhysicsSpace


class PredictionEngine:
    def __init__(self, local_player_id: int) -> None:
        self._pid = local_player_id
        self._space: PhysicsSpace = PhysicsSpace()
        self._pending: deque[PlayerInput] = deque()
        self._predicted_x: float = 0.0
        self._predicted_y: float = 0.0
        self._confirmed_state: GameState | None = None

    # ── Called by game_scene when a new input is generated ────────────────────

    def apply_input(self, inp: PlayerInput) -> None:
        """Immediately apply input to local prediction space."""
        self._pending.append(inp)
        self._step_input(inp)

    # ── Called when a StateUpdateMsg arrives from the server ──────────────────

    def reconcile(self, server_state: GameState) -> None:
        """Accept authoritative state and replay unconfirmed inputs."""
        self._confirmed_state = server_state
        self._rebuild_space(server_state)

        # Discard inputs that have been confirmed by the server
        while (self._pending
               and self._pending[0].tick <= server_state.tick):
            self._pending.popleft()

        # Replay remaining unconfirmed inputs
        for inp in self._pending:
            self._step_input(inp)

        pos = self._space.get_player_position(self._pid)
        if pos:
            self._predicted_x, self._predicted_y = pos

    # ── Predicted position for rendering ──────────────────────────────────────

    @property
    def predicted_x(self) -> float:
        return self._predicted_x

    @property
    def predicted_y(self) -> float:
        return self._predicted_y

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _rebuild_space(self, state: GameState) -> None:
        self._space = PhysicsSpace()
        # Static tile walls (EMPTY == 0, everything else is solid)
        self._space.rebuild_static_walls(state.tiles)
        # Bomb shapes (for push interaction)
        for i, bomb in enumerate(state.bombs):
            self._space.add_bomb(i, bomb.px, bomb.py)
        # Local player body at server-confirmed position
        phys = state.player_physics.get(self._pid)
        if phys:
            self._space.add_player(self._pid, phys.x, phys.y)
            self._predicted_x, self._predicted_y = phys.x, phys.y

    def _step_input(self, inp: PlayerInput) -> None:
        if not self._space.has_player(self._pid):
            return
        mx, my = inp.move_x, inp.move_y
        mag = (mx * mx + my * my) ** 0.5
        if mag > 1.0:
            mx, my = mx / mag, my / mag
        self._space.set_player_velocity(self._pid, mx * MAX_PLAYER_SPEED,
                                        my * MAX_PLAYER_SPEED)
        self._space.step(TICK_DT)
        pos = self._space.get_player_position(self._pid)
        if pos:
            self._predicted_x, self._predicted_y = pos
