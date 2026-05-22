"""Client-side sound playback driven by game state changes."""
from __future__ import annotations

import random

import arcade

from core.components import PowerupKind
from core.state import GameState
from systems.collision import px_to_grid

_EXPLOSION_PATHS = [
    ':resources:sounds/explosion1.wav',
    ':resources:sounds/explosion2.wav',
]

_PICKUP_PATHS: dict[PowerupKind, str] = {
    PowerupKind.EXTRA_BOMB: ':resources:sounds/upgrade1.wav',
    PowerupKind.BLAST_UP:   ':resources:sounds/upgrade2.wav',
}


class SoundSystem:
    def __init__(self, local_player_id: int | None) -> None:
        self._player_id = local_player_id
        self._explosions = [arcade.load_sound(p) for p in _EXPLOSION_PATHS]
        self._pickups = {k: arcade.load_sound(p) for k, p in _PICKUP_PATHS.items()}

    def update(self, prev: GameState | None, curr: GameState) -> None:
        self._check_explosions(prev, curr)
        self._check_pickups(prev, curr)

    def _check_explosions(self, prev: GameState | None, curr: GameState) -> None:
        prev_cells = {(e.col, e.row) for e in prev.explosions} if prev else set()
        curr_cells = {(e.col, e.row) for e in curr.explosions}
        if curr_cells - prev_cells:
            arcade.play_sound(random.choice(self._explosions))

    def _check_pickups(self, prev: GameState | None, curr: GameState) -> None:
        if prev is None or self._player_id is None:
            return
        phys = curr.player_physics.get(self._player_id)
        if phys is None:
            return
        player_pos = px_to_grid(phys.x, phys.y)
        prev_by_pos = {(p.col, p.row): p.kind for p in prev.powerups}
        curr_positions = {(p.col, p.row) for p in curr.powerups}
        for pos, kind in prev_by_pos.items():
            if pos not in curr_positions and pos == player_pos:
                sound = self._pickups.get(kind)
                if sound:
                    arcade.play_sound(sound)
