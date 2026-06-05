"""All primitive game dataclasses. No methods, no imports from other game layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class TileKind(IntEnum):
    EMPTY      = 0
    SOLID_WALL = 1
    SOFT_BLOCK = 2


class GamePhase(IntEnum):
    LOBBY     = 0
    PLAYING   = 1
    GAME_OVER = 2


class PowerupKind(IntEnum):
    EXTRA_BOMB       = 1
    BLAST_UP         = 2
    SHIELD           = 3
    REVERSE_CONTROLS = 4


@dataclass
class PhysicsState:
    """Server-authoritative continuous position and velocity (pixels)."""
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class PlayerStats:
    player_id: int
    lives: int          = 1
    bomb_capacity: int  = 1
    bombs_in_use: int   = 0
    blast_radius: int   = 2
    shield: bool        = False
    reversed_controls_ticks: int = 0


@dataclass
class BombComponent:
    """Grid cell is the authority for explosion logic; px/py drive the physics body."""
    owner_id: int
    fuse_ticks_remaining: int
    blast_radius: int
    col: int
    row: int
    px: float
    py: float
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class ExplosionCenter:
    col: int
    row: int
    ticks_remaining: int


@dataclass
class ExplosionRay:
    origin_col: int
    origin_row: int
    direction: tuple[int, int]
    length: int
    ticks_remaining: int


@dataclass
class PowerupComponent:
    kind: PowerupKind
    col: int
    row: int


@dataclass
class PlayerInput:
    player_id: int
    tick: int
    move_x: float              # -1.0 … 1.0  (keyboard: -1 / 0 / 1)
    move_y: float
    place_bomb: bool


# Neutral input used when a player sends nothing for a tick
def neutral_input(player_id: int, tick: int) -> PlayerInput:
    return PlayerInput(
        player_id=player_id, tick=tick,
        move_x=0.0, move_y=0.0, place_bomb=False,
    )
