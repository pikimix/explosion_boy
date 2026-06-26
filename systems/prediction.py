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

from collections import deque

from core.components import PlayerInput, PhysicsState
from core.state import GameState
from core.tick import TICK_DT
from engine.config import MAX_PLAYER_SPEED, TILE_SIZE
from engine.physics import PhysicsSpace

# If the server position diverges from our prediction by more than this many
# pixels, hard-snap rather than silently drifting (wall clip, real desync).
_SNAP_THRESHOLD = TILE_SIZE * 0.6


class PredictionEngine:
    def __init__(self, local_player_id: int) -> None:
        self._pid = local_player_id
        self._space: PhysicsSpace = PhysicsSpace()
        self._pending: deque[PlayerInput] = deque()
        self._predicted_x: float = 0.0
        self._predicted_y: float = 0.0
        self._confirmed_state: GameState | None = None
        self._tiles_version: int = -1
        self._confirmed_tiles: list[list] | None = None

    # ── Called by game_scene when a new input is generated ────────────────────

    def apply_input(self, inp: PlayerInput) -> None:
        """Immediately apply input to local prediction space."""
        self._pending.append(inp)
        self._step_input(inp)

    # ── Called when a StateUpdateMsg arrives from the server ──────────────────

    def reconcile(self, server_state: GameState) -> None:
        """Accept authoritative state and replay unconfirmed inputs.

        Always rebuilds from the server snapshot and replays pending inputs,
        then compares the *replayed* position against the *prior predicted*
        position.  If they agree within _SNAP_THRESHOLD the prediction was
        accurate and we keep the predicted position (no visible correction).
        Only snap when they genuinely diverge — wall clips, real desync.

        Comparing replayed vs predicted (rather than server vs predicted) is
        important because the server is always INPUT_LEAD_TICKS behind by
        design, so server vs predicted is always large while moving and would
        incorrectly trigger a hard-snap on every reconcile.
        """
        self._confirmed_state = server_state

        # Remember where we were before reconciliation.
        prev_x, prev_y = self._predicted_x, self._predicted_y

        # Rebuild from authoritative server state and replay all unconfirmed
        # inputs.  This gives the server-authoritative predicted position.
        self._rebuild_space(server_state)
        while (self._pending
               and self._pending[0].tick <= server_state.tick):
            self._pending.popleft()
        for inp in self._pending:
            self._step_input(inp)

        pos = self._space.get_player_position(self._pid)
        if pos:
            replayed_x, replayed_y = pos
            dx = replayed_x - prev_x
            dy = replayed_y - prev_y
            if (dx * dx + dy * dy) ** 0.5 < _SNAP_THRESHOLD:
                # Replay matches prior prediction — keep the predicted position
                # for smooth rendering and re-plant the physics body there so
                # future collision detection is consistent.
                self._space.remove_player(self._pid)
                self._space.add_player(self._pid, prev_x, prev_y)
                self._predicted_x, self._predicted_y = prev_x, prev_y
            else:
                # Genuine desync — snap to the authoritative replayed position.
                self._predicted_x, self._predicted_y = replayed_x, replayed_y

    # ── Predicted position for rendering ──────────────────────────────────────

    @property
    def predicted_x(self) -> float:
        return self._predicted_x

    @property
    def predicted_y(self) -> float:
        return self._predicted_y

    @property
    def predicted_vx(self) -> float:
        vx, _ = self._space.get_player_velocity(self._pid)
        return vx

    @property
    def predicted_vy(self) -> float:
        _, vy = self._space.get_player_velocity(self._pid)
        return vy

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _rebuild_space(self, state: GameState) -> None:
        # Remove dynamic bodies — always re-added below.
        self._space.remove_player(self._pid)
        for i in list(self._space.bomb_indices()):
            self._space.remove_bomb(i)

        if state.tiles_version != self._tiles_version:
            if self._confirmed_tiles is not None:
                # Incremental update: only touch cells that changed.
                for r, row in enumerate(state.tiles):
                    for c, kind in enumerate(row):
                        if kind != self._confirmed_tiles[r][c]:
                            if int(kind) == 0:  # TileKind.EMPTY — wall removed
                                self._space.remove_wall(c, r)
                            else:  # TileKind.SOFT_BLOCK added by rubble bomb
                                self._space.add_wall(c, r)
            else:
                self._space.rebuild_static_walls(state.tiles)
            self._confirmed_tiles = state.tiles
            self._tiles_version = state.tiles_version

        # Bomb shapes (for push interaction)
        for i, bomb in enumerate(state.bombs):
            self._space.add_bomb(i, bomb.px, bomb.py)

        phys = state.player_physics.get(self._pid)
        if phys:
            self._space.add_player(self._pid, phys.x, phys.y)
            self._predicted_x, self._predicted_y = phys.x, phys.y

    def _step_input(self, inp: PlayerInput) -> None:
        if not self._space.has_player(self._pid):
            return
        stats = (self._confirmed_state.players.get(self._pid)
                 if self._confirmed_state else None)
        if stats is not None and stats.reversed_controls_ticks > 0:
            mx, my = -inp.move_x, -inp.move_y
        else:
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
