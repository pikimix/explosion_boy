"""Powerup drop on soft block destruction and pickup on player contact."""
from __future__ import annotations

import random

from core.components import PowerupComponent, PowerupKind
from core.state import GameState
from engine.config import SOFT_BLOCK_DROP_CHANCE
from systems.collision import px_to_grid


def maybe_drop_powerup(state: GameState, col: int, row: int) -> None:
    if random.random() >= SOFT_BLOCK_DROP_CHANCE:
        return
    kind = random.choice(list(PowerupKind))
    state.powerups.append(PowerupComponent(kind=kind, col=col, row=row))


def process_powerup_pickups(state: GameState) -> None:
    if not state.powerups:
        return

    to_remove: list[int] = []
    for i, pup in enumerate(state.powerups):
        for pid, phys in state.player_physics.items():
            col, row = px_to_grid(phys.x, phys.y)
            if col == pup.col and row == pup.row:
                _apply(state, pid, pup.kind)
                to_remove.append(i)
                break

    for i in sorted(to_remove, reverse=True):
        state.powerups.pop(i)


REVERSE_CONTROLS_TICKS = 200   # 10 seconds at 20 tps
SPEED_BOOST_MAX_LEVEL  = 3
CLUSTER_SUB_FUSE_TICKS = 40    # 2 seconds at 20 tps


def tick_status_effects(state: GameState) -> None:
    """Count down timed powerup effects."""
    for stats in state.players.values():
        if stats.reversed_controls_ticks > 0:
            stats.reversed_controls_ticks -= 1
        if stats.shield_invincibility_ticks > 0:
            stats.shield_invincibility_ticks -= 1


def _apply(state: GameState, player_id: int, kind: PowerupKind) -> None:
    stats = state.players.get(player_id)
    if stats is None:
        return
    if kind == PowerupKind.EXTRA_BOMB:
        stats.bomb_capacity += 1
    elif kind == PowerupKind.BLAST_UP:
        stats.blast_radius += 1
    elif kind == PowerupKind.SHIELD:
        stats.shield = True
    elif kind == PowerupKind.REVERSE_CONTROLS:
        stats.reversed_controls_ticks = REVERSE_CONTROLS_TICKS
    elif kind == PowerupKind.SPEED_UP:
        stats.speed_level = min(stats.speed_level + 1, SPEED_BOOST_MAX_LEVEL)
    elif kind == PowerupKind.SKULL:
        effect = random.choice(["speed_down", "bomb_down", "blast_down"])
        if effect == "speed_down":
            stats.speed_level = max(0, stats.speed_level - 1)
        elif effect == "bomb_down":
            stats.bomb_capacity = max(1, stats.bomb_capacity - 1)
        else:
            stats.blast_radius = max(1, stats.blast_radius - 1)
    elif kind == PowerupKind.SUPER_BOMB:
        stats.has_super_bomb = True
    elif kind == PowerupKind.CLUSTER_BOMB:
        stats.has_cluster_bomb = True
