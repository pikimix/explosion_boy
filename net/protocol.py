"""
All network message dataclasses.

Every message has a 'type' string discriminator so decode_msg can route it.
GameState payloads are pre-encoded bytes (via core.serialiser) to avoid
double-serialisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.components import Colour
from core.serialiser import decode_msg, encode_msg, decode_state
from core.state import GameState

PROTOCOL_VERSION: int = 2

# ── Client → Server ────────────────────────────────────────────────────────────

@dataclass
class JoinMsg:
    """Client request to join the game with a chosen player name."""

    player_name: str
    version: int = PROTOCOL_VERSION
    TYPE: str = "join"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "name": self.player_name,
                           "v": self.version})

    @staticmethod
    def decode(d: dict) -> "JoinMsg":
        """Build a JoinMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        JoinMsg
            The reconstructed message.
        """
        return JoinMsg(player_name=d["name"], version=d.get("v", 0))


@dataclass
class ReadyMsg:
    """Client notification of the player's ready status in the lobby."""

    ready: bool
    TYPE: str = "ready"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "ready": self.ready})


@dataclass
class ColourMsg:
    """Client request to set the player's chosen colour."""

    colour: Colour
    TYPE: str = 'colour'

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({'type': self.TYPE, 'r': self.colour.r, 'g': self.colour.g, 'b': self.colour.b})

    @staticmethod
    def decode(d: dict) -> 'ColourMsg':
        """Build a ColourMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        ColourMsg
            The reconstructed message.
        """
        return ColourMsg(colour=Colour(d['r'], d['g'], d['b']))


@dataclass
class RenameMsg:
    """Client request to change the player's name."""

    new_name: str
    TYPE: str = 'rename'

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({'type': self.TYPE, 'name': self.new_name})

    @staticmethod
    def decode(d: dict) -> 'RenameMsg':
        """Build a RenameMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        RenameMsg
            The reconstructed message.
        """
        return RenameMsg(new_name=d['name'])


@dataclass
class InputMsg:
    """Client per-tick input state, including movement and bomb placement."""

    player_id: int
    tick: int
    move_x: float
    move_y: float
    place_bomb: bool
    TYPE: str = "input"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
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
        """Build an InputMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        InputMsg
            The reconstructed message.
        """
        return InputMsg(
            player_id=d["pid"], tick=d["t"],
            move_x=d["mx"], move_y=d["my"],
            place_bomb=d["pb"],
        )


# ── Server → Client ────────────────────────────────────────────────────────────

@dataclass
class RejectMsg:
    """Server notification that a client request was rejected."""

    reason: str
    TYPE: str = "reject"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "reason": self.reason})

    @staticmethod
    def decode(d: dict) -> "RejectMsg":
        """Build a RejectMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        RejectMsg
            The reconstructed message.
        """
        return RejectMsg(reason=d.get("reason", "Rejected by server"))


@dataclass
class WelcomeMsg:
    """Server acknowledgement assigning a player id and tick rate to a client."""

    assigned_player_id: int
    tick_rate: int = 60
    TYPE: str = "welcome"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "pid": self.assigned_player_id,
                           "tr": self.tick_rate})

    @staticmethod
    def decode(d: dict) -> "WelcomeMsg":
        """Build a WelcomeMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        WelcomeMsg
            The reconstructed message.
        """
        return WelcomeMsg(assigned_player_id=d["pid"], tick_rate=d.get("tr", 60))


@dataclass
class LobbyUpdateMsg:
    """Server broadcast of the current lobby roster and ready states."""

    players: list[dict]   # [{"id": int, "name": str, "ready": bool}]
    TYPE: str = "lobby_update"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "players": self.players})

    @staticmethod
    def decode(d: dict) -> "LobbyUpdateMsg":
        """Build a LobbyUpdateMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        LobbyUpdateMsg
            The reconstructed message.
        """
        return LobbyUpdateMsg(players=d["players"])


@dataclass
class GameStartMsg:
    """Server notification that the game has begun, carrying the initial state."""

    state_bytes: bytes
    TYPE: str = "game_start"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "state": self.state_bytes})

    @staticmethod
    def decode(d: dict) -> "GameStartMsg":
        """Build a GameStartMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        GameStartMsg
            The reconstructed message.
        """
        return GameStartMsg(state_bytes=bytes(d["state"]))

    def get_state(self) -> GameState:
        """Decode the embedded state bytes into a GameState.

        Returns
        -------
        GameState
            The deserialised game state.
        """
        return decode_state(self.state_bytes)


@dataclass
class StateUpdateMsg:
    """Server per-tick broadcast of the authoritative game state."""

    tick: int
    state_bytes: bytes
    TYPE: str = "state_update"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "t": self.tick,
                           "state": self.state_bytes})

    @staticmethod
    def decode(d: dict) -> "StateUpdateMsg":
        """Build a StateUpdateMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        StateUpdateMsg
            The reconstructed message.
        """
        return StateUpdateMsg(tick=d["t"], state_bytes=bytes(d["state"]))

    def get_state(self) -> GameState:
        """Decode the embedded state bytes into a GameState.

        Returns
        -------
        GameState
            The deserialised game state.
        """
        return decode_state(self.state_bytes)


@dataclass
class GameOverMsg:
    """Server notification that the game has ended, with the winner or drawers."""

    winner_id: int | None
    winner_name: str
    draw_names: list[str] = field(default_factory=list)
    TYPE: str = "game_over"

    def encode(self) -> bytes:
        """Encode this message into its wire byte representation.

        Returns
        -------
        bytes
            The encoded message ready to be sent over the network.
        """
        return encode_msg({"type": self.TYPE, "wid": self.winner_id,
                           "wname": self.winner_name, "dnames": self.draw_names})

    @staticmethod
    def decode(d: dict) -> "GameOverMsg":
        """Build a GameOverMsg from a decoded wire dictionary.

        Parameters
        ----------
        d : dict
            The raw decoded message fields.

        Returns
        -------
        GameOverMsg
            The reconstructed message.
        """
        return GameOverMsg(winner_id=d["wid"], winner_name=d["wname"],
                           draw_names=d.get("dnames", []))


# ── Dispatcher ────────────────────────────────────────────────────────────────

AnyMsg = (JoinMsg | ReadyMsg | ColourMsg | RenameMsg | InputMsg | RejectMsg | WelcomeMsg
          | LobbyUpdateMsg | GameStartMsg | StateUpdateMsg | GameOverMsg)

_DECODERS = {
    "join":         JoinMsg.decode,
    "ready":        lambda d: ReadyMsg(ready=d.get("ready", True)),
    "colour":       ColourMsg.decode,
    "rename":       RenameMsg.decode,
    "input":        InputMsg.decode,
    "reject":       RejectMsg.decode,
    "welcome":      WelcomeMsg.decode,
    "lobby_update": LobbyUpdateMsg.decode,
    "game_start":   GameStartMsg.decode,
    "state_update": StateUpdateMsg.decode,
    "game_over":    GameOverMsg.decode,
}


def decode_any(data: bytes) -> AnyMsg | None:
    """Decode raw wire bytes into the appropriate message dataclass.

    Parameters
    ----------
    data : bytes
        The raw encoded message bytes received from the network.

    Returns
    -------
    AnyMsg or None
        The decoded message instance, or None if the data could not be
        decoded or its type is unrecognised.
    """
    try:
        d = decode_msg(data)
    except Exception:
        return None
    decoder = _DECODERS.get(d.get("type", ""))
    if decoder is None:
        return None
    return decoder(d)
