"""GameState — the canonical world snapshot. Fully serialisable, no methods."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.components import (
    BombComponent,
    ExplosionCenter,
    ExplosionRay,
    GamePhase,
    PlayerStats,
    PhysicsState,
    PowerupComponent,
    TileKind,
)


@dataclass
class GameState:
    tick: int
    map_cols: int
    map_rows: int

    # tiles[row][col]
    tiles: list[list[TileKind]] = field(default_factory=list)

    # keyed by player_id (0-based index, assigned at lobby)
    players: dict[int, PlayerStats] = field(default_factory=dict)
    player_physics: dict[int, PhysicsState] = field(default_factory=dict)

    bombs: list[BombComponent] = field(default_factory=list)
    explosions: list[ExplosionCenter] = field(default_factory=list)
    explosion_rays: list[ExplosionRay] = field(default_factory=list)
    powerups: list[PowerupComponent] = field(default_factory=list)

    player_names: dict[int, str] = field(default_factory=dict)

    phase: GamePhase = GamePhase.LOBBY
    winner_id: int | None = None
