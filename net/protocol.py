"""
All network message dataclasses.

Every message has a 'type' string discriminator so decode_msg can route it.
GameState payloads are pre-encoded bytes (via core.serialiser) to avoid
double-serialisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.serialiser import decode_msg, encode_msg, encode_state, decode_state
from core.state import GameState


# ── Client → Server ────────────────────────────────────────────────────────────

@dataclass
class JoinMsg:
    player_name: str
    TYPE: str = "join"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "name": self.player_name})

    @staticmethod
    def decode(d: dict) -> "JoinMsg":
        return JoinMsg(player_name=d["name"])


@dataclass
class ReadyMsg:
    ready: bool
    TYPE: str = "ready"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "ready": self.ready})


@dataclass
class ColourMsg:
    colour_rgb: tuple[int, int, int]
    TYPE: str = 'colour'

    def encode(self) -> bytes:
        r, g, b = self.colour_rgb
        return encode_msg({'type': self.TYPE, 'r': r, 'g': g, 'b': b})

    @staticmethod
    def decode(d: dict) -> 'ColourMsg':
        return ColourMsg(colour_rgb=(d['r'], d['g'], d['b']))


@dataclass
class InputMsg:
    player_id: int
    tick: int
    move_x: float
    move_y: float
    place_bomb: bool
    TYPE: str = "input"

    def encode(self) -> bytes:
        return encode_msg({
            "type": self.TYPE,
            "pid": self.player_id,
            "t": self.tick,
            "mx": self.move_x,
            "my": self.move_y,
            "pb": self.place_bomb,
        })

    @staticmethod
    def decode(d: dict) -> "InputMsg":
        return InputMsg(
            player_id=d["pid"], tick=d["t"],
            move_x=d["mx"], move_y=d["my"],
            place_bomb=d["pb"],
        )


# ── Server → Client ────────────────────────────────────────────────────────────

@dataclass
class WelcomeMsg:
    assigned_player_id: int
    TYPE: str = "welcome"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "pid": self.assigned_player_id})

    @staticmethod
    def decode(d: dict) -> "WelcomeMsg":
        return WelcomeMsg(assigned_player_id=d["pid"])


@dataclass
class LobbyUpdateMsg:
    players: list[dict]   # [{"id": int, "name": str, "ready": bool}]
    TYPE: str = "lobby_update"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "players": self.players})

    @staticmethod
    def decode(d: dict) -> "LobbyUpdateMsg":
        return LobbyUpdateMsg(players=d["players"])


@dataclass
class GameStartMsg:
    state_bytes: bytes
    TYPE: str = "game_start"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "state": self.state_bytes})

    @staticmethod
    def decode(d: dict) -> "GameStartMsg":
        return GameStartMsg(state_bytes=bytes(d["state"]))

    def get_state(self) -> GameState:
        return decode_state(self.state_bytes)


@dataclass
class StateUpdateMsg:
    tick: int
    state_bytes: bytes
    TYPE: str = "state_update"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "t": self.tick,
                           "state": self.state_bytes})

    @staticmethod
    def decode(d: dict) -> "StateUpdateMsg":
        return StateUpdateMsg(tick=d["t"], state_bytes=bytes(d["state"]))

    def get_state(self) -> GameState:
        return decode_state(self.state_bytes)


@dataclass
class GameOverMsg:
    winner_id: int | None
    winner_name: str
    TYPE: str = "game_over"

    def encode(self) -> bytes:
        return encode_msg({"type": self.TYPE, "wid": self.winner_id,
                           "wname": self.winner_name})

    @staticmethod
    def decode(d: dict) -> "GameOverMsg":
        return GameOverMsg(winner_id=d["wid"], winner_name=d["wname"])


# ── Dispatcher ────────────────────────────────────────────────────────────────

AnyMsg = (JoinMsg | ReadyMsg | ColourMsg | InputMsg | WelcomeMsg | LobbyUpdateMsg
          | GameStartMsg | StateUpdateMsg | GameOverMsg)

_DECODERS = {
    "join":         JoinMsg.decode,
    "ready":        lambda d: ReadyMsg(ready=d.get("ready", True)),
    "colour":       ColourMsg.decode,
    "input":        InputMsg.decode,
    "welcome":      WelcomeMsg.decode,
    "lobby_update": LobbyUpdateMsg.decode,
    "game_start":   GameStartMsg.decode,
    "state_update": StateUpdateMsg.decode,
    "game_over":    GameOverMsg.decode,
}


def decode_any(data: bytes) -> AnyMsg | None:
    d = decode_msg(data)
    decoder = _DECODERS.get(d.get("type", ""))
    if decoder is None:
        return None
    return decoder(d)
