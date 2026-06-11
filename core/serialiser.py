"""msgpack encode/decode for GameState and all net messages.

All dataclasses are converted to plain dicts before packing.
Enums are serialised as their int value.
"""
from __future__ import annotations

from typing import Any

import msgpack

from core.components import (
    BombComponent,
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
            s.shield_invincibility_ticks]

def _enc_bomb(b: BombComponent) -> list:
    return [b.owner_id, b.fuse_ticks_remaining, b.blast_radius,
            b.col, b.row, b.px, b.py, b.vx, b.vy, b.is_super, b.is_cluster]

def _enc_exp_center(e: ExplosionCenter) -> list:
    return [e.col, e.row, e.ticks_remaining]

def _enc_exp_ray(r: ExplosionRay) -> list:
    return [r.origin_col, r.origin_row, r.direction[0], r.direction[1],
            r.length, r.ticks_remaining]

def _enc_powerup(p: PowerupComponent) -> list:
    return [int(p.kind), p.col, p.row]


def encode_state(gs: GameState) -> bytes:
    if gs.tiles_dirty or gs.tile_list_cache is None:
        gs.tile_list_cache = [[int(c) for c in row] for row in gs.tiles]
        gs.tiles_dirty = False
    d: dict[str, Any] = {
        "t": gs.tick,
        "mc": gs.map_cols,
        "mr": gs.map_rows,
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
        "pc": {str(k): list(v) for k, v in gs.player_colours.items()},
    }
    return msgpack.packb(d, use_bin_type=True)


# ── Decode ─────────────────────────────────────────────────────────────────────

def decode_state(data: bytes) -> GameState:
    d = msgpack.unpackb(data, raw=False)
    return GameState(
        tick=d["t"],
        map_cols=d["mc"],
        map_rows=d["mr"],
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
        player_colours={int(k): tuple(v) for k, v in d.get("pc", {}).items()},
        phase=GamePhase(d["ph"]),
        winner_id=d["wi"],
    )


# ── Generic message encode/decode (for net/protocol.py messages) ───────────────

def encode_msg(obj: dict[str, Any]) -> bytes:
    return msgpack.packb(obj, use_bin_type=True)


def decode_msg(data: bytes) -> dict[str, Any]:
    return msgpack.unpackb(data, raw=False)
