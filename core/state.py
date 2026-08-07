"""GameState — the canonical world snapshot. Fully serialisable, no methods."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.components import (
    BombComponent,
    Colour,
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
    """Canonical, fully serialisable snapshot of the world at a given tick."""

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
    player_colours: dict[int, Colour] = field(default_factory=dict)

    phase: GamePhase = GamePhase.LOBBY
    winner_id: int | None = None

    # Set once at round start; informational only (round setup used it to size
    # the initial grid via map_size_for_player_count).
    starting_player_count: int = 0

    # Perimeter shrink progress
    shrink_active: bool = False
    shrink_ring: int = 0                  # last CLOSED ring index (0 = none closed yet)
    shrink_target_ring: int = 0           # ring shrink is currently working towards (see update_shrink_target)
    shrink_warn_ring: int = 0             # ring currently flashing/warning, 0 = none pending
    shrink_warn_ticks_remaining: int = 0  # counts down like BombComponent.fuse_ticks_remaining
    shrink_next_warn_tick: int = 0        # tick the next ring's warning phase begins
    shrink_stopped: bool = False

    # Incremented server-side whenever tiles change; serialised so the client
    # can skip the expensive ShapeElementList rebuild when nothing changed.
    tiles_version: int = field(default=0, repr=False, compare=False)

    # Server-side caches — not serialised, not compared
    tiles_dirty: bool = field(default=True, repr=False, compare=False)
    tile_list_cache: list[list[int]] | None = field(
        default=None, repr=False, compare=False, init=False
    )

    # Set whenever explosions/explosion_rays are added or aged out; lets
    # _kill_players_in_explosions reuse its lit-cell set across ticks where
    # the active explosion batch hasn't changed.
    lit_cells_dirty: bool = field(default=True, repr=False, compare=False)
    lit_cells_cache: set | None = field(
        default=None, repr=False, compare=False, init=False
    )
