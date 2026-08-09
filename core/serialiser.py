"""msgpack encode/decode for GameState and all net messages.

All dataclasses are converted to plain dicts before packing.
Enums are serialised as their int value.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, TypeVar

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
    SmokeCloud,
    TileKind,
)
from core.state import GameState


# ── Encode ─────────────────────────────────────────────────────────────────────

def _enc_physics(p: PhysicsState) -> list:
    return list(dataclasses.astuple(p))

def _enc_stats(s: PlayerStats) -> list:
    return list(dataclasses.astuple(s))

def _enc_bomb(b: BombComponent) -> list:
    return list(dataclasses.astuple(b))

def _enc_exp_center(e: ExplosionCenter) -> list:
    return list(dataclasses.astuple(e))

def _enc_exp_ray(r: ExplosionRay) -> list:
    return [r.origin_col, r.origin_row, r.direction[0], r.direction[1],
            r.length, r.ticks_remaining]

def _enc_smoke(sc: SmokeCloud) -> list:
    return list(dataclasses.astuple(sc))

def _enc_powerup(p: PowerupComponent) -> list:
    return [int(p.kind), p.col, p.row]


V = TypeVar("V")


def _enc_keyed(d: dict[int, V], enc: Callable[[V], Any] = lambda v: v) -> dict[str, Any]:
    return {str(k): enc(v) for k, v in d.items()}

def _dec_keyed(d: dict[str, Any], dec: Callable[[Any], V] = lambda v: v) -> dict[int, V]:
    return {int(k): dec(v) for k, v in d.items()}

def _enc_list(items: list[V], enc: Callable[[V], Any]) -> list[Any]:
    return [enc(x) for x in items]

def _dec_list(items: list[Any], dec: Callable[[Any], V]) -> list[V]:
    return [dec(x) for x in items]


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
        "pl": _enc_keyed(gs.players, _enc_stats),
        "pp": _enc_keyed(gs.player_physics, _enc_physics),
        "bm": _enc_list(gs.bombs, _enc_bomb),
        "ex": _enc_list(gs.explosions, _enc_exp_center),
        "er": [_enc_exp_ray(r) for r in gs.explosion_rays],
        "sm": _enc_list(gs.smoke_clouds, _enc_smoke),
        "pw": [_enc_powerup(p) for p in gs.powerups],
        "ph": int(gs.phase),
        "wi": gs.winner_id,
        "pn": _enc_keyed(gs.player_names),
        "pc": _enc_keyed(gs.player_colours, lambda v: list(v.as_tuple())),
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
        players=_dec_keyed(d["pl"], lambda v: PlayerStats(*v)),
        player_physics=_dec_keyed(d["pp"], lambda v: PhysicsState(*v)),
        bombs=_dec_list(d["bm"], lambda b: BombComponent(*b)),
        explosions=_dec_list(d["ex"], lambda e: ExplosionCenter(*e)),
        explosion_rays=[
            ExplosionRay(r[0], r[1], (r[2], r[3]), r[4], r[5])
            for r in d["er"]
        ],
        smoke_clouds=_dec_list(d["sm"], lambda s: SmokeCloud(*s)),
        powerups=[PowerupComponent(PowerupKind(p[0]), p[1], p[2]) for p in d["pw"]],
        player_names=_dec_keyed(d.get("pn", {})),
        player_colours=_dec_keyed(d.get("pc", {}), lambda v: Colour(*v)),
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
