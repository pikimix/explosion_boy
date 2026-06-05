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
