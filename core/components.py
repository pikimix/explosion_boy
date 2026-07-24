"""All primitive game dataclasses. No methods, no imports from other game layers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class TileKind(IntEnum):
    """The kind of terrain occupying a single grid cell."""
    EMPTY      = 0
    SOLID_WALL = 1
    SOFT_BLOCK = 2


class GamePhase(IntEnum):
    """The current stage of the overall match lifecycle."""
    LOBBY     = 0
    PLAYING   = 1
    GAME_OVER = 2


class PowerupKind(IntEnum):
    """The type of powerup a player can collect and its effect."""
    EXTRA_BOMB            = 1
    BLAST_UP              = 2
    SHIELD                = 3
    REVERSE_CONTROLS      = 4   # affects all other players
    SPEED_UP              = 5
    SKULL                 = 6
    SUPER_BOMB            = 7
    CLUSTER_BOMB          = 8
    RUBBLE_BOMB           = 9
    REVERSE_CONTROLS_SELF = 10  # affects only the collector
    BLAST_PENETRATION     = 11  # how many soft blocks one arm can punch through


@dataclass(frozen=True)
class Cell:
    """A grid cell position, usable as a dict/set key."""
    col: int
    row: int


@dataclass(frozen=True)
class Colour:
    """An RGB colour, e.g. a player's chosen colour."""
    r: int
    g: int
    b: int

    def as_tuple(self) -> tuple[int, int, int]:
        """Return the ``(r, g, b)`` tuple form, e.g. for arcade draw calls or msgpack.

        Returns
        -------
        tuple[int, int, int]
            The colour as a plain ``(r, g, b)`` tuple.
        """
        return self.r, self.g, self.b


@dataclass(frozen=True)
class Position:
    """A physics body's position, in pixels."""
    x: float
    y: float


@dataclass(frozen=True)
class Velocity:
    """A physics body's velocity, in pixels per second."""
    vx: float
    vy: float


@dataclass
class PhysicsState:
    """Server-authoritative continuous position and velocity (pixels)."""
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class PlayerStats:
    """A player's persistent gameplay stats and active powerup effects."""
    player_id: int
    lives: int          = 1
    bomb_capacity: int  = 1
    bombs_in_use: int   = 0
    blast_radius: int   = 2
    shield: bool        = False
    reversed_controls_ticks: int = 0
    speed_level:        int  = 0
    has_super_bomb:     bool = False
    has_cluster_bomb:   bool = False
    has_rubble_bomb:    bool = False
    shield_invincibility_ticks: int = 0
    blast_penetration:  int  = 2  # starts matching blast_radius default


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
    is_super:          bool = False
    is_cluster:        bool = False
    is_rubble:         bool = False
    blast_penetration: int  = 1


@dataclass
class ExplosionCenter:
    """The origin cell of an active explosion and its remaining lifetime."""
    col: int
    row: int
    ticks_remaining: int


@dataclass
class ExplosionRay:
    """One directional arm of blast radiating out from an explosion center."""
    origin_col: int
    origin_row: int
    direction: tuple[int, int]
    length: int
    ticks_remaining: int


@dataclass
class PowerupComponent:
    """A powerup item sitting on the grid, waiting to be collected."""
    kind: PowerupKind
    col: int
    row: int


@dataclass
class PlayerInput:
    """A player's per-tick input: movement direction and bomb placement."""
    player_id: int
    tick: int
    move_x: float              # -1.0 … 1.0  (keyboard: -1 / 0 / 1)
    move_y: float
    place_bomb: bool


# Neutral input used when a player sends nothing for a tick
def neutral_input(player_id: int, tick: int) -> PlayerInput:
    """Build a `PlayerInput` representing no movement and no bomb placement.

    Parameters
    ----------
    player_id : int
        The player this input belongs to.
    tick : int
        The simulation tick this input applies to.

    Returns
    -------
    PlayerInput
        A neutral input used when a player sends nothing for a tick.
    """
    return PlayerInput(
        player_id=player_id, tick=tick,
        move_x=0.0, move_y=0.0, place_bomb=False,
    )
