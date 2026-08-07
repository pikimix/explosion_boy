"""msgpack encode/decode for GameState and all net messages.

All dataclasses are converted to plain dicts before packing.
Enums are serialised as their int value.
"""
from __future__ import annotations

from typing import Any

import msgpack

from core.components import (
    BombComponent,
    Colour,
    ExplosionCenter,
    ExplosionRay,
    GamePhase,
    PhysicsState,
    PlayerStats,
    PowerupComponent,
    PowerupKind,
    TileKind,
)
from core.state import GameState


# ── Encode ─────────────────────────────────────────────────────────────────────

def _enc_physics(p: PhysicsState) -> list:
    return [p.x, p.y, p.vx, p.vy]

def _enc_stats(s: PlayerStats) -> list:
    return [s.player_id, s.lives, s.bomb_capacity, s.bombs_in_use, s.blast_radius, s.shield,
            s.reversed_controls_ticks, s.speed_level, s.has_super_bomb, s.has_cluster_bomb,
            s.has_rubble_bomb, s.shield_invincibility_ticks, s.blast_penetration]

def _enc_bomb(b: BombComponent) -> list:
    return [b.owner_id, b.fuse_ticks_remaining, b.blast_radius,
            b.col, b.row, b.px, b.py, b.vx, b.vy, b.is_super, b.is_cluster, b.is_rubble,
            b.blast_penetration]

def _enc_exp_center(e: ExplosionCenter) -> list:
    return [e.col, e.row, e.ticks_remaining]

def _enc_exp_ray(r: ExplosionRay) -> list:
    return [r.origin_col, r.origin_row, r.direction[0], r.direction[1],
            r.length, r.ticks_remaining]

def _enc_powerup(p: PowerupComponent) -> list:
    return [int(p.kind), p.col, p.row]


def encode_state(gs: GameState) -> bytes:
    """Pack a ``GameState`` into msgpack bytes for network transmission.

    Parameters
    ----------
    gs : GameState
        The game state to serialise. Its tile cache/version is refreshed
        in place if the tile grid has changed since the last encode.

    Returns
    -------
    bytes
        The msgpack-encoded representation of the state.
    """
    if gs.tiles_dirty or gs.tile_list_cache is None:
        gs.tiles_version += 1
        gs.tile_list_cache = [[int(c) for c in row] for row in gs.tiles]
        gs.tiles_dirty = False
    d: dict[str, Any] = {
        "t": gs.tick,
        "mc": gs.map_cols,
        "mr": gs.map_rows,
        "tv": gs.tiles_version,
        "tl": gs.tile_list_cache,
        "pl": {str(k): _enc_stats(v) for k, v in gs.players.items()},
        "pp": {str(k): _enc_physics(v) for k, v in gs.player_physics.items()},
        "bm": [_enc_bomb(b) for b in gs.bombs],
        "ex": [_enc_exp_center(e) for e in gs.explosions],
        "er": [_enc_exp_ray(r) for r in gs.explosion_rays],
        "pw": [_enc_powerup(p) for p in gs.powerups],
        "ph": int(gs.phase),
        "wi": gs.winner_id,
        "pn": {str(k): v for k, v in gs.player_names.items()},
        "pc": {str(k): list(v.as_tuple()) for k, v in gs.player_colours.items()},
        "spc": gs.starting_player_count,
        "sa": gs.shrink_active,
        "sr": gs.shrink_ring,
        "str": gs.shrink_target_ring,
        "swr": gs.shrink_warn_ring,
        "swt": gs.shrink_warn_ticks_remaining,
        "snw": gs.shrink_next_warn_tick,
        "ss": gs.shrink_stopped,
    }
    return msgpack.packb(d, use_bin_type=True)


# ── Decode ─────────────────────────────────────────────────────────────────────

def decode_state(data: bytes) -> GameState:
    """Unpack msgpack bytes back into a ``GameState``.

    Parameters
    ----------
    data : bytes
        The msgpack-encoded state, as produced by :func:`encode_state`.

    Returns
    -------
    GameState
        The reconstructed game state.
    """
    d = msgpack.unpackb(data, raw=False)
    return GameState(
        tick=d["t"],
        map_cols=d["mc"],
        map_rows=d["mr"],
        tiles_version=d.get("tv", 0),
        tiles=[[TileKind(c) for c in row] for row in d["tl"]],
        players={int(k): PlayerStats(*v) for k, v in d["pl"].items()},
        player_physics={int(k): PhysicsState(*v) for k, v in d["pp"].items()},
        bombs=[BombComponent(*b) for b in d["bm"]],
        explosions=[ExplosionCenter(*e) for e in d["ex"]],
        explosion_rays=[
            ExplosionRay(r[0], r[1], (r[2], r[3]), r[4], r[5])
            for r in d["er"]
        ],
        powerups=[PowerupComponent(PowerupKind(p[0]), p[1], p[2]) for p in d["pw"]],
        player_names={int(k): v for k, v in d.get("pn", {}).items()},
        player_colours={int(k): Colour(*v) for k, v in d.get("pc", {}).items()},
        phase=GamePhase(d["ph"]),
        winner_id=d["wi"],
        starting_player_count=d.get("spc", 0),
        shrink_active=d.get("sa", False),
        shrink_ring=d.get("sr", 0),
        shrink_target_ring=d.get("str", 0),
        shrink_warn_ring=d.get("swr", 0),
        shrink_warn_ticks_remaining=d.get("swt", 0),
        shrink_next_warn_tick=d.get("snw", 0),
        shrink_stopped=d.get("ss", False),
    )


# ── Generic message encode/decode (for net/protocol.py messages) ───────────────

def encode_msg(obj: dict[str, Any]) -> bytes:
    """Pack a plain dict (e.g. a net/protocol.py message) into msgpack bytes.

    Parameters
    ----------
    obj : dict of str to Any
        The message payload to serialise.

    Returns
    -------
    bytes
        The msgpack-encoded representation of ``obj``.
    """
    return msgpack.packb(obj, use_bin_type=True)


def decode_msg(data: bytes) -> dict[str, Any]:
    """Unpack msgpack bytes back into a plain dict.

    Parameters
    ----------
    data : bytes
        The msgpack-encoded message, as produced by :func:`encode_msg`.

    Returns
    -------
    dict of str to Any
        The reconstructed message payload.
    """
    return msgpack.unpackb(data, raw=False)
