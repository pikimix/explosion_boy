"""Client-side sound playback driven by game state changes."""
from __future__ import annotations

import random
from pathlib import Path

import arcade
import pyglet.media

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
_SCREAM_CHANCE = 4

_PICKUP_PATHS: dict[PowerupKind, str] = {
    PowerupKind.EXTRA_BOMB: ':resources:sounds/upgrade1.wav',
    PowerupKind.BLAST_UP:   ':resources:sounds/upgrade2.wav',
}

_SCREAM_PATH = Path(__file__).parent.parent / 'resources' / 'sounds' / 'scream.wav'

_music_volume: float = 1.0
_sfx_volume: float = 1.0


def set_music_volume(value: float) -> None:
    global _music_volume
    _music_volume = max(0.0, min(1.0, value))


def get_music_volume() -> float:
    return _music_volume


def set_sfx_volume(value: float) -> None:
    global _sfx_volume
    _sfx_volume = max(0.0, min(1.0, value))


def get_sfx_volume() -> float:
    return _sfx_volume


class MusicPlayer:
    """Loads and plays a single looping music track, with volume and pitch control."""

    def __init__(self, path: str | Path) -> None:
        self._sound = arcade.load_sound(str(path))
        self._player: pyglet.media.Player | None = None

    def play(self) -> None:
        self._player = arcade.play_sound(
            self._sound, volume=_music_volume * _MUSIC_GAIN, loop=True,
        )

    def sync_volume(self) -> None:
        if self._player:
            self._player.volume = _music_volume * _MUSIC_GAIN

    def stop(self) -> None:
        if self._player:
            arcade.stop_sound(self._player)
            self._player = None

    @property
    def pitch(self) -> float:
        return self._player.pitch if self._player else 1.0  # type: ignore[return-value]

    @pitch.setter
    def pitch(self, value: float) -> None:
        if self._player:
            self._player.pitch = value


class SoundSystem:
    def __init__(self, local_player_id: int | None,
                 music_volume: float = 1.0, sfx_volume: float = 1.0,
                 music_path: str | Path = _MUSIC_PATH) -> None:
        self._player_id = local_player_id
        set_music_volume(music_volume)
        set_sfx_volume(sfx_volume)
        self._explosions = [arcade.load_sound(p) for p in _EXPLOSION_PATHS]
        self._pickups = {k: arcade.load_sound(p) for k, p in _PICKUP_PATHS.items()}
        self._scream = arcade.load_sound(str(_SCREAM_PATH))
        self._music = MusicPlayer(music_path)
        self._music.play()
        self._debug_pitch: float = 1.0

    @property
    def music_volume(self) -> float:
        return get_music_volume()

    @music_volume.setter
    def music_volume(self, value: float) -> None:
        set_music_volume(value)
        self._music.sync_volume()

    @property
    def sfx_volume(self) -> float:
        return get_sfx_volume()

    @sfx_volume.setter
    def sfx_volume(self, value: float) -> None:
        set_sfx_volume(value)

    @property
    def pitch(self) -> float:
        return self._music.pitch

    def step_pitch(self) -> float:
        """Raise debug pitch by one semitone and return the new value."""
        self._debug_pitch *= _SEMITONE
        self._music.pitch = self._debug_pitch
        return self._debug_pitch

    def stop(self) -> None:
        self._music.stop()

    def update(self, prev: GameState | None, curr: GameState) -> None:
        self._check_explosions(prev, curr)
        self._check_deaths(prev, curr)
        self._check_pickups(prev, curr)
        self._update_music_tempo(curr)

    def _update_music_tempo(self, curr: GameState) -> None:
        tense = len(curr.player_physics) <= 2
        base = _MUSIC_PITCH_TENSE if tense else _MUSIC_PITCH_NORMAL
        self._music.pitch = base * self._debug_pitch

    def _check_deaths(self, prev: GameState | None, curr: GameState) -> None:
        if prev is None:
            return
        deaths = prev.player_physics.keys() - curr.player_physics.keys()
        if deaths and random.randint(1, _SCREAM_CHANCE) == 1:
            arcade.play_sound(self._scream, volume=get_sfx_volume() * _SFX_GAIN)

    def _check_explosions(self, prev: GameState | None, curr: GameState) -> None:
        prev_cells = {(e.col, e.row) for e in prev.explosions} if prev else set()
        curr_cells = {(e.col, e.row) for e in curr.explosions}
        if curr_cells - prev_cells:
            arcade.play_sound(
                random.choice(self._explosions), volume=get_sfx_volume() * _SFX_GAIN,
            )

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
                    arcade.play_sound(sound, volume=get_sfx_volume() * _SFX_GAIN)
