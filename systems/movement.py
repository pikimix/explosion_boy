"""Apply player input impulses via the physics space and write results to GameState."""
from __future__ import annotations

from core.components import PlayerInput, PhysicsState
from core.state import GameState
from core.tick import TICK_DT
from engine.config import MAX_PLAYER_SPEED
from engine.physics import PhysicsSpace


def process_movement(
    state: GameState,
    space: PhysicsSpace,
    inputs: list[PlayerInput],
) -> None:
    for inp in inputs:
        if inp.player_id not in state.players:
            continue
        if not space.has_player(inp.player_id):
            continue

        # Reverse controls if the debuff is active
        stats = state.players.get(inp.player_id)
        if stats is not None and stats.reversed_controls_ticks > 0:
            mx, my = -inp.move_x, -inp.move_y
        else:
            mx, my = inp.move_x, inp.move_y
        # Normalise diagonal input so speed is consistent
        mag = (mx * mx + my * my) ** 0.5
        if mag > 1.0:
            mx, my = mx / mag, my / mag

        speed = MAX_PLAYER_SPEED * (1 + stats.speed_level * 0.3) if stats else MAX_PLAYER_SPEED
        vx = mx * speed
        vy = my * speed
        space.set_player_velocity(inp.player_id, vx, vy)

    space.step(TICK_DT)

    # Write physics results back to GameState
    for pid in list(state.players.keys()):
        pos = space.get_player_position(pid)
        if pos is None:
            continue
        vel = space.get_player_velocity(pid)
        if pid in state.player_physics:
            state.player_physics[pid].x = pos[0]
            state.player_physics[pid].y = pos[1]
            state.player_physics[pid].vx = vel[0]
            state.player_physics[pid].vy = vel[1]
        else:
            state.player_physics[pid] = PhysicsState(pos[0], pos[1], vel[0], vel[1])

    # Sync bomb physics positions back to state
    for i, bomb in enumerate(state.bombs):
        pos = space.get_bomb_position(i)
        if pos:
            bomb.px, bomb.py = pos
