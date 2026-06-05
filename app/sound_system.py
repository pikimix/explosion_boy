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

_SFX_GAIN = 0.5
_MUSIC_GAIN = 0.4
_MUSIC_PATH = ':resources:music/funkyrobot.mp3'
_MUSIC_PITCH_NORMAL = 1.0
_MUSIC_PITCH_TENSE = 1.26
_SEMITONE = 2 ** (1 / 12)

_PICKUP_PATHS: dict[PowerupKind, str] = {
    PowerupKind.EXTRA_BOMB: ':resources:sounds/upgrade1.wav',
    PowerupKind.BLAST_UP:   ':resources:sounds/upgrade2.wav',
}


class SoundSystem:
    def __init__(self, local_player_id: int | None, volume: float = 1.0) -> None:
        self._player_id = local_player_id
        self._volume = max(0.0, min(1.0, volume))
        self._explosions = [arcade.load_sound(p) for p in _EXPLOSION_PATHS]
        self._pickups = {k: arcade.load_sound(p) for k, p in _PICKUP_PATHS.items()}
        self._music = arcade.load_sound(_MUSIC_PATH)
        self._music_player = arcade.play_sound(self._music, volume=self._volume * _MUSIC_GAIN, loop=True)
        self._debug_pitch: float = 1.0

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = max(0.0, min(1.0, value))
        if self._music_player:
            self._music_player.volume = self._volume * _MUSIC_GAIN

    @property
    def pitch(self) -> float:
        return self._music_player.pitch if self._music_player else self._debug_pitch

    def step_pitch(self) -> float:
        """Raise debug pitch by one semitone and return the new value."""
        self._debug_pitch *= _SEMITONE
        if self._music_player:
            self._music_player.pitch = self.pitch
        return self._debug_pitch

    def stop(self) -> None:
        if self._music_player:
            arcade.stop_sound(self._music_player)
            self._music_player = None

    def update(self, prev: GameState | None, curr: GameState) -> None:
        self._check_explosions(prev, curr)
        self._check_pickups(prev, curr)
        self._update_music_tempo(curr)

    def _update_music_tempo(self, curr: GameState) -> None:
        if not self._music_player:
            return
        tense = len(curr.player_physics) <= 2
        base = _MUSIC_PITCH_TENSE if tense else _MUSIC_PITCH_NORMAL
        self._music_player.pitch = base * self._debug_pitch

    def _check_explosions(self, prev: GameState | None, curr: GameState) -> None:
        prev_cells = {(e.col, e.row) for e in prev.explosions} if prev else set()
        curr_cells = {(e.col, e.row) for e in curr.explosions}
        if curr_cells - prev_cells:
            arcade.play_sound(random.choice(self._explosions), volume=self._volume * _SFX_GAIN)

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
                    arcade.play_sound(sound, volume=self._volume * _SFX_GAIN)
